"""Inference-only, budgeted paired development audit. Never reads official test data."""
from contextlib import contextmanager
from datetime import datetime,timezone
from decimal import Decimal
import argparse, hashlib, json, math, os, random, statistics, sys, time, urllib.request, urllib.error
from pathlib import Path

ROOT=Path(__file__).resolve().parent
WORKSPACE=ROOT.parents[1]
RUN=ROOT/'runs/inference_efficiency32_modes_caps_v1'
STATE=ROOT/'runs/supervisor'
DEV=ROOT/'runs/human_math_cohort2048_dev200_v1/development.jsonl'
DEV_SHA='cccdce864d728e6b43d9d4de866e719bfd9c706cc735a3a3d429095835c767c7'
MODEL='ibm-granite/granite-4.2-3b'
REVISION='4e9c275e232f10211ec88644d106a1f6a1b60e06'
PREFIX='Solve the math problem. Explain only the necessary calculation steps concisely. Finish with #### followed by the numeric final answer.\n\n'
SEED=20261103
COUNT=32
CAPS=[512,2048]
GRANITE_MODES=['nonthinking','low','thinking']
DEEPSEEK_MODES=['nonthinking','low','high','max']
AMOUNTS={'modal':3.0,'deepseek':2.0}
SOURCES=['efficiency_audit.py','modal_efficiency_audit.py','comparison_metrics.py','modal_train.py']

def now():return datetime.now(timezone.utc).isoformat()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def digest(v):return hashlib.sha256(canonical(v).encode()).hexdigest()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,v,immutable=False):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);raw=(canonical(v)+'\n').encode()
 if immutable:
  try:
   with p.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
  except FileExistsError:
   if p.read_bytes()!=raw:raise ValueError('Immutable audit artifact differs')
 else:
  temp=p.with_name(p.name+f'.{os.getpid()}.tmp');temp.write_bytes(raw);temp.replace(p)

@contextmanager
def lock(p):
 fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
 try:os.write(fd,str(os.getpid()).encode());os.fsync(fd);yield
 finally:os.close(fd);Path(p).unlink()

def split_response(text,mode):
 if '</think>' in text:
  reasoning,content=text.split('</think>',1)
  return reasoning.replace('<think>','').strip(),content.replace('<|im_end|>','').strip(),True
 if mode!='nonthinking':return text.replace('<think>','').replace('<|im_end|>','').strip(),'',False
 return '',text.replace('<|im_end|>','').strip(),True

def payload(row,mode,cap):
 if mode not in DEEPSEEK_MODES or cap not in CAPS:raise ValueError('Unreviewed DeepSeek settings')
 v={'model':'deepseek-v4-pro','messages':[{'role':'user','content':PREFIX+row['prompt']}],
    'thinking':{'type':'disabled' if mode=='nonthinking' else 'enabled'},'max_tokens':cap,'stream':False}
 if mode=='nonthinking':v.update(temperature=1.0,top_p=.95)
 else:v['reasoning_effort']=mode
 return v

def cases(rows,modes,service):
 result=[]
 for row in rows:
  cells=[(mode,cap) for cap in CAPS for mode in modes]
  random.Random(SEED+int(row['id'].rsplit(':',1)[1])).shuffle(cells)
  for mode,cap in cells:
   result.append({'id':row['id']+'::'+mode+'::'+str(cap),'question_id':row['id'],'mode':mode,'cap':cap,
    'seed':int(hashlib.sha256((row['id']+'::'+mode).encode()).hexdigest()[:8],16),
    **({'payload_sha256':digest(payload(row,mode,cap))} if service=='deepseek' else {})})
 return result

