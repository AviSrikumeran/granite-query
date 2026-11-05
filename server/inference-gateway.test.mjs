import test from 'node:test';
import assert from 'node:assert/strict';
import {Readable} from 'node:stream';
import {createInferenceGateway,MODEL,REVISION,SERVICE} from './inference-gateway.mjs';

const NOW=Date.parse('2026-11-05T12:00:00.000Z');
const ENV={GRANITE_INFERENCE_ENABLED:'true',MODAL_INFERENCE_BASE_URL:'https://fixture.modal.run/private/base',MODAL_PROXY_TOKEN_ID:'wk-fixture-id',MODAL_PROXY_TOKEN_SECRET:'ws-fixture-private-secret',PUBLIC_SITE_ORIGIN:'https://granitequery.example',GRANITE_CHECKPOINT_ID:'correction-fixture',GRANITE_MODEL_REVISION:REVISION,GRANITE_CHECKPOINT_VARIANT:'correction',GRANITE_TRIAL_EXPIRES_AT_UTC:'2026-11-06T12:00:00.000Z',GRANITE_DURABLE_ADMISSION_CONFIRMED:'true',GRANITE_PROXY_AUTH_CONFIRMED:'true'};
const REQUEST={prompt:'How much is 2 + 2?',variant:'correction',max_new_tokens:256,request_id:'18f71629-de1e-4be0-9ca6-aed4b5a6b637'};
const METADATA={model:MODEL,revision:REVISION,checkpoint_id:ENV.GRANITE_CHECKPOINT_ID,variant:'correction',status:'ready',requests_consumed:0,expires_at_utc:ENV.GRANITE_TRIAL_EXPIRES_AT_UTC,measured_accuracy:{correct:28,n:32,split_role:'development_monitoring',report_url:'https://avisrikumeran.github.io/granite-query/research/?report=overnight'},limits:{max_requests:20,max_input_chars:2400,max_input_tokens:768,max_output_tokens:512,context_limit:2048},note:'Must not be copied blindly',private_path:'C:/private/backend/path'};
const GENERATION={model:MODEL,revision:REVISION,response:'2 + 2 = 4.\n#### 4',generated_tokens:12,input_tokens:36,truncated:false,elapsed_seconds:1.2,checkpoint_id:ENV.GRANITE_CHECKPOINT_ID,request_id:REQUEST.request_id,private_path:'C:/private/backend/path'};
const json=(body,status=200,headers={})=>new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json',...headers}});
function request(method='POST',body=REQUEST,headers={}){return {method,headers:{host:'granitequery.example',origin:ENV.PUBLIC_SITE_ORIGIN,'content-type':'application/json',...headers},body};}
async function invoke(handler,req){
  const res={headers:{},setHeader(name,value){this.headers[name]=value;},end(value){this.raw=value;}};
  await handler(req,res);return {status:res.statusCode,headers:res.headers,body:res.raw?JSON.parse(res.raw):null,raw:res.raw};
}
function fixture({env=ENV,response=()=>json(GENERATION),timeoutMs=1000}={}){
  const calls=[];const gateway=createInferenceGateway({env:{...env},now:()=>NOW,timeoutMs,fetchImpl:async(...args)=>{calls.push(args);return response(...args);}});
  return {gateway,calls};
}

