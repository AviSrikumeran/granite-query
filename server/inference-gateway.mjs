/* Local, disabled-by-default Vercel gateway foundation. No deployment or GPU work.
 * Modal proxy tokens are not workspace API tokens. Their documented headers:
 * https://modal.com/docs/guide/webhook-proxy-auth
 * The Modal ASGI decorator must separately enable requires_proxy_auth=True.
 * Configuration attestations are operator gates, not proof of remote controls.
 */
export const SERVICE='granite-query-inference-gateway';
export const VERSION=1;
export const MODEL='ibm-granite/granite-4.2-3b';
export const REVISION='4e9c275e232f10211ec88644d106a1f6a1b60e06';
const BODY_LIMIT=16384,RESPONSE_LIMIT=65536;
const UUID=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
const NAME=/^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/;

class GatewayError extends Error{
  constructor(status,code,message,completion='not_started'){super(message);Object.assign(this,{status,code,completion});}
}
const failure=(status,code,message,completion)=>new GatewayError(status,code,message,completion);
const disabled=()=>failure(503,'not_configured','Interactive inference is not connected on this host.');

function configuration(env,now){
  if(env.GRANITE_INFERENCE_ENABLED!=='true')throw disabled();
  if(env.GRANITE_DURABLE_ADMISSION_CONFIRMED!=='true'||env.GRANITE_PROXY_AUTH_CONFIRMED!=='true')throw disabled();
  let endpoint,origin;
  try{endpoint=new URL(env.MODAL_INFERENCE_BASE_URL);origin=new URL(env.PUBLIC_SITE_ORIGIN);}catch{throw disabled();}
  if(endpoint.protocol!=='https:'||endpoint.username||endpoint.password||endpoint.search||endpoint.hash||!endpoint.hostname||/%2f|%5c/i.test(endpoint.pathname))throw disabled();
  if(origin.protocol!=='https:'||origin.username||origin.password||origin.search||origin.hash||origin.pathname!=='/'||origin.origin!==env.PUBLIC_SITE_ORIGIN)throw disabled();
  if(!/^wk-[A-Za-z0-9_-]{4,200}$/.test(env.MODAL_PROXY_TOKEN_ID??'')||!/^ws-[A-Za-z0-9_-]{4,200}$/.test(env.MODAL_PROXY_TOKEN_SECRET??''))throw disabled();
  if(!NAME.test(env.GRANITE_CHECKPOINT_ID??'')||!NAME.test(env.GRANITE_CHECKPOINT_VARIANT??'')||env.GRANITE_MODEL_REVISION!==REVISION)throw disabled();
  const expires=Date.parse(env.GRANITE_TRIAL_EXPIRES_AT_UTC);
  if(!/^\d{4}-\d\d-\d\dT.*Z$/.test(env.GRANITE_TRIAL_EXPIRES_AT_UTC??'')||!Number.isFinite(expires))throw disabled();
  if(expires<=now())throw failure(410,'trial_expired','The configured inference trial has ended.');
  endpoint.pathname=endpoint.pathname.replace(/\/$/,'')+'/';
  return {endpoint,origin:origin.origin,host:origin.host,checkpoint:env.GRANITE_CHECKPOINT_ID,variant:env.GRANITE_CHECKPOINT_VARIANT,revision:REVISION,expires,expiresISO:new Date(expires).toISOString(),key:env.MODAL_PROXY_TOKEN_ID,secret:env.MODAL_PROXY_TOKEN_SECRET};
}

function header(req,name){const headers=req.headers??{};const value=typeof headers.get==='function'?headers.get(name):headers[name.toLowerCase()];return typeof value==='string'?value:null;}
function checkOrigin(req,config){
  const origin=header(req,'origin');
  if(origin!==null){if(origin!==config.origin)throw failure(403,'origin_denied','This request must come from the configured website.');}
  else if(req.method!=='GET'||header(req,'host')!==config.host||header(req,'sec-fetch-site')==='cross-site')throw failure(403,'origin_denied','This request must come from the configured website.');
  if(header(req,'sec-fetch-site')==='cross-site')throw failure(403,'origin_denied','Cross-site requests are not accepted.');
}