def prepare():
 if sha(DEV)!=DEV_SHA:raise ValueError('Existing development source bytes changed')
 all_rows=[json.loads(x) for x in DEV.read_text(encoding='utf-8').split('\n') if x.strip()]
 if len(all_rows)!=200 or any(r.get('source_split')!='train' for r in all_rows):raise ValueError('Frozen TRAIN development cohort required')
 rows=sorted(all_rows,key=lambda r:r['id']);random.Random(SEED).shuffle(rows)
 rows=[{k:r[k] for k in ('id','prompt','gold_answer','source_split')} for r in rows[:COUNT]]
 from transformers import AutoTokenizer
 tok=AutoTokenizer.from_pretrained(str(WORKSPACE/'research/models/ibm-granite--granite-4.2-3b'),local_files_only=True)
 maximum=max(len(tok.encode(PREFIX+r['prompt'],add_special_tokens=False)) for r in rows)
 if maximum>1000 or max(len(canonical(payload(r,'max',2048)['messages']).encode()) for r in rows)>1800:
  raise ValueError('Prompt bound exceeds reviewed envelope')
 plan={'version':'inference-efficiency32-modes-caps-v1','run_id':RUN.name,'created_at_utc':now(),'model':MODEL,'revision':REVISION,
  'deepseek_alias':'deepseek-v4-pro','selection_seed':SEED,'question_count':COUNT,'source_sha256':DEV_SHA,'rows_sha256':digest(rows),
  'source_code_sha256':{n:sha(ROOT/n) for n in SOURCES},'prefix':PREFIX,'caps':CAPS,'granite_modes':GRANITE_MODES,
  'deepseek_modes':DEEPSEEK_MODES,'granite_cases':cases(rows,GRANITE_MODES,'modal'),'deepseek_cases':cases(rows,DEEPSEEK_MODES,'deepseek'),
  'inference_only':True,'official_test_used':False,'granite_temperature':1.0,'granite_top_p':.95,'granite_batch_size':1,
  'granite_max_worker_seconds':2400,'granite_soft_stop_seconds':2200,'automatic_retries':0,'deepseek_workers':1,'max_http_seconds':180,
  'deepseek_input_token_bound':2000,'deepseek_peak_input_rate_per_million':1.32,'deepseek_peak_output_rate_per_million':3.96,
  'deepseek_worst_token_cost_usd':float(Decimal(COUNT)*(8*2000*Decimal('1.32')+4*sum(CAPS)*Decimal('3.96'))/Decimal(1000000)),
  'reservations_usd':AMOUNTS,'protected_per_service_usd':5,
  'runtime_scope':'Granite warm batch-one GPU generation and server request times; DeepSeek serial HTTP round trips. Not equal hardware or compute. Mode names are native controls, not calibrated equal effort.',
  'sampling_scope':'One sampled response per question/cell. Granite per-question/mode seed shared across caps; DeepSeek exposes no controlled seed. Development only.'}
 if plan['deepseek_worst_token_cost_usd']>AMOUNTS['deepseek']:raise ValueError('DeepSeek worst case does not fit')
 if (RUN/'plan.json').exists():return validate()[0]
 write(RUN/'questions.json',rows,True);write(RUN/'plan.json',plan,True)
 return plan

def validate():
 p=read(RUN/'plan.json');rows=read(RUN/'questions.json')
 if p['rows_sha256']!=digest(rows) or p['source_code_sha256']!={n:sha(ROOT/n) for n in SOURCES}:raise ValueError('Frozen source or question bytes differ')
 if p['model']!=MODEL or p['revision']!=REVISION or p['caps']!=CAPS or len(rows)!=COUNT or not p['inference_only'] or p['official_test_used']:
  raise ValueError('Frozen inference scope differs')
 if p['granite_cases']!=cases(rows,GRANITE_MODES,'modal') or p['deepseek_cases']!=cases(rows,DEEPSEEK_MODES,'deepseek'):raise ValueError('Frozen cases differ')
 return p,rows

