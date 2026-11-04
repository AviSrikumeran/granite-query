"""At most one bounded continuation for never-attempted Granite audit cases.

Uses the original $3 envelope: $2.10 retained for the first call, $0.90 for
the continuation. Completed generations are never repeated or selected by score.
"""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
import modal
from cloud import efficiency_audit as a
from cloud.modal_train import image,artifacts,state
from cloud.modal_efficiency_audit import evaluate

CHILD=a.RUN/'remaining'
JOB=a.RUN.name+'-modal-remaining-v1'
RUN_ID=a.RUN.name+'-remaining-v1'
THIS=Path(__file__).name
app=modal.App('granite-query-inference-efficiency-remaining',include_source=False)

def missing_cases(plan,original):
 expected={c['id']:c for c in plan['granite_cases']};seen=set()
 for r in original['results']:
  if r['id'] in seen or r['id'] not in expected:raise ValueError('Original outcome identity differs')
  c=expected[r['id']]
  if any(r[k]!=c[k] for k in ('question_id','mode','cap','seed')):raise ValueError('Original case changed')
  seen.add(r['id'])
 return [c for c in plan['granite_cases'] if c['id'] not in seen]

def prepare():
 plan,rows=a.validate();original=a.read(a.RUN/'granite_provider_result.json')
 if original['plan_sha256']!=a.sha(a.RUN/'plan.json') or original['stage']!='partial_time_guard':raise ValueError('A preserved time-guard partial is required')
 missing=missing_cases(plan,original)
 if not 1<=len(missing)<=32:raise ValueError('Recovery limited to at most 32 never-attempted cases')
 p=dict(plan,run_id=RUN_ID,version=plan['version']+'-remaining-v1',granite_cases=missing,
  granite_soft_stop_seconds=720,granite_max_worker_seconds=900,
  recovery_parent_plan_sha256=a.sha(a.RUN/'plan.json'),recovery_parent_result_sha256=a.sha(a.RUN/'granite_provider_result.json'))
 p['source_code_sha256']=dict(plan['source_code_sha256'],**{THIS:a.sha(Path(__file__))})
 a.write(CHILD/'plan.json',p,True)
 review={'parent_plan_sha256':a.sha(a.RUN/'plan.json'),'parent_result_sha256':a.sha(a.RUN/'granite_provider_result.json'),
  'remaining_plan_sha256':a.sha(CHILD/'plan.json'),'remaining_cases':len(missing),'no_completed_generation_repeated':True,
  'first_call_retained_usd':2.1,'remaining_call_reserved_usd':.9,'combined_original_envelope_usd':3.0,
  'rate_bound_per_second':.00081812,
  'verified_workspace_hourly_rates':{'a100_80gb':'2.50000','cpu_core':'0.04730','memory_gib':'0.00800'},
  'combined_timeout_startup_scaledown_seconds':2400+120+2+900+120+2,
  'misc_allowance_usd':.1,'reviewed_at_utc':a.now()}
 review['combined_resource_bound_plus_misc_usd']=review['rate_bound_per_second']*review['combined_timeout_startup_scaledown_seconds']+.1
 if review['combined_resource_bound_plus_misc_usd']>3:raise ValueError('Combined calls do not fit original envelope')
 if (CHILD/'review.json').exists():
  prior=a.read(CHILD/'review.json')
  if any(prior[k]!=v for k,v in review.items() if k!='reviewed_at_utc'):raise ValueError('Recovery review changed')
 else:a.write(CHILD/'review.json',review,True)
 return p,rows

@app.function(image=image,gpu='A100-80GB',cpu=(4,4),memory=(32768,32768),timeout=900,startup_timeout=120,
 retries=0,max_containers=1,min_containers=0,buffer_containers=0,scaledown_window=2,volumes={'/artifacts':artifacts})
def remaining(p:dict,rows:list,plan_sha:str):
 actual=__import__('hashlib').sha256((a.canonical(p)+'\n').encode()).hexdigest()
 if actual!=plan_sha or p['run_id']!=RUN_ID or p['granite_soft_stop_seconds']!=720 or len(p['granite_cases'])>32:raise ValueError('Bounded remaining plan differs')
 return evaluate.local(p,rows,plan_sha)

