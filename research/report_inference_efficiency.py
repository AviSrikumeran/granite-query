"""Validate paired inference receipts and publish aggregate, prompt-free evidence."""
from collections import Counter
from datetime import datetime,timezone
import hashlib,html,json,math,statistics,sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'granite_query'))
from cloud import efficiency_audit as a
from cloud.comparison_metrics import score

def wilson(k,n):
 z=1.95996398454;p=k/n;denom=1+z*z/n
 mid=(p+z*z/(2*n))/denom;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/denom
 return [100*(mid-half),100*(mid+half)]

def summarize(rows,service,mode,cap):
 k=sum(r['scoring']['correct'] for r in rows);known=[r['generated_tokens'] for r in rows if r.get('generated_tokens') is not None]
 times=[r['elapsed_seconds'] for r in rows];n=len(rows)
 return {'service':service,'mode':mode,'cap':cap,'completed_attempts':n,'target_questions':32,'complete_cell':n==32,
  'correct':k,'accuracy_percent':100*k/n if n else None,'accuracy_wilson95_percent':wilson(k,n) if n else None,
  'total_output_tokens':sum(known),'output_usage_complete':len(known)==n,'mean_output_tokens':sum(known)/len(known) if known else None,
  'tokens_per_correct':sum(known)/k if k and len(known)==n else None,
  'tokens_on_incorrect_answers':sum(r.get('generated_tokens') or 0 for r in rows if not r['scoring']['correct']),
  'total_output_text_utf8_bytes':sum(len((r['reasoning_content']+r['response']).encode('utf-8')) for r in rows),
  'reasoning_tokens':sum(r['reasoning_tokens'] for r in rows if r.get('reasoning_tokens') is not None) if all(r.get('reasoning_tokens') is not None for r in rows) and rows else None,
  'truncated':sum(r['truncated'] for r in rows),'failed':sum(r['failed'] for r in rows),
  'total_request_seconds':sum(times),'mean_request_seconds':statistics.mean(times) if times else None,
  'median_request_seconds':statistics.median(times) if times else None,'p95_request_seconds':float(np.percentile(times,95)) if times else None,
  'total_generation_seconds':sum(r.get('generation_seconds',0) for r in rows) if service=='granite' else None,
  'returned_models':dict(Counter(r.get('returned_model',r.get('model')) for r in rows)),
  'outcomes':[{'question_id':r['question_id'],'correct':r['scoring']['correct'],'tokens':r.get('generated_tokens'),
    'elapsed_seconds':r['elapsed_seconds'],'truncated':r['truncated'],'failed':r['failed']} for r in rows]}

def paired(left,right,label):
 l={r['question_id']:r for r in left};r={r['question_id']:r for r in right};ids=sorted(l.keys()&r.keys())
 deltas=np.array([int(r[i]['scoring']['correct'])-int(l[i]['scoring']['correct']) for i in ids])
 if not len(ids):return None
 rng=np.random.default_rng(20261103);boot=rng.choice(deltas,size=(10000,len(ids)),replace=True).mean(axis=1)*100
 known=all(l[i].get('generated_tokens') is not None and r[i].get('generated_tokens') is not None for i in ids)
 return {'label':label,'paired_questions':len(ids),'accuracy_change_pp':float(deltas.mean()*100),
  'paired_bootstrap95_pp':[float(x) for x in np.percentile(boot,[2.5,97.5])],
  'corrected':int((deltas==1).sum()),'regressed':int((deltas==-1).sum()),
  'total_extra_tokens':sum(r[i]['generated_tokens']-l[i]['generated_tokens'] for i in ids) if known else None,
  'total_extra_request_seconds':sum(r[i]['elapsed_seconds']-l[i]['elapsed_seconds'] for i in ids)}