async function requestBody(req){
  const contentType=(header(req,'content-type')??'').split(';')[0].trim().toLowerCase();
  if(contentType!=='application/json')throw failure(415,'unsupported_media_type','Use Content-Type application/json.');
  if(header(req,'content-encoding')&&!/^identity$/i.test(header(req,'content-encoding')))throw failure(415,'unsupported_media_type','Compressed request bodies are not supported.');
  const length=header(req,'content-length');
  if(length!==null&&(!/^\d+$/.test(length)||Number(length)>BODY_LIMIT))throw failure(413,'request_too_large','The request body must not exceed 16 KiB.');
  let raw,providedBody;
  try{providedBody=req.body;}catch{throw failure(422,'invalid_request','The request must contain valid JSON.');}
  if(providedBody!==undefined){
    try{raw=Buffer.isBuffer(providedBody)?providedBody:typeof providedBody==='string'?Buffer.from(providedBody):Buffer.from(JSON.stringify(providedBody));}catch{throw failure(422,'invalid_request','The request must contain valid JSON.');}
    if(raw.byteLength>BODY_LIMIT)throw failure(413,'request_too_large','The request body must not exceed 16 KiB.');
  }else if(typeof req[Symbol.asyncIterator]==='function'){
    const chunks=[];let size=0;const iterator=req[Symbol.asyncIterator]();
    while(true){const {done,value}=await iterator.next();if(done)break;const part=Buffer.from(value);size+=part.byteLength;if(size>BODY_LIMIT){req.pause?.();throw failure(413,'request_too_large','The request body must not exceed 16 KiB.');}chunks.push(part);}
    raw=Buffer.concat(chunks);
  }else throw failure(422,'invalid_request','The request must contain a JSON body.');
  try{return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(raw));}catch{throw failure(422,'invalid_request','The request must contain valid JSON.');}
}

function validateRequest(body,config){
  if(!body||typeof body!=='object'||Array.isArray(body)||Object.keys(body).some(key=>!['prompt','variant','max_new_tokens','request_id'].includes(key)))throw failure(422,'invalid_request','Expected prompt, variant, request_id and optional max_new_tokens only.');
  const prompt=typeof body.prompt==='string'?body.prompt.trim():'';
  if(!prompt||prompt.length>2400)throw failure(422,'invalid_prompt','Enter a problem containing 1 to 2400 characters.');
  if(body.variant!==config.variant)throw failure(422,'unsupported_variant','Choose the checkpoint variant advertised by this service.');
  if(typeof body.request_id!=='string'||!UUID.test(body.request_id))throw failure(422,'invalid_request_id','A UUID request_id is required. Do not retry a previously attempted request.');
  const cap=body.max_new_tokens??512;
  if(!Number.isInteger(cap)||cap<1||cap>512)throw failure(422,'invalid_token_limit','max_new_tokens must be an integer from 1 to 512.');
  return {prompt,max_new_tokens:cap,request_id:body.request_id.toLowerCase()};
}

async function responseJSON(response){
  if((response.headers.get('content-type')??'').split(';')[0].trim().toLowerCase()!=='application/json')throw failure(502,'invalid_backend_response','The inference backend returned an unsupported response.','unknown');
  const length=response.headers.get('content-length');
  if(length!==null&&(!/^\d+$/.test(length)||Number(length)>RESPONSE_LIMIT))throw failure(502,'invalid_backend_response','The inference backend returned an oversized response.','unknown');
  if(!response.body?.getReader)throw failure(502,'invalid_backend_response','The inference backend returned an empty response.','unknown');
  const reader=response.body.getReader(),parts=[];let size=0;
  try{while(true){const {value,done}=await reader.read();if(done)break;size+=value.byteLength;if(size>RESPONSE_LIMIT){await reader.cancel();throw failure(502,'invalid_backend_response','The inference backend returned an oversized response.','unknown');}parts.push(value);}}
  finally{reader.releaseLock();}
  try{return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(Buffer.concat(parts)));}catch{throw failure(502,'invalid_backend_response','The inference backend returned invalid JSON.','unknown');}
}

