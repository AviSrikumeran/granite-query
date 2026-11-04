"""Audit every low-effort miss using preserved receipts; no model calls."""
from collections import Counter
from datetime import datetime,timezone
from fractions import Fraction
import hashlib,json,re,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'granite_query'));sys.path.insert(0,str(ROOT/'research'))
from cloud import efficiency_audit as a
from cloud.comparison_metrics import score
from cloud.human_math_cohort import exact_arithmetic,annotation_check
from build_error_curriculum import build as build_curriculum,COHORT,OUT

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def digest(text):return hashlib.sha256(text.encode()).hexdigest()
def compact(row):
 return {k:row[k] for k in ('mode','cap','generated_tokens','truncated','failed','elapsed_seconds','scoring')}

def analyze():
 plan,questions=a.validate();q={r['id']:r for r in questions}
 public=json.loads((ROOT/'docs/inference-efficiency-results.json').read_text())
 if public['stage']!='completed' or public['plan_sha256']!=sha(a.RUN/'plan.json'):raise ValueError('Completed frozen inference study required')
 proof=a.read(a.RUN/'granite_composition.json')
 for file,key in [('granite_completed_results.json','combined_results_sha256'),('granite_provider_result.json','parent_result_sha256'),('remaining/provider_result.json','continuation_result_sha256')]:
  if sha(a.RUN/file)!=proof[key]:raise ValueError('Original Granite receipt composition differs')
 g=a.read(a.RUN/'granite_completed_results.json');d=a.read(a.RUN/'deepseek_results.json')
 for rows,key in [(g,'granite_cases'),(d,'deepseek_cases')]:
  expected={c['id']:c for c in plan[key]}
  if len(rows)!=len(expected) or len({r['id'] for r in rows})!=len(rows) or {r['id'] for r in rows}!=set(expected):raise ValueError('Case identity/count differs')
  for row in rows:
   if any(row[k]!=expected[row['id']][k] for k in ('question_id','mode','cap')) or row['gold_answer']!=q[row['question_id']]['gold_answer']:raise ValueError('Case metadata differs')
   if row['scoring']!=score(dict(row,truncated=row['truncated'] or row['failed'])):raise ValueError('Frozen numeric score differs')
 low=[r for r in g if r['mode']=='low' and r['cap']==2048]
 misses={r['question_id']:r for r in low if not r['scoring']['correct']}
 notes=json.loads((OUT/'curator_notes.json').read_text())
 if len(low)!=32 or set(misses)!={c['question_id'] for c in notes['cases']}:raise ValueError('Review must include every low-effort miss exactly once')
 train=ROOT/'granite_query/ranking/data/raw/train.jsonl'
 if sha(train)!='17f347dc51477c50d4efb83959dbb7c56297aba886e5544ee2aaed3024813465':raise ValueError('Pinned canonical TRAIN source differs')
 canonical=[json.loads(line) for line in train.read_text(encoding='utf-8').splitlines()]
 cases=[];private=[]
 for note in notes['cases']:
  qid=note['question_id'];gr=misses[qid];question=q[qid];ds=next(r for r in d if r['question_id']==qid and r['mode']=='nonthinking' and r['cap']==2048)
  short=next(r for r in g if r['question_id']==qid and r['mode']=='low' and r['cap']==512)
  reference=canonical[int(qid.rsplit(':',1)[1])]
  if reference['question']!=question['prompt'] or reference['answer'].rsplit('####',1)[1].strip()!=question['gold_answer']:raise ValueError('Canonical TRAIN reference differs')
  if short['output_ids']!=gr['output_ids'] or gr['failed'] or gr['truncated'] or not gr['thinking_closed']:raise ValueError('Expected completed, identical low-effort outputs at both caps')
  if len(gr['output_ids'])!=gr['generated_tokens']:raise ValueError('Granite token count differs')
  if not re.search(r'####\s*[+-]?\d+(?:\.\d+)?\s*$',gr['response']):raise ValueError('Review assumed valid answer formatting')
  for span in note['support_spans']:
   if span not in gr['reasoning_content']:raise ValueError('Generated-text support span absent: '+span)
  if (gr['scoring']['prediction']!=note['granite_prediction'] or ds['scoring']['prediction']!=note['deepseek_prediction'] or question['gold_answer']!=note['reference']):raise ValueError('Curator predictions differ from originals')
  for check in note['checks']:
   if exact_arithmetic(check['expression'])!=Fraction(check['result']):raise ValueError('Reviewed arithmetic fails exact check')
  modes=[]
  for row in sorted([r for r in d if r['question_id']==qid and r['cap']==2048],key=lambda r:r['mode']):
   wire=(a.RUN/'deepseek_attempts'/(digest(row['id'])+'.wire.json')).read_bytes()
   if hashlib.sha256(wire).hexdigest()!=row['wire_sha256']:raise ValueError('Teacher receipt hash differs')
   raw=json.loads(wire);choice=raw['choices'][0]
   if raw['usage']!=row['usage'] or row['generated_tokens']!=raw['usage']['completion_tokens'] or (choice['message'].get('content') or '')!=row['response'] or (choice['message'].get('reasoning_content') or '')!=row['reasoning_content']:raise ValueError('Teacher receipt does not support derived trace')
   modes.append(compact(row))
  case={k:v for k,v in note.items() if k!='support_spans'}
  case.update(granite_low=compact(gr),deepseek_nonthinking=compact(ds),deepseek_modes=modes,
   granite_modes=[compact(r) for r in sorted(g,key=lambda r:r['mode']) if r['question_id']==qid and r['cap']==2048],
   low_caps_identical=True,valid_final_numeric_format=True,canonical_reference_sha256=digest(reference['answer']),
   granite_trace_sha256=digest(gr['reasoning_content']+'\n'+gr['response']),teacher_final_sha256=digest(ds['response']))
  cases.append(case)
  private.append(dict(case,question=question,canonical_reference=reference['answer'],granite_generated_reasoning=gr['reasoning_content'],granite_final=gr['response'],
   deepseek_final=ds['response'],curator_support_spans=note['support_spans']))
 records,manifest=build_curriculum()
 source={r['id']:r for r in [json.loads(line) for line in COHORT.read_text().splitlines()]}
 rejections=[]
 for reject in notes['candidate_rejections']:
  row=source[reject['id']]
  if reject['required_span'] not in row['reference_solution']:raise ValueError('Reference defect support absent')
  check,_,_=annotation_check(row['reference_solution'],row['gold_answer'])
  if check is None:raise ValueError('Expected arithmetic-pass semantic counterexample')
  rejections.append({k:v for k,v in reject.items() if k!='required_span'}|{'arithmetic_annotation_check_passed':True,'changed_existing_training_pool':False})
 process=[c for c in cases if c['kind']=='process_failure']
 summary={'schema_version':1,'stage':'review_complete_training_unproven','reviewed_local_date':'2026-11-03','timezone':'America/Chicago',
  'run_id':plan['run_id'],'selection':notes['selection'],'selected_misses':len(cases),'original_low_effort_reference_matches':'27/32',
  'process_failures':len(process),'reference_sensitive':len(cases)-len(process),
  'process_failures_solved_by_deepseek_nonthinking':sum(c['deepseek_nonthinking']['scoring']['correct'] for c in process),
  'process_failures_solved_by_granite_nonthinking':sum(next(r for r in c['granite_modes'] if r['mode']=='nonthinking')['scoring']['correct'] for c in process),
  'new_model_calls':0,'new_training':False,'primary_grader_changed':False,'official_test_accessed':False,
  'evidence_sha256':{'plan':sha(a.RUN/'plan.json'),'granite_outcomes':sha(a.RUN/'granite_completed_results.json'),'deepseek_outcomes':sha(a.RUN/'deepseek_results.json'),'curator_notes':sha(OUT/'curator_notes.json')},
  'cases':cases,'candidate_reference_rejections':rejections,'curriculum':manifest,
  'candidate_sources':[{'id':r.get('source_id',r['id']),'family':r['family'],'title':r.get('title',r.get('variant')),'target_granite_tokens':r['target_granite_tokens']} for r in records],
  'authored_counterfactuals':[{k:r[k] for k in ['id','family','contrast_group','variant','prompt','target','gold_answer','training_ready']} for r in records if r['source']=='authored_error_analysis_seed'],
  'training_plan':[
   'Treat these three process failures as development-informed hypotheses. First expand manual error review to more development questions before choosing category weights.',
   'Before retraining, compare a short entity-and-quantity-ledger prompt with the current prompt on separate transfer-development questions, using repeated decoding and total-token accounting. A prompt or mode change may improve reliability with the original weights.',
   'Build a larger semantically reviewed training pool with varied contexts. Use these 15 examples to establish quality criteria; do not fill the pool with numerical clones of the five missed questions.',
   'Compare targeted selection with random selection from the same reviewed pool. Apply the same concise worked-solution style and validation rules to both arms, and match actual supervised tokens and optimizer updates.',
   'Use fresh copies of the same base checkpoint and identical adapter/optimizer settings. Validate native low-effort serialization, role masks, target completeness and EOS before any run. Include an untouched-base comparison.',
   'Freeze a new transfer-development set from untouched TRAIN questions or independently authored families. Keep all original 200 development questions excluded from training. These five reviewed cases are diagnostic, not independent confirmation.',
   'Report paired corrections/regressions, accuracy, total tokens, truncation and runtime in low-effort mode; also check nonthinking and instruction/tool/grounding retention. Repeat decoding or training seeds before stronger claims.',
   'Keep the two ambiguous references out of corrective supervision. A separate clarification/interval/averaging task can teach explicit conventions with verified labels.',
   'Launch training only through a separately reviewed and funded protocol. This review adds no jobs, reservations, live manifests or official-test access.'
  ],
  'limitations':['Five selected misses from one sampled 32-question study. This diagnoses observed text, not hidden model internals or the causal effect of training.',
   'All three process failures were solved by Granite in sampled nonthinking responses, but mode and random decoding differ; this does not prove a deterministic mode effect.',
   'DeepSeek is an evidence source, not an automatic ground-truth oracle. Reference-sensitive items preserve their original grades.',
   'Semantic review was performed by this assistant and is not an independent second-rater study. Candidate checks and examples are a starter specification, not evidence of improved model performance.']}
 OUT.mkdir(exist_ok=True)
 (OUT/'private_case_review.json').write_text(json.dumps(private,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
 (ROOT/'docs/low-effort-error-review.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
 md=['# Granite low-effort misses: paired answer and training-data review','',
  '**Status: review complete; training benefit unproven. High priority. November 3, 2026, America/Chicago.**','',
  'All five low-effort misses are retained. Three are supported process failures; two are reference-sensitive. DeepSeek nonthinking solves all three process failures, and the same Granite checkpoint also solves all three in its sampled nonthinking answers. There were no new model calls or training runs. The original 27/32 score is unchanged.','',
  '| Case | Granite low / tokens | DeepSeek nonthinking / tokens | Assessment |','|---|---:|---:|---|']
 for c in cases:md.append(f"| {c['title']} | {c['granite_prediction']} / {c['granite_low']['generated_tokens']} | {c['deepseek_prediction']} / {c['deepseek_nonthinking']['generated_tokens']} | {c['kind']} |")
 for c in cases:
  md+=['',f"## {c['title']}",'',f"Source ID: `{c['question_id']}`. Dataset reference: {c['reference']}.",'',
   c['setup'],'','Granite observed text: '+c['granite_observation'],'','DeepSeek comparison: '+c['deepseek_observation'],'',
   'Verified arithmetic: '+'; '.join(x['expression']+' = '+x['result'] for x in c['checks'])+'.','',
   'Data implication: '+c['data_needed'],'',c['confidence']]
 md+=['','## Candidate curriculum','',
  f"Prepared {manifest['candidate_count']} untrained seed examples: nine manually reviewed questions from the existing TRAIN teaching pool and six authored counterfactual examples, five per skill family. All exact calculations were checked. The 200-question development exclusion was checked by IDs, normalized text and a limited numeric-masked lexical diagnostic. None entered a live training manifest.",'',
  'The assistant targets contain concise named calculations and final answers. Raw target token counts exclude template/EOS and cannot be treated as an actual supervised-token budget. These are posthoc development-informed training candidates, not independent evaluation cases.','',
  '| Training source ID | Family | Purpose |','|---|---|---|']
 for r in summary['candidate_sources']:md.append(f"| {r['id']} | {r['family']} | {r['title']} |")
 md+=['','## Reference defects found during candidate review','',
  'Two references passed the existing exact-annotation/final-number checks but contained contradictory prose. This is a targeted manual finding, not a rejection-rate estimate for the full pool. The existing pool was left unchanged.','']
 md += [f"- {r['id']}: {r['issue']} {r['decision']}" for r in rejections]
 md+=['','## Experiment required to establish usefulness','']+[f'{i+1}. {text}' for i,text in enumerate(summary['training_plan'])]
 md+=['','## Limits','']+['- '+x for x in summary['limitations']]
 md+=['','The earlier final-answer-only review was cautious about the book and fuel mistakes. Reviewing their preserved generated reasoning now supplies explicit evidence of the omitted gift subtotal and stale bag count. This describes generated text rather than a direct measurement of internal computation.','',
  'Reproduce locally: `python research/analyze_low_effort_errors.py`, then `python research/build_low_effort_page.py`. These require the existing private inference receipts and curator notes, TRAIN teaching/development artifacts and local pinned tokenizer. They do not call providers.','']
 (ROOT/'progress/LOW_EFFORT_ERROR_REVIEW.md').write_text('\n'.join(md),encoding='utf-8')
 return summary

if __name__=='__main__':
 s=analyze();print(json.dumps({k:s[k] for k in ['stage','selected_misses','process_failures','reference_sensitive','process_failures_solved_by_granite_nonthinking','new_model_calls']}));print(json.dumps(s['curriculum']))