test('disabled, incomplete, expired or unauthenticated configuration never dispatches',async()=>{
  for(const patch of [{GRANITE_INFERENCE_ENABLED:'false'},{MODAL_INFERENCE_BASE_URL:''},{GRANITE_CHECKPOINT_ID:''},{GRANITE_MODEL_REVISION:'0'.repeat(40)},{GRANITE_CHECKPOINT_VARIANT:''},{GRANITE_TRIAL_EXPIRES_AT_UTC:''},{GRANITE_DURABLE_ADMISSION_CONFIRMED:'false'},{GRANITE_PROXY_AUTH_CONFIRMED:'false'},{MODAL_PROXY_TOKEN_ID:'ak-workspace-token'},{MODAL_PROXY_TOKEN_SECRET:'as-workspace-secret'}]){
    const {gateway,calls}=fixture({env:{...ENV,...patch}});const result=await invoke(gateway.generate,request());
    assert.equal(result.status,503);assert.equal(result.body.error.code,'not_configured');assert.equal(calls.length,0);assert.equal(result.body.error.retryable,false);
  }
  const expired=fixture({env:{...ENV,GRANITE_TRIAL_EXPIRES_AT_UTC:'2026-11-04T12:00:00Z'}});assert.equal((await invoke(expired.gateway.generate,request())).status,410);assert.equal(expired.calls.length,0);
});
test('upstream URLs cannot contain credentials, query, fragments, encoded slashes or insecure transport',async()=>{
  for(const url of ['http://fixture.modal.run','https://user:password@fixture.modal.run','https://fixture.modal.run/?secret=x','https://fixture.modal.run/#fragment','https://fixture.modal.run/%2fhidden']){
    const {gateway,calls}=fixture({env:{...ENV,MODAL_INFERENCE_BASE_URL:url}});assert.equal((await invoke(gateway.generate,request())).status,503);assert.equal(calls.length,0);
  }
});
test('same-origin generation is required; cross-origin OPTIONS and absent POST origin cannot dispatch',async()=>{
  const {gateway,calls}=fixture();
  for(const req of [request('POST',REQUEST,{origin:'https://other.example'}),request('OPTIONS',undefined,{origin:'https://other.example'}),request('POST',REQUEST,{origin:'null'}),request('POST',REQUEST,{'sec-fetch-site':'cross-site'})])assert.equal((await invoke(gateway.generate,req)).status,403);
  const missing=request();delete missing.headers.origin;assert.equal((await invoke(gateway.generate,missing)).status,403);
  const option=await invoke(gateway.generate,request('OPTIONS',undefined));assert.equal(option.status,204);assert.equal(option.body,null);assert.equal(calls.length,0);assert.equal(option.headers['Access-Control-Allow-Origin'],undefined);
});
test('same-origin GET metadata works without browser Origin and exposes only reviewed fields',async()=>{
  const {gateway,calls}=fixture({response:()=>json(METADATA)});const req=request('GET');delete req.headers.origin;
  const result=await invoke(gateway.model,req);
  assert.equal(result.status,200);assert.equal(result.body.version,1);assert.equal(result.body.service,SERVICE);assert.equal(result.body.variant,'correction');assert.deepEqual(result.body.supported_variants,['correction']);assert.equal(result.body.checkpoint_improvement_established,false);assert.deepEqual(result.body.measured_accuracy,METADATA.measured_accuracy);
  assert.equal(result.body.private_path,undefined);assert.equal(result.raw.includes('C:/private'),false);assert.equal(result.raw.includes(ENV.MODAL_PROXY_TOKEN_SECRET),false);assert.equal(calls.length,1);assert.equal(calls[0][0].href,'https://fixture.modal.run/private/base/model');
  const bad=request('GET');delete bad.headers.origin;bad.headers.host='other.example';assert.equal((await invoke(gateway.model,bad)).status,403);
});
test('methods are bounded and never dispatch for unsupported verbs',async()=>{
  const {gateway,calls}=fixture();
  for(const [handler,method] of [[gateway.model,'POST'],[gateway.generate,'GET'],[gateway.generate,'DELETE'],[gateway.generate,'HEAD']]){const result=await invoke(handler,request(method));assert.equal(result.status,405);assert.equal(result.body.error.code,'method_not_allowed');assert.match(result.headers.Allow,/OPTIONS/);}
  assert.equal(calls.length,0);
});
test('invalid types, unknown keys, unsupported variants, UUIDs, lengths and token bounds fail before outbound calls',async()=>{
  const {gateway,calls}=fixture();
  const invalid=[null,[],{}, {...REQUEST,prompt:' '},{...REQUEST,prompt:'a'.repeat(2401)},{...REQUEST,prompt:3},{...REQUEST,variant:'base'},{...REQUEST,request_id:'not-uuid'},{...REQUEST,request_id:null},{...REQUEST,max_new_tokens:0},{...REQUEST,max_new_tokens:513},{...REQUEST,max_new_tokens:1.2},{...REQUEST,max_new_tokens:'256'},{...REQUEST,endpoint:'https://other.example'},{...REQUEST,secret:ENV.MODAL_PROXY_TOKEN_SECRET}];
  for(const body of invalid){const result=await invoke(gateway.generate,request('POST',body));assert.equal(result.status,422);assert.equal(result.body.error.completion,'not_started');}
  assert.equal(calls.length,0);
});
test('JSON media type, request byte limits and malformed UTF-8/JSON are enforced',async()=>{
  const {gateway,calls}=fixture();
  assert.equal((await invoke(gateway.generate,request('POST',REQUEST,{'content-type':'text/plain'}))).status,415);
  assert.equal((await invoke(gateway.generate,request('POST',REQUEST,{'content-encoding':'gzip'}))).status,415);
  assert.equal((await invoke(gateway.generate,request('POST',REQUEST,{'content-length':'16385'}))).status,413);
  assert.equal((await invoke(gateway.generate,request('POST',' '.repeat(16385)))).status,413);
  assert.equal((await invoke(gateway.generate,request('POST','{invalid}'))).status,422);
  assert.equal((await invoke(gateway.generate,request('POST',Buffer.from([255])))).status,422);
  const stream=Readable.from([Buffer.alloc(9000),Buffer.alloc(9000)]);stream.method='POST';stream.headers=request().headers;
  assert.equal((await invoke(gateway.generate,stream)).status,413);assert.equal(calls.length,0);
});
test('a malformed-body getter is read once and rejected before inference dispatch',async()=>{
  const {gateway,calls}=fixture();const req=request();let reads=0;
  Object.defineProperty(req,'body',{get(){reads++;throw new SyntaxError('private malformed parser detail');}});
  const result=await invoke(gateway.generate,req);assert.equal(result.status,422);assert.equal(result.body.error.code,'invalid_request');assert.equal(result.body.error.completion,'not_started');assert.equal(reads,1);assert.equal(calls.length,0);assert.equal(result.raw.includes('private malformed'),false);
});
test('valid request is trimmed, forwarded once with private proxy headers, and variant is never sent as an unsupported backend field',async()=>{
  const {gateway,calls}=fixture();const result=await invoke(gateway.generate,request('POST',{...REQUEST,prompt:'  2 + 2?  '}));
  assert.equal(result.status,200);assert.equal(result.body.response,GENERATION.response);assert.equal(result.body.variant,'correction');assert.equal(result.body.request_id,REQUEST.request_id);assert.equal(result.body.private_path,undefined);
  assert.equal(calls.length,1);const [url,options]=calls[0];assert.equal(url.href,'https://fixture.modal.run/private/base/generate');assert.equal(options.headers['Modal-Key'],ENV.MODAL_PROXY_TOKEN_ID);assert.equal(options.headers['Modal-Secret'],ENV.MODAL_PROXY_TOKEN_SECRET);assert.equal(options.redirect,'manual');assert.equal(options.cache,'no-store');assert.deepEqual(JSON.parse(options.body),{prompt:'2 + 2?',max_new_tokens:256,request_id:REQUEST.request_id});
  assert.equal(result.raw.includes(ENV.MODAL_PROXY_TOKEN_SECRET),false);assert.equal(result.raw.includes(ENV.MODAL_PROXY_TOKEN_ID),false);assert.equal(result.headers['Cache-Control'],'no-store');assert.equal(result.headers['X-Content-Type-Options'],'nosniff');
});
test('raw stream requests and both output-token boundaries are accepted',async()=>{
  for(const cap of [1,512]){
    const {gateway}=fixture({response:()=>json({...GENERATION,generated_tokens:cap})});const stream=Readable.from([JSON.stringify({...REQUEST,max_new_tokens:cap})]);stream.method='POST';stream.headers=request().headers;
    assert.equal((await invoke(gateway.generate,stream)).status,200);
  }
});
test('backend checkpoint, request, variant, revision and expiry mismatches fail closed',async()=>{
  for(const patch of [{checkpoint_id:'other'},{request_id:'00000000-0000-0000-0000-000000000000'},{variant:'base'},{model:'other-model'},{revision:'0'.repeat(40)},{model:undefined},{revision:undefined}]){
    const {gateway}=fixture({response:()=>json({...GENERATION,...patch})});const result=await invoke(gateway.generate,request());assert.equal(result.status,502);assert.equal(result.body.error.code,'checkpoint_mismatch');assert.equal(result.body.response,undefined);
  }
  for(const patch of [{checkpoint_id:'other'},{revision:'0'.repeat(40)},{model:'other-model'},{expires_at_utc:'2026-11-07T12:00:00Z'},{variant:'base'}]){
    const {gateway}=fixture({response:()=>json({...METADATA,...patch})});assert.equal((await invoke(gateway.model,request('GET'))).body.error.code,'checkpoint_mismatch');
  }
});
test('metadata reports exhausted quota and rejects inconsistent or unknown availability',async()=>{
  const {gateway}=fixture({response:()=>json({...METADATA,status:'quota_exhausted',requests_consumed:20})});
  const result=await invoke(gateway.model,request('GET'));assert.equal(result.status,200);assert.equal(result.body.status,'quota_exhausted');assert.equal(result.body.requests_consumed,20);assert.equal(result.body.requests_remaining,0);
  const available=fixture({response:()=>json({...METADATA,requests_consumed:7})});const ready=await invoke(available.gateway.model,request('GET'));assert.equal(ready.body.status,'ready');assert.equal(ready.body.requests_remaining,13);
  for(const patch of [{requests_consumed:20,status:'ready'},{requests_consumed:19,status:'quota_exhausted'},{requests_consumed:-1},{requests_consumed:21},{requests_consumed:0.5},{requests_consumed:undefined},{status:undefined},{status:'unknown'}]){
    const bad=fixture({response:()=>json({...METADATA,...patch})});const denied=await invoke(bad.gateway.model,request('GET'));assert.equal(denied.status,502);assert.equal(denied.body.error.code,'invalid_backend_response');assert.equal(denied.body.status,'unavailable');
  }
});
test('metadata constraints and generation counters are validated rather than trusted',async()=>{
  for(const patch of [{generated_tokens:257},{input_tokens:769},{elapsed_seconds:-1},{truncated:'false'},{response:ENV.MODAL_PROXY_TOKEN_SECRET}]){
    const {gateway}=fixture({response:()=>json({...GENERATION,...patch})});assert.equal((await invoke(gateway.generate,request())).body.error.code,'invalid_backend_response');
  }
  for(const patch of [{limits:{...METADATA.limits,max_output_tokens:4096}},{measured_accuracy:{...METADATA.measured_accuracy,correct:33}},{measured_accuracy:{...METADATA.measured_accuracy,report_url:'https://private.example/config?secret=hidden'}}]){
    const {gateway}=fixture({response:()=>json({...METADATA,...patch})});assert.equal((await invoke(gateway.model,request('GET'))).status,502);
  }
});
test('upstream errors are normalized without leaking remote messages, paths, secrets or retry instructions',async()=>{
  const expected={401:'backend_unavailable',403:'backend_unavailable',409:'request_already_attempted',410:'trial_expired',422:'backend_rejected',429:'quota_exhausted',500:'backend_unavailable',503:'backend_unavailable'};
  for(const [status,code] of Object.entries(expected)){
    const {gateway,calls}=fixture({response:()=>json({detail:'C:/private '+ENV.MODAL_PROXY_TOKEN_SECRET},Number(status))});const result=await invoke(gateway.generate,request());
    assert.equal(result.body.error.code,code);assert.equal(result.body.error.retryable,false);assert.equal(result.body.error.completion,'unknown');assert.equal(result.raw.includes('C:/private'),false);assert.equal(result.raw.includes(ENV.MODAL_PROXY_TOKEN_SECRET),false);assert.equal(calls.length,1);
  }
});
test('HTML, malformed JSON, oversized responses and redirects are not passed through',async()=>{
  const responses=[()=>new Response('<script>secret()</script>',{headers:{'content-type':'text/html'}}),()=>new Response('{broken',{headers:{'content-type':'application/json'}}),()=>json({response:'a'.repeat(65537)}),()=>json(GENERATION,200,{'content-length':'65537'}),()=>new Response(null,{status:307,headers:{Location:'https://elsewhere.example'}})];
  for(const response of responses){const {gateway,calls}=fixture({response});const result=await invoke(gateway.generate,request());assert.equal(result.status,502);assert.equal(result.body.response,undefined);assert.equal(result.raw.includes('<script>'),false);assert.equal(calls.length,1);}
});
test('timeout aborts once, does not retry, and marks completion unknown',async()=>{
  let signal;const {gateway,calls}=fixture({timeoutMs:5,response:(_url,options)=>{signal=options.signal;return new Promise(()=>{});}});
  const result=await invoke(gateway.generate,request());assert.equal(result.status,504);assert.equal(result.body.error.code,'upstream_timeout');assert.equal(result.body.error.completion,'unknown');assert.equal(result.body.error.retryable,false);assert.equal(signal.aborted,true);assert.equal(calls.length,1);
});
test('cold-start deadline configuration is bounded independently of execution latency',()=>{
  for(const timeoutMs of [0,-1,1.5,200001,Infinity])assert.throws(()=>createInferenceGateway({env:{},timeoutMs}),/between 1 and 200000/);
  for(const timeoutMs of [170000,200000])assert.doesNotThrow(()=>createInferenceGateway({env:{},timeoutMs}));
});
test('connection failures never expose exception details or retry',async()=>{
  const {gateway,calls}=fixture({response:()=>{throw new Error(ENV.MODAL_PROXY_TOKEN_SECRET+' /private/path');}});const result=await invoke(gateway.generate,request());assert.equal(result.status,502);assert.equal(result.body.error.completion,'unknown');assert.equal(result.raw.includes(ENV.MODAL_PROXY_TOKEN_SECRET),false);assert.equal(calls.length,1);
});