function upstreamFailure(status){
  if(status===429)return failure(429,'quota_exhausted','The inference trial cannot accept another request.','unknown');
  if(status===409)return failure(409,'request_already_attempted','This request was already attempted. It will not be dispatched again.','unknown');
  if(status===410)return failure(410,'trial_expired','The inference trial has ended.','unknown');
  if(status===422)return failure(422,'backend_rejected','The inference backend rejected this request.','unknown');
  return failure(status===503?503:502,'backend_unavailable','The inference backend is unavailable. No automatic retry was attempted.','unknown');
}

function assertIdentity(data,config,{model=false,requestId}={}){
  if(!data||typeof data!=='object'||Array.isArray(data)||data.checkpoint_id!==config.checkpoint||data.model!==MODEL||data.revision!==config.revision||(model&&Date.parse(data.expires_at_utc)!==config.expires)||(requestId&&data.request_id!==requestId))throw failure(502,'checkpoint_mismatch','The backend response does not match the configured checkpoint or request.','unknown');
  if(data.variant!==undefined&&data.variant!==config.variant)throw failure(502,'checkpoint_mismatch','The backend response does not match the configured variant.','unknown');
}
function publicMetadata(data,config){
  assertIdentity(data,config,{model:true});
  const measured=data.measured_accuracy,limits=data.limits;
  if(!measured||!Number.isInteger(measured.n)||measured.n<1||!Number.isInteger(measured.correct)||measured.correct<0||measured.correct>measured.n||!['development_monitoring','final_test'].includes(measured.split_role))throw failure(502,'invalid_backend_response','The backend model metadata is incomplete.');
  const maximums={max_requests:20,max_input_chars:2400,max_input_tokens:768,max_output_tokens:512,context_limit:2048};
  if(!limits||Object.entries(maximums).some(([key,max])=>!Number.isInteger(limits[key])||limits[key]<1||limits[key]>max)||limits.max_input_tokens+limits.max_output_tokens>limits.context_limit)throw failure(502,'invalid_backend_response','The backend limits differ from the bounded serving contract.');
  if(!Number.isInteger(data.requests_consumed)||data.requests_consumed<0||data.requests_consumed>limits.max_requests||data.status!==(data.requests_consumed===limits.max_requests?'quota_exhausted':'ready'))throw failure(502,'invalid_backend_response','The backend trial availability could not be verified.');
  let report;
  try{report=new URL(measured.report_url);if(report.origin!=='https://avisrikumeran.github.io'||!report.pathname.startsWith('/granite-query/')||report.username||report.password||[...report.searchParams].some(([key,value])=>key!=='report'||!/^[A-Za-z0-9_-]{1,80}$/.test(value))||!/^#?[A-Za-z0-9_-]*$/.test(report.hash))throw new Error();}catch{throw failure(502,'invalid_backend_response','The backend model report is not a supported public source.');}
  return {version:VERSION,service:SERVICE,status:data.status,model:MODEL,base_revision:config.revision,checkpoint_id:config.checkpoint,variant:config.variant,supported_variants:[config.variant],expires_at_utc:config.expiresISO,limits:Object.fromEntries(Object.keys(maximums).map(key=>[key,limits[key]])),requests_consumed:data.requests_consumed,requests_remaining:limits.max_requests-data.requests_consumed,measured_accuracy:{correct:measured.correct,n:measured.n,split_role:measured.split_role,report_url:report.href},checkpoint_improvement_established:false,note:'Interactive inference is not a benchmark or proof of improved accuracy. Failed or cancelled requests can consume the durable trial quota.'};
}
function publicGeneration(data,config,body){
  assertIdentity(data,config,{requestId:body.request_id});
  if(typeof data.response!=='string'||data.response.length>32768||data.response.includes(config.secret)||data.response.includes(config.key)||typeof data.truncated!=='boolean'||!Number.isInteger(data.generated_tokens)||data.generated_tokens<0||data.generated_tokens>body.max_new_tokens||!Number.isInteger(data.input_tokens)||data.input_tokens<1||data.input_tokens>768||!Number.isFinite(data.elapsed_seconds)||data.elapsed_seconds<0||data.elapsed_seconds>240)throw failure(502,'invalid_backend_response','The inference backend returned an invalid generation record.','unknown');
  return {version:VERSION,service:SERVICE,status:'completed',response:data.response,variant:config.variant,model:MODEL,base_revision:config.revision,checkpoint_id:config.checkpoint,request_id:body.request_id,input_tokens:data.input_tokens,generated_tokens:data.generated_tokens,truncated:data.truncated,elapsed_seconds:data.elapsed_seconds,settings:{enable_thinking:false,do_sample:false,max_new_tokens:body.max_new_tokens},limitations:'Interactive inference is not a benchmark or evidence of improved accuracy.'};
}

function send(res,status,payload,extra={}){
  res.statusCode=status;
  for(const [key,value] of Object.entries({'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Vary':'Origin',...extra}))res.setHeader(key,value);
  res.end(status===204?'':JSON.stringify(payload));
}

export function createInferenceGateway({env=process.env,fetchImpl=globalThis.fetch,now=()=>Date.now(),timeoutMs=85000}={}){
  if(!Number.isInteger(timeoutMs)||timeoutMs<1||timeoutMs>90000)throw new TypeError('Gateway timeout must be between 1 and 90000 milliseconds');
  async function upstream(route,config,body){
    const controller=new AbortController();let timer;
    const timeout=new Promise((_,reject)=>{timer=setTimeout(()=>{controller.abort();reject(failure(504,'upstream_timeout','The backend did not finish within the gateway deadline. Completion is unknown; do not automatically retry.','unknown'));},timeoutMs);});
    try{return await Promise.race([timeout,(async()=>{
      const response=await fetchImpl(new URL(route,config.endpoint),{method:body?'POST':'GET',headers:{Accept:'application/json','Modal-Key':config.key,'Modal-Secret':config.secret,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{}),signal:controller.signal,redirect:'manual',cache:'no-store'});
      if(!response.ok){void response.body?.cancel().catch(()=>{});throw upstreamFailure(response.status);}
      return responseJSON(response);
    })()]);}catch(error){if(error instanceof GatewayError)throw error;throw failure(502,'backend_unavailable','The inference backend could not be reached. Completion is unknown; no automatic retry was attempted.','unknown');}
    finally{clearTimeout(timer);}
  }
  function handler(route,method){return async(req,res)=>{
    if(req.method!==method&&req.method!=='OPTIONS')return send(res,405,{version:VERSION,service:SERVICE,status:'unavailable',error:{code:'method_not_allowed',message:'This route accepts '+method+' requests only.',retryable:false,completion:'not_started'}},{Allow:method+', OPTIONS'});
    try{
      const config=configuration(env,now);checkOrigin(req,config);
      if(req.method==='OPTIONS')return send(res,204,null,{Allow:method+', OPTIONS'});
      if(route==='model')return send(res,200,publicMetadata(await upstream('model',config),config));
      const body=validateRequest(await requestBody(req),config);
      return send(res,200,publicGeneration(await upstream('generate',config,body),config,body));
    }catch(error){const known=error instanceof GatewayError?error:failure(500,'gateway_error','The inference gateway could not complete this request.','unknown');return send(res,known.status,{version:VERSION,service:SERVICE,status:'unavailable',error:{code:known.code,message:known.message,retryable:false,completion:known.completion}});}
  };}
  return Object.freeze({model:handler('model','GET'),generate:handler('generate','POST')});
}