@app.local_entrypoint()
def launch():
 with a.lock(a.STATE/'gpu_launch.lock'):
  if (CHILD/'dispatch_intent.json').exists():raise ValueError('Existing recovery intent must be polled, never repeated')
  p,rows=prepare()
  rates=modal.Workspace.from_context().billing.rates()
  rate=(rates['gpu_hour_cost_a100_80gb']+4*rates['cpu_hour_cost']+32*rates['mem_gib_hour_cost'])/3600
  if rate>__import__('decimal').Decimal('.00081812'):raise ValueError('Current workspace rates exceed reviewed original-envelope bound')
  a.write(CHILD/'resource_rates.json',{'source':'Supported Workspace.billing.rates()',
   'hourly':{k:str(rates[k]) for k in ['gpu_hour_cost_a100_80gb','cpu_hour_cost','mem_gib_hour_cost']}},True)
  with a.lock(a.STATE/'budget_reconcile.lock'):
   ledger=a.read(a.STATE/'budget.json');parent=next(j for j in ledger['jobs'] if j['run_id']==a.jobid('modal'))
   child=next((j for j in ledger['jobs'] if j['run_id']==JOB),None)
   if child is None:
    if parent['status'] not in ('completed','failed') or parent['reserved_usd']!=3.0:raise ValueError('Original owned envelope is not terminal and intact')
    parent.update(original_reservation_usd=3.0,reserved_usd=2.1,recovery_transfer_usd=.9)
    child={'run_id':JOB,'service':'modal','status':'queued','reserved_usd':.9,'created_at_utc':a.now(),
     'audit_plan_sha256':a.sha(CHILD/'plan.json'),'original_audit_envelope':a.jobid('modal'),'hard_cpu_cores':4,'hard_memory_gib':32,'timeout_seconds':900}
    ledger['jobs'].append(child);a.write(a.STATE/'budget.json',ledger)
   if child['audit_plan_sha256']!=a.sha(CHILD/'plan.json') or child['reserved_usd']!=.9 or child['status']!='queued':raise ValueError('Existing continuation reservation differs')
   from cloud.comparison_control import require_fresh_modal_budget
   require_fresh_modal_budget(ledger,new_reservation=True)
   free=ledger['limits']['modal']-ledger['estimated_spend']['modal']-ledger['reserved']['modal']
   if free<5:
    print(json.dumps({'stage':'queued_waiting_for_billing_collection','free_after_liabilities_usd':free,'new_paid_call_launched':False}));return
   if any(j.get('service','modal')=='modal' and j['run_id']!=JOB and j.get('status') not in ('reserved','completed','failed','cancelled','superseded') for j in ledger['jobs']):raise ValueError('Another GPU dispatch owns the queue')
  apps=json.loads(subprocess.run([sys.executable,'-m','modal','app','list','--json'],capture_output=True,check=True,timeout=30).stdout)
  if any(not str(v.get('tasks','?')).isdigit() or int(v['tasks'])>0 for v in apps):raise ValueError('Another GPU application is active')
  with a.lock(a.STATE/'budget_reconcile.lock'):
   ledger=a.read(a.STATE/'budget.json');child=next(j for j in ledger['jobs'] if j['run_id']==JOB)
   child['status']='spawning';a.write(CHILD/'dispatch_intent.json',{'plan_sha256':a.sha(CHILD/'plan.json'),'started_at_utc':a.now()},True);a.write(a.STATE/'budget.json',ledger)
  call=remaining.spawn(p,rows,a.sha(CHILD/'plan.json'))
  receipt={'call_id':call.object_id,'run_id':RUN_ID,'plan_sha256':a.sha(CHILD/'plan.json')};a.write(CHILD/'launch.json',receipt,True)
  with a.lock(a.STATE/'budget_reconcile.lock'):
   ledger=a.read(a.STATE/'budget.json');child=next(j for j in ledger['jobs'] if j['run_id']==JOB);child.update(status='spawned',call_id=call.object_id);a.write(a.STATE/'budget.json',ledger)
  print(json.dumps(receipt),flush=True)

def poll():
 launch=a.read(CHILD/'launch.json')
 try:r=modal.FunctionCall.from_id(launch['call_id']).get(timeout=0)
 except TimeoutError:return state.get(RUN_ID,{'stage':'running'})
 a.write(CHILD/'provider_result.json',r,True);p=a.read(CHILD/'plan.json')
 if r['plan_sha256']!=a.sha(CHILD/'plan.json') or r['rows_sha256']!=p['rows_sha256']:raise ValueError('Remaining provider result identity differs')
 parent=a.read(a.RUN/'granite_provider_result.json');combined=parent['results']+r['results']
 original,_=a.validate();seen=[v['id'] for v in combined]
 if len(seen)!=len(set(seen)):raise ValueError('A generation was repeated')
 if r['stage']!='completed' or set(seen)!={v['id'] for v in original['granite_cases']}:raise ValueError('Remaining call incomplete; preserve all artifacts without an automatic retry')
 a.write(a.RUN/'granite_completed_results.json',combined,True)
 proof={'derivative_only':True,'provider_calls':[a.read(a.RUN/'launch.json')['call_id'],launch['call_id']],
  'parent_result_sha256':a.sha(a.RUN/'granite_provider_result.json'),'continuation_result_sha256':a.sha(CHILD/'provider_result.json'),
  'combined_results_sha256':a.sha(a.RUN/'granite_completed_results.json'),'unique_original_cases':len(seen)}
 a.write(a.RUN/'granite_composition.json',proof,True)
 with a.lock(a.STATE/'budget_reconcile.lock'):
  ledger=a.read(a.STATE/'budget.json');job=next(j for j in ledger['jobs'] if j['run_id']==JOB)
  job.update(status='completed',finished_at_utc=a.now(),worker_elapsed_seconds=r['worker_elapsed_seconds']);a.write(a.STATE/'budget.json',ledger)
 return {'stage':'all_192_granite_cases_completed','combined_cases':len(seen),'remaining_worker_seconds':r['worker_elapsed_seconds']}

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','poll']);arg=parser.parse_args()
 value=prepare()[0] if arg.action=='prepare' else poll()
 print(json.dumps(value))