def jobid(service):return RUN.name+'-'+service
def funding(service,ledger=None):
 p,_=validate();ledger=ledger or read(STATE/'budget.json')
 from cloud.comparison_control import require_fresh_modal_budget
 from cloud.deepseek_reconcile import require_fresh_deepseek_budget
 if service=='modal':require_fresh_modal_budget(ledger,new_reservation=True)
 else:require_fresh_deepseek_budget(ledger,new_reservation=True)
 matches=[j for j in ledger['jobs'] if j['run_id']==jobid(service) and j.get('service')==service]
 if len(matches)!=1 or matches[0]['status'] not in ('reserved','spawning','spawned','running','collecting') or matches[0].get('audit_plan_sha256')!=sha(RUN/'plan.json') or matches[0]['reserved_usd']<AMOUNTS[service]:raise ValueError('Exact active audit reservation required')
 if ledger['limits'][service]-ledger['estimated_spend'][service]-ledger['reserved'][service]<5:raise ValueError('Protect remaining final/API funds')
 return matches[0]

def reserve():
 p,_=validate()
 from cloud.comparison_control import reserve as reserve_one
 for service in ('modal','deepseek'):
  reserve_one(service,AMOUNTS[service],jobid(service))
  with lock(STATE/'budget_reconcile.lock'):
   ledger=read(STATE/'budget.json');job=next(j for j in ledger['jobs'] if j['run_id']==jobid(service))
   if job.get('audit_plan_sha256',sha(RUN/'plan.json'))!=sha(RUN/'plan.json'):raise ValueError('Reservation previously bound differently')
   job['audit_plan_sha256']=sha(RUN/'plan.json');job['inference_only']=True
   if service=='modal':job.update(hard_cpu_cores=4,hard_memory_gib=32,timeout_seconds=2400)
   write(STATE/'budget.json',ledger);funding(service,ledger)
 write(RUN/'funding_review.json',{'plan_sha256':sha(RUN/'plan.json'),'reviewed_at_utc':now(),'amounts':AMOUNTS,'protected_usd_each':5},True)
 return {'reserved':AMOUNTS,'paid_calls_launched':False}

def attempt(c,row,key,p):
 folder=RUN/'deepseek_attempts';folder.mkdir(exist_ok=True)
 slug=hashlib.sha256(c['id'].encode()).hexdigest();intent=folder/(slug+'.intent.json');result=folder/(slug+'.result.json');wire=folder/(slug+'.wire.json')
 if intent.exists():
  if result.exists():return read(result)
  raise RuntimeError('Ambiguous original API transmission; never resend automatically')
 body=payload(row,c['mode'],c['cap']);assert digest(body)==c['payload_sha256']
 funding('deepseek');write(intent,{'case':c,'started_at_utc':now(),'plan_sha256':sha(RUN/'plan.json')},True)
 r=dict(c,service='deepseek',model=p['deepseek_alias'],gold_answer=row['gold_answer'],failed=False,generated_tokens=None,reasoning_tokens=None,response='',reasoning_content='',truncated=False)
 start=time.monotonic()
 try:
  req=urllib.request.Request('https://api.deepseek.com/chat/completions',data=canonical(body).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=p['max_http_seconds']) as response:raw=response.read(2*1024*1024+1)
  with wire.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
  r['wire_sha256']=hashlib.sha256(raw).hexdigest()
  if len(raw)>2*1024*1024:raise ValueError('Oversized response')
  v=json.loads(raw);choice=v['choices'][0];u=v['usage'];message=choice['message']
  if not isinstance(u.get('completion_tokens'),int) or not isinstance(u.get('prompt_tokens'),int):raise ValueError('Missing authoritative usage')
  if u['completion_tokens']>c['cap'] or u['prompt_tokens']>p['deepseek_input_token_bound']:raise ValueError('Usage beyond frozen bound')
  r.update(generated_tokens=u['completion_tokens'],prompt_tokens=u['prompt_tokens'],reasoning_tokens=u.get('completion_tokens_details',{}).get('reasoning_tokens'),
   usage=u,response=message.get('content') or '',reasoning_content=message.get('reasoning_content') or '',finish_reason=choice['finish_reason'],
   truncated=choice['finish_reason']=='length',returned_model=v.get('model'),system_fingerprint=v.get('system_fingerprint'))
  if choice['finish_reason'] not in ('stop','length'):r['failed']=True
 except Exception as exc:
  r.update(failed=True,error_type=type(exc).__name__)
  if isinstance(exc,urllib.error.HTTPError):r['http_status']=exc.code
 r['elapsed_seconds']=time.monotonic()-start
 from cloud.comparison_metrics import score
 r['scoring']=score(dict(r,truncated=r['truncated'] or r['failed']))
 write(result,r,True);return r