def build():
 plan,questions=a.validate();data={}
 for service,file in [('granite','granite_results.json'),('deepseek','deepseek_results.json')]:
  if service=='granite' and (a.RUN/'granite_completed_results.json').exists():
   proof=a.read(a.RUN/'granite_composition.json')
   for path,key in [('granite_completed_results.json','combined_results_sha256'),('granite_provider_result.json','parent_result_sha256'),('remaining/provider_result.json','continuation_result_sha256')]:
    if a.sha(a.RUN/path)!=proof[key]:raise ValueError('Derived Granite composition proof differs')
   if proof.get('derivative_only') is not True:raise ValueError('Composition must not claim to be a provider terminal')
   file='granite_completed_results.json'
  p=a.RUN/file
  data[service]=a.read(p) if p.exists() else []
  expected={c['id']:c for c in plan['granite_cases' if service=='granite' else 'deepseek_cases']}
  q={r['id']:r for r in questions};seen=set()
  for r in data[service]:
   if r['id'] in seen or r['id'] not in expected:raise ValueError('Unexpected or duplicate outcome')
   seen.add(r['id']);case=expected[r['id']]
   if any(r[k]!=case[k] for k in ['question_id','mode','cap']):raise ValueError('Case metadata differs')
   if service=='granite' and r['seed']!=case['seed']:raise ValueError('Granite sampling seed differs')
   if r['gold_answer']!=q[r['question_id']]['gold_answer']:raise ValueError('Reference differs')
   if r['scoring']!=score(dict(r,truncated=r['truncated'] or r['failed'])):raise ValueError('Numeric score differs')
   if service=='granite' and (len(r['output_ids'])!=r['generated_tokens'] or len(r['output_ids'])>r['cap']):raise ValueError('Raw output-token count differs')
   if service=='deepseek':
    slug=hashlib.sha256(r['id'].encode()).hexdigest();folder=a.RUN/'deepseek_attempts'
    intent=a.read(folder/(slug+'.intent.json'))
    if intent['case']!=case or intent['plan_sha256']!=a.sha(a.RUN/'plan.json'):raise ValueError('Original API intent differs')
    if not r['failed']:
     wire=(folder/(slug+'.wire.json')).read_bytes()
     if hashlib.sha256(wire).hexdigest()!=r['wire_sha256']:raise ValueError('API wire bytes differ')
     raw=json.loads(wire);choice=raw['choices'][0];usage=raw['usage']
     if (usage!=r['usage'] or usage['completion_tokens']!=r['generated_tokens'] or (choice['message'].get('content') or '')!=r['response']
         or (choice['message'].get('reasoning_content') or '')!=r['reasoning_content'] or choice['finish_reason']!=r['finish_reason']):raise ValueError('Derived API receipt differs from original wire')
 cells=[];comparisons=[]
 for service,modes in [('granite',a.GRANITE_MODES),('deepseek',a.DEEPSEEK_MODES)]:
  for cap in a.CAPS:
   baseline=[r for r in data[service] if r['mode']=='nonthinking' and r['cap']==cap]
   for mode in modes:
    rows=[r for r in data[service] if r['mode']==mode and r['cap']==cap]
    cells.append(summarize(rows,service,mode,cap))
    if mode!='nonthinking' and len(rows)==len(baseline)==32:comparisons.append(paired(baseline,rows,f'{service} {mode} minus nonthinking at cap {cap}'))
  for mode in modes:
   small=[r for r in data[service] if r['mode']==mode and r['cap']==512]
   large=[r for r in data[service] if r['mode']==mode and r['cap']==2048]
   if len(small)==len(large)==32:comparisons.append(paired(small,large,f'{service} cap 2048 minus 512 in {mode}'))
 for cap in a.CAPS:
  left=[r for r in data['granite'] if r['mode']=='nonthinking' and r['cap']==cap]
  right=[r for r in data['deepseek'] if r['mode']=='nonthinking' and r['cap']==cap]
  if len(left)==len(right)==32:comparisons.append(paired(left,right,f'deepseek nonthinking minus granite nonthinking at cap {cap}'))
 complete=len(data['granite'])==192 and len(data['deepseek'])==256
 prefix_checks=[]
 for mode in a.GRANITE_MODES:
  small={r['question_id']:r for r in data['granite'] if r['mode']==mode and r['cap']==512}
  large={r['question_id']:r for r in data['granite'] if r['mode']==mode and r['cap']==2048}
  ids=sorted(small.keys()&large.keys())
  prefix_checks.append({'mode':mode,'paired_questions':len(ids),
   'identical_generated_prefixes':sum(small[i]['output_ids']==large[i]['output_ids'][:len(small[i]['output_ids'])] for i in ids),
   'short_cap_truncations_corrected_by_large_cap':sum(small[i]['truncated'] and large[i]['scoring']['correct'] for i in ids)})
 provider=a.read(a.RUN/'granite_provider_result.json') if (a.RUN/'granite_provider_result.json').exists() else None
 worker_summary={k:provider[k] for k in ['stage','gpu','packages','worker_elapsed_seconds','load_seconds','warmup_seconds']} if provider else None
 if provider:
  worker_summary['actual_provider_calls']=1
  if (a.RUN/'granite_composition.json').exists():
   continuation=a.read(a.RUN/'remaining/provider_result.json')
   if continuation['packages']!=provider['packages']:raise ValueError('Granite runtime package versions changed between calls')
   worker_summary.update(stage='derived_complete_across_two_provider_calls',actual_provider_calls=2)
   for k in ['worker_elapsed_seconds','load_seconds','warmup_seconds']:worker_summary[k]+=continuation[k]
   worker_summary['gpu']=', '.join(sorted({provider['gpu'],continuation['gpu']}))
 reference_audit=json.loads((ROOT/'progress/INFERENCE_REFERENCE_AUDIT.json').read_text())
 error_audit=json.loads((ROOT/'progress/INFERENCE_ERROR_AUDIT.json').read_text())
 result={'schema_version':1,'run_id':plan['run_id'],'stage':'completed' if complete else 'partial','generated_at_utc':datetime.now(timezone.utc).isoformat(),
  'priority':'high','inference_only':True,'official_test_used':False,'question_count':32,'selection_seed':a.SEED,
  'source_development_sha256':plan['source_sha256'],'question_projection_sha256':plan['rows_sha256'],'plan_sha256':a.sha(a.RUN/'plan.json'),
  'granite_revision':a.REVISION,'deepseek_alias':plan['deepseek_alias'],'granite_completed':len(data['granite']),'deepseek_completed':len(data['deepseek']),
  'runtime_scope':plan['runtime_scope'],'sampling_scope':plan['sampling_scope'],'cells':cells,'paired_comparisons':comparisons,
  'granite_cap_prefix_checks':prefix_checks,
  'reference_audit':reference_audit,
  'error_audit':error_audit,
  'granite_worker':worker_summary,
  'limitations':['32 seeded questions from an existing, repeatedly inspected development cohort; one sample per cell; no official-test claim.','Accuracy means numeric agreement with dataset references. Two posthoc interpretation-sensitive cases are flagged separately; grades and denominators are unchanged.','Question-bootstrap intervals do not include repeated decoding or training-seed uncertainty; comparisons are exploratory.','Tokens differ by tokenizer. Both reasoning and final answer count toward the shared native output cap.','Granite runs batch one on a dedicated A100 with warm weights using Transformers and SDPA. DeepSeek runtime includes network and provider service; neither hardware nor sampling is matched.','Granite low and DeepSeek low are native controls and do not imply equal internal effort.','DeepSeek V4 Pro is a much larger teacher model; this is not a parameter-matched architecture comparison.','A capped unfinished answer is scored incorrect even if a numeric guess appears in its reasoning. No retries or answer-based exclusions.','The 512 and 2048 caps test bounded-budget behavior, not unconstrained reasoning ability. A truncated answer may succeed with a larger budget.']}
 out=ROOT/'docs/inference-efficiency-results.json';out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
 md=['# Granite and DeepSeek inference efficiency','',f"Status: {result['stage']}. Inference only. Same 32 GSM8K TRAIN development questions; no training or official-test access.",'',
  'The caps are 512 and 2048 total generated tokens, including reasoning and final output. Each cell uses one sampled response per question. Granite uses its native nonthinking, low-effort and thinking controls. DeepSeek uses nonthinking, low, high and max. These names do not calibrate equal effort.','',
  '| Model | Mode | Cap | Reference matches | Total output tokens | Truncated | Total request seconds | Median request seconds | Tokens per correct |',
  '|---|---|---:|---:|---:|---:|---:|---:|---:|']
 for c in cells:
  md.append('| '+ ' | '.join([c['service'],c['mode'],str(c['cap']),f"{c['correct']}/{c['completed_attempts']}" if c['complete_cell'] else f"Pending ({c['completed_attempts']}/32 attempts)",
   str(c['total_output_tokens']) if c['output_usage_complete'] else str(c['total_output_tokens'])+' known',str(c['truncated']),f"{c['total_request_seconds']:.2f}",f"{c['median_request_seconds']:.2f}" if c['median_request_seconds'] is not None else '—',f"{c['tokens_per_correct']:.1f}" if c['tokens_per_correct'] is not None else '—'])+' |')
 md+=['','## Paired changes','', '| Change | Corrected | Regressed | Accuracy change pp | Exploratory paired 95 percent interval | Extra output tokens |','|---|---:|---:|---:|---|---:|']
 for c in comparisons:md.append(f"| {c['label']} | {c['corrected']} | {c['regressed']} | {c['accuracy_change_pp']:+.2f} | [{c['paired_bootstrap95_pp'][0]:+.2f}, {c['paired_bootstrap95_pp'][1]:+.2f}] | {c['total_extra_tokens']} |")
 md+=['','## Reference interpretation review','',reference_audit['scope'],'']
 for c in reference_audit['cases']:
  md+=[f"- {c['question_id']}: {c['issue']} Reference: {c['reference_calculation']}. Alternative: {c['alternative_calculation']}. Primary grades are unchanged."]
 md+=['','## Reviewed completed Granite errors','',error_audit['scope'],'']
 for c in error_audit['cases']:
  md+=[f"- {c['question_id']}, low effort / 2048 cap: returned {c['observed_answer']}; reference {c['reference_answer']}. Exact check: {c['verified_calculation']}. {c['observed_mechanism']}"]
 md+=['',error_audit['next_hypothesis'],'']
 md+=['','## How to interpret the measurements','']+[f'- {x}' for x in result['limitations']]
 md+=['','Runtime in the main table is the sum of serial request durations. Granite also saves synchronized GPU-generation seconds, model-load time, warmup and whole-worker time separately. DeepSeek output totals are the provider completion_tokens field; reasoning_tokens is a subset and is never added twice. Unknown usage is never treated as zero.','',
  'Scientific question: does a larger cap or deeper mode correct enough additional questions to justify its extra tokens and request time? Extra spending on wrong or still-incorrect answers is a diagnostic; it does not prove the reasoning could be removed without changing behavior.','',
  'Inference settings and data are independently versioned from the earlier 200-question greedy/nonthinking experiment. The new scores must not be joined to old scores as one improvement curve.','',
  'Sources: [Granite native modes](https://huggingface.co/ibm-granite/granite-4.2-3b#thinking-modes), [DeepSeek native controls](https://api-docs.deepseek.com/guides/thinking_mode/), [DeepSeek usage fields](https://api-docs.deepseek.com/api/create-chat-completion/).','']
 if worker_summary and worker_summary['actual_provider_calls']>1:
  md+=['Granite used two actual provider calls after the first reached its predefined time guard. The second executed only never-attempted cases, on the same GPU class and package versions, within the original $3 GPU envelope. Original provider results remain separate; their union is explicitly a derived artifact. Warm request metrics exclude each call\'s separately recorded model-load and synthetic-warmup times.','']
 (ROOT/'progress/INFERENCE_EFFICIENCY_RESULTS.md').write_text('\n'.join(md),encoding='utf-8')
 print(json.dumps({'stage':result['stage'],'granite':result['granite_completed'],'deepseek':result['deepseek_completed'],'cells_complete':sum(c['complete_cell'] for c in cells)}))
 return result

if __name__=='__main__':build()
