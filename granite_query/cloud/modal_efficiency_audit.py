"""One inference-only A100 call. No adapter, optimizer, backward pass or training."""
import hashlib, json, os, random, time
from pathlib import Path
import modal
from cloud.modal_train import image,artifacts,state
from cloud import efficiency_audit as audit

app=modal.App('granite-query-inference-efficiency',include_source=False)

@app.function(image=image,gpu='A100-80GB',cpu=(4,4),memory=(32768,32768),timeout=2400,startup_timeout=120,
 retries=0,max_containers=1,min_containers=0,buffer_containers=0,scaledown_window=2,volumes={'/artifacts':artifacts})
def evaluate(plan:dict,rows:list,plan_sha256:str):
 started=time.monotonic();results=[];folder=Path('/artifacts')/plan['run_id'];folder.mkdir(exist_ok=True)
 if audit.digest(rows)!=plan['rows_sha256'] or plan['model']!=audit.MODEL or plan['revision']!=audit.REVISION:raise ValueError('Input/checkpoint mismatch')
 for name,sha in plan['source_code_sha256'].items():
  if audit.sha(Path(__file__).parent/name)!=sha:raise ValueError('Packaged source bytes differ')
 def checkpoint(stage):
  v={'stage':stage,'completed':len(results),'expected':len(plan['granite_cases']),'elapsed_seconds':round(time.monotonic()-started,3)}
  state[plan['run_id']]=v;(folder/'status.json').write_text(json.dumps(v));(folder/'results.json').write_text(json.dumps(results));artifacts.commit()
  print(json.dumps(v),flush=True)
 checkpoint('loading_model')
 import torch,importlib.metadata
 from transformers import AutoModelForCausalLM,AutoTokenizer,set_seed
 torch.set_num_threads(4)
 load=time.monotonic();tok=AutoTokenizer.from_pretrained(audit.MODEL,revision=audit.REVISION)
 model=AutoModelForCausalLM.from_pretrained(audit.MODEL,revision=audit.REVISION,torch_dtype=torch.bfloat16,attn_implementation='sdpa').to('cuda').eval()
 torch.cuda.synchronize();load_seconds=time.monotonic()-load
 rowmap={r['id']:r for r in rows}
 # Synthetic warmup, excluded from question scores and separately timed.
 warm=time.monotonic();warm_inputs=tok('Compute 2 + 2.',return_tensors='pt').to('cuda')
 with torch.inference_mode():model.generate(**warm_inputs,max_new_tokens=8,do_sample=False,pad_token_id=tok.eos_token_id)
 torch.cuda.synchronize();warmup_seconds=time.monotonic()-warm
 stage='completed'
 for c in plan['granite_cases']:
  if time.monotonic()-started>plan['granite_soft_stop_seconds']:
   stage='partial_time_guard';break
  row=rowmap[c['question_id']];request_start=time.monotonic()
  text=tok.apply_chat_template([{'role':'user','content':plan['prefix']+row['prompt']}],tokenize=False,add_generation_prompt=True,
   enable_thinking=c['mode']!='nonthinking',low_effort=c['mode']=='low')
  inputs=tok(text,add_special_tokens=False,return_tensors='pt').to('cuda')
  if inputs['input_ids'].shape[1]>1100:raise ValueError('Input bound')
  set_seed(c['seed']);torch.cuda.reset_peak_memory_stats();torch.cuda.synchronize();before=time.monotonic()
  with torch.inference_mode():
   out=model.generate(**inputs,max_new_tokens=c['cap'],do_sample=True,temperature=1.0,top_p=.95,use_cache=True,pad_token_id=tok.eos_token_id)
  torch.cuda.synchronize();generation=time.monotonic()-before
  ids=out[0,inputs['input_ids'].shape[1]:].tolist();raw=tok.decode(ids,skip_special_tokens=False)
  reasoning,content,closed=audit.split_response(raw,c['mode'])
  truncated=len(ids)>=c['cap'] and ids[-1]!=tok.eos_token_id
  r=dict(c,service='granite',model=audit.MODEL,revision=audit.REVISION,gold_answer=row['gold_answer'],
   generated_tokens=len(ids),output_ids=ids,prompt_tokens=inputs['input_ids'].shape[1],rendered_prompt_sha256=hashlib.sha256(text.encode()).hexdigest(),
   raw_output=raw,response=content,reasoning_content=reasoning,thinking_closed=closed,failed=False,
   finish_reason='length' if truncated else 'stop',truncated=truncated,generation_seconds=generation,
   elapsed_seconds=time.monotonic()-request_start,peak_gpu_allocated_bytes=torch.cuda.max_memory_allocated())
  from cloud.comparison_metrics import score
  r['scoring']=score(r);results.append(r);checkpoint('evaluating')
 answer={'run_id':plan['run_id'],'stage':stage,'plan_sha256':plan_sha256,'rows_sha256':plan['rows_sha256'],'results':results,
  'worker_elapsed_seconds':time.monotonic()-started,'load_seconds':load_seconds,'warmup_seconds':warmup_seconds,
  'completed':len(results),'expected':len(plan['granite_cases']),'gpu':torch.cuda.get_device_name(0),
  'packages':{n:importlib.metadata.version(n) for n in ['torch','transformers','safetensors']},'inference_only':True}
 (folder/'result.json').write_text(json.dumps(answer));checkpoint(stage);artifacts.commit();return answer

@app.local_entrypoint()
def launch():
 p,rows=audit.validate()
 with audit.lock(audit.STATE/'gpu_launch.lock'):
  if (audit.RUN/'dispatch_intent.json').exists():raise ValueError('Original dispatch intent exists; poll or reconcile, never spawn twice')
  import subprocess,sys
  apps=json.loads(subprocess.run([sys.executable,'-m','modal','app','list','--json'],capture_output=True,check=True,timeout=30).stdout)
  if any(not str(a.get('tasks','?')).isdigit() or int(a['tasks'])>0 for a in apps):raise ValueError('Another active GPU application exists')
  with audit.lock(audit.STATE/'budget_reconcile.lock'):
   ledger=audit.read(audit.STATE/'budget.json');job=audit.funding('modal',ledger)
   if any(j.get('service','modal')=='modal' and j['run_id']!=job['run_id'] and j.get('status') not in ('reserved','completed','failed','cancelled','superseded') for j in ledger['jobs']):raise ValueError('Another unsettled GPU dispatch exists')
   audit.write(audit.RUN/'dispatch_intent.json',{'plan_sha256':audit.sha(audit.RUN/'plan.json'),'started_at_utc':audit.now()},True)
   job['status']='spawning';audit.write(audit.STATE/'budget.json',ledger)
  call=evaluate.spawn(p,rows,audit.sha(audit.RUN/'plan.json'))
  receipt={'call_id':call.object_id,'run_id':p['run_id'],'plan_sha256':audit.sha(audit.RUN/'plan.json')}
  audit.write(audit.RUN/'launch.json',receipt,True)
  with audit.lock(audit.STATE/'budget_reconcile.lock'):
   ledger=audit.read(audit.STATE/'budget.json');job=next(j for j in ledger['jobs'] if j['run_id']==audit.jobid('modal'));job.update(status='spawned',call_id=call.object_id);audit.write(audit.STATE/'budget.json',ledger)
  print(json.dumps(receipt),flush=True)