def collect():
 p,rows=validate()
 others=list((ROOT/'runs').rglob('collector.lock'))
 if others:raise RuntimeError('An existing collector owns API dispatch; wait for its owner')
 from cloud.run_api_pilot import credential
 key=credential('DEEPSEEK_API_KEY')
 if not key:raise RuntimeError('DeepSeek credential unavailable')
 rowmap={r['id']:r for r in rows};results=[]
 with lock(RUN/'collector.lock'):
  for c in p['deepseek_cases']:
   # Fresh read-only wallet observation before the funding gate expires.
   stamp=read(STATE/'budget.json')['deepseek_budget_accounting']['updated_at_utc']
   if (datetime.now(timezone.utc)-datetime.fromisoformat(stamp)).total_seconds()>600:
    import subprocess
    subprocess.run([sys.executable,'-m','cloud.deepseek_reconcile','--refresh'],cwd=ROOT.parent,check=True,stdout=subprocess.DEVNULL)
   r=attempt(c,rowmap[c['question_id']],key,p);results.append(r)
   write(RUN/'deepseek_results.json',results)
   print(canonical({'service':'deepseek','completed':len(results),'total':len(p['deepseek_cases']),'mode':r['mode'],'cap':r['cap'],'correct':r['scoring']['correct'],'tokens':r['generated_tokens'],'failed':r['failed']}),flush=True)
   if r['failed']:return {'stage':'halted_after_failed_or_unknown_request','completed':len(results)}
 return {'stage':'completed','completed':len(results)}

def settle(service,*,result=None):
 p,_=validate()
 with lock(STATE/'budget_reconcile.lock'):
  ledger=read(STATE/'budget.json');job=next(j for j in ledger['jobs'] if j['run_id']==jobid(service))
  if job['status'] in ('completed','failed'):return
  if service=='deepseek':
   rows=read(RUN/'deepseek_results.json')
   if len(rows)!=len(p['deepseek_cases']) or any(r['failed'] or r['generated_tokens'] is None for r in rows):raise ValueError('Incomplete usage keeps full reservation')
   cost=sum(Decimal(r['prompt_tokens'])*Decimal('1.32')+Decimal(r['generated_tokens'])*Decimal('3.96') for r in rows)/Decimal(1000000)
   job['accounted_upper_estimate_usd']=float(cost);job['status']='completed';job['finished_at_utc']=now()
   ledger['reserved'][service]=round(ledger['reserved'][service]-job['reserved_usd'],2)
  else:
   if not result or result.get('run_id')!=p['run_id']:raise ValueError('Provider result required')
   job.update(status='completed' if result['stage']=='completed' else 'failed',finished_at_utc=now(),worker_elapsed_seconds=result['worker_elapsed_seconds'])
   # Reservation stays on the terminal job for the billing-lag reconciler.
  write(STATE/'budget.json',ledger)

def poll():
 p,_=validate();launch=read(RUN/'launch.json')
 import modal
 try:r=modal.FunctionCall.from_id(launch['call_id']).get(timeout=0)
 except TimeoutError:
  status=modal.Dict.from_name('granite-query-training-progress').get(RUN.name,{})
  return dict(status,stage=status.get('stage','running'))
 write(RUN/'granite_provider_result.json',r,True)
 if r['plan_sha256']!=sha(RUN/'plan.json') or r['rows_sha256']!=p['rows_sha256']:raise ValueError('Provider identity mismatch')
 write(RUN/'granite_results.json',r['results'],True);settle('modal',result=r)
 return {k:r[k] for k in ['stage','worker_elapsed_seconds','completed','expected']}

def main():
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','reserve','collect','poll','settle-deepseek']);args=parser.parse_args()
 r=settle('deepseek') if args.action=='settle-deepseek' else globals()[args.action]()
 print(canonical(r),flush=True)

if __name__=='__main__':main()
