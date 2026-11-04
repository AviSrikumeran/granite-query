"""Unpaid, reviewable seed curriculum; no trainer/API/GPU dispatch or test reads.

Every source is from the already approved TRAIN teaching cohort. The original
development questions and teacher traces are evidence only. Draft examples
remain outside all live training manifests and are not marked training-ready.
"""
from copy import deepcopy
from fractions import Fraction
import hashlib,json,re,sys,unicodedata
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'granite_query'))
from cloud.human_math_cohort import exact_arithmetic,annotation_check,masked_shingles

COHORT=ROOT/'granite_query/cloud/runs/human_math_cohort2048_dev200_v1/candidates.jsonl'
DEV=COHORT.with_name('development.jsonl')
OUT=ROOT/'granite_query/cloud/runs/low_effort_error_review_v1'

# Manually reviewed semantic bindings. Numeric results are separately checked
# against exact arithmetic and the pinned source's reference final number.
SOURCE_SPECS=[
 ('04233','units_and_aggregation','Meal quantities to bags to cost',[
  ('Potatoes needed','1.5*40','60','pounds'),('Bags needed','60/20','3','bags'),('Total cost','3*5','15','dollars')]),
 ('03612','units_and_aggregation','Cards through students, packs and cost',[
  ('Students','6*30','180','students'),('Cards','180*10','1800','cards'),('Packs','1800/50','36','packs'),('Total cost','36*3','108','dollars')]),
 ('04326','units_and_aggregation','Two sellers with different price units',[
  ('Liam pairs','40/2','20','pairs'),('Liam revenue','20*2.5','50','dollars'),('Claire revenue','30*1.2','36','dollars'),('Combined revenue','50+36','86','dollars')]),
 ('03019','complete_quantity_ledger','Inventory with a mixed-color outgoing gift',[
  ('Blue marbles bought','6*10','60','marbles'),('Before gift','26+60','86','marbles'),('Gift removed','6+8','14','marbles'),('Remaining','86-14','72','marbles')]),
 ('05346','complete_quantity_ledger','Donations from multiple locations and a later addition',[
  ('Boxed donations','3*15','45','books'),('All donations','45+21+4+18','88','books'),('After donations','99-88','11','books'),('After new books','11+12','23','books')]),
 ('01306','complete_quantity_ledger','Carry all three spending categories into the balance',[
  ('Gum cost','3*1','3','dollars'),('Chocolate cost','5*1','5','dollars'),('Candy-cane cost','2*0.5','1','dollars'),('All spending','3+5+1','9','dollars'),('Remaining','10-9','1','dollars')]),
 ('02606','entity_scope_and_dependencies','Students and adults have different fees',[
  ('Student fees','35*5','175','dollars'),('Adult fees','4*6','24','dollars'),('Total fees','175+24','199','dollars')]),
 ('05541','entity_scope_and_dependencies','Separate adult tickets, child tickets and concessions',[
  ('All ticket spending','76-12','64','dollars'),('Child ticket spending','2*7','14','dollars'),('Adult ticket spending','64-14','50','dollars'),('Each adult ticket','50/5','10','dollars')]),
 ('04040','entity_scope_and_dependencies','Different consuming and sharing groups',[
  ('Adults eat','120/3','40','cookies'),('Children share','120-40','80','cookies'),('Each child receives','80/4','20','cookies')])
]

def digest(raw):return hashlib.sha256(raw).hexdigest()
def normalized(text):return ' '.join(unicodedata.normalize('NFKC',text).casefold().split())
def read_rows(path):return [json.loads(s) for s in path.read_text(encoding='utf-8-sig').splitlines() if s.strip()]
def number(value):
 value=Fraction(value)
 if value.denominator==1:return str(value.numerator)
 # All authored seed values are exactly terminating decimals.
 denominator=value.denominator
 for factor in (2,5):
  while denominator%factor==0:denominator//=factor
 if denominator!=1:return str(value)
 from decimal import Decimal
 return format(Decimal(value.numerator)/Decimal(value.denominator),'f').rstrip('0').rstrip('.')

def render(steps,answer,note=''):
 lines=([note] if note else [])+[f'{label}: {expression} = {value} {unit}.' for label,expression,value,unit in steps]
 return '\n'.join(lines)+'\n\n#### '+answer

def synthetic():
 common={'source':'authored_error_analysis_seed','source_split':'authored_training_draft','posthoc_development_informed':True}
 printer='A print station takes 5 minutes per batch. A batch prints either 3 A-labels, 4 B-labels, or 6 C-labels. The order needs 6 A-labels, 12 B-labels, and 18 C-labels. '
 ledger='A club has 48 tokens. It then receives 7 membership tokens, buys 5 more, spends 8, and donates 2. '
 scope='A workshop has 18 apprentices and 3 mentors. Admission costs 5 dollars for each attendee. Brushes cost 4 dollars each. '
 specs=[
  ('units-sequential','units_and_aggregation','printer-semantics','sequential',printer+'One station prints all batches sequentially. How many minutes does it take?',
   [('A batches','6/3','2','batches'),('B batches','12/4','3','batches'),('C batches','18/6','3','batches'),('Total time','5*(2+3+3)','40','minutes')],'40',''),
  ('units-parallel','units_and_aggregation','printer-semantics','parallel',printer+'Three identical stations start together, with one assigned to each label type and no shared work. How many minutes until the entire order is finished?',
   [('A station time','5*(6/3)','10','minutes'),('B station time','5*(12/4)','15','minutes'),('C station time','5*(18/6)','15','minutes'),('Completion time','15','15','minutes')],'15','Parallel completion uses the largest station time, rather than adding station times.'),
  ('ledger-new-gifts','complete_quantity_ledger','gift-timing','new_gifts',ledger+'After that, it receives two gifts of 4 and 3 tokens. How many tokens does it now have?',
   [('All additions','7+5+4+3','19','tokens'),('All removals','8+2','10','tokens'),('Ending balance','48+19-10','57','tokens')],'57',''),
  ('ledger-counted-gifts','complete_quantity_ledger','gift-timing','already_counted',ledger+'The original 48-token count already included two gifts of 4 and 3 tokens. Those gifts are not received again. How many tokens does it now have?',
   [('New additions','7+5','12','tokens'),('All removals','8+2','10','tokens'),('Ending balance','48+12-10','50','tokens')],'50','The two earlier gifts are already in the starting balance and are counted once.'),
  ('scope-all','entity_scope_and_dependencies','brush-recipients','all_attendees',scope+'Every attendee receives 2 brushes. How much do admission and brushes cost altogether?',
   [('Attendees','18+3','21','people'),('Brushes','21*2','42','brushes'),('Admission','21*5','105','dollars'),('Brush cost','42*4','168','dollars'),('Total','105+168','273','dollars')],'273',''),
  ('scope-subset','entity_scope_and_dependencies','brush-recipients','apprentices_only',scope+'Only apprentices receive 2 brushes each; mentors bring their own and buy none. How much do admission and purchased brushes cost altogether?',
   [('Attendees','18+3','21','people'),('Purchased brushes','18*2','36','brushes'),('Admission','21*5','105','dollars'),('Brush cost','36*4','144','dollars'),('Total','105+144','249','dollars')],'249','')
 ]
 return [dict(common,id='authored:'+identifier,family=family,contrast_group=group,variant=variant,prompt=prompt,steps=steps,gold_answer=answer,note=note,
  semantic_review='Authored wording explicitly fixes timing, resource sharing, or entity membership; reviewed against the structured calculation.') for identifier,family,group,variant,prompt,steps,answer,note in specs]

def verify_row(row):
 if not row['steps']:raise ValueError('No worked calculation')
 for _,expression,result,_ in row['steps']:
  if exact_arithmetic(expression)!=Fraction(result):raise ValueError('Incorrect intermediate calculation')
 if Fraction(row['steps'][-1][2])!=Fraction(row['gold_answer']):raise ValueError('Final answer not linked to final step')
 if row['target']!=render(row['steps'],row['gold_answer'],row.get('note','')):raise ValueError('Target not the reviewed complete solution')
 if row['training_ready'] is not False:raise ValueError('Seed review is not training authorization')
 if row.get('source')=='authored_error_analysis_seed':
  # Independent semantic oracle for these six fixed, explicitly authored cases.
  expected={'sequential':5*(6//3+12//4+18//6),'parallel':5*max(6//3,12//4,18//6),
   'new_gifts':48+7+5+4+3-8-2,'already_counted':48+7+5-8-2,
   'all_attendees':(18+3)*5+(18+3)*2*4,'apprentices_only':(18+3)*5+18*2*4}
  if Fraction(row['gold_answer'])!=expected[row['variant']]:raise ValueError('Answer contradicts authored semantic variant')

def build():
 cohort=read_rows(COHORT);by_id={r['id']:r for r in cohort};dev=read_rows(DEV)
 if len(cohort)!=2048 or len(dev)!=200:raise ValueError('Expected established TRAIN cohorts')
 if digest(DEV.read_bytes())!='cccdce864d728e6b43d9d4de866e719bfd9c706cc735a3a3d429095835c767c7':raise ValueError('Development source changed')
 records=[]
 for suffix,family,title,steps in SOURCE_SPECS:
  source=by_id['gsm8k:train:'+suffix]
  if source['source_split']!='train' or source['id'] in {d['id'] for d in dev}:raise ValueError('Invalid training source')
  proof,reason,_=annotation_check(source['reference_solution'],source['gold_answer'])
  if proof is None:raise ValueError('Source annotation checks failed: '+reason)
  records.append({'id':'reviewed:'+source['id'],'source_id':source['id'],'source':source['source'],'source_split':'train',
   'source_revision':source['source_revision'],'source_reference_sha256':digest(source['reference_solution'].encode()),
   'prompt':source['prompt'],'gold_answer':source['gold_answer'],'family':family,'title':title,'steps':steps,
   'semantic_review':'Question, entity bindings and concise rewritten worked solution manually reviewed together; exact calculations checked separately.'})
 records+=synthetic()
 dev_ids={r['id'] for r in dev};dev_norm={normalized(r['prompt']) for r in dev};dev_shingles=[masked_shingles(r['prompt']) for r in dev]
 from transformers import AutoTokenizer
 tok=AutoTokenizer.from_pretrained(str(ROOT/'research/models/ibm-granite--granite-4.2-3b'),local_files_only=True)
 for row in records:
  row['training_ready']=False;row['role']='candidate_training_seed_for_review';row['target']=render(row['steps'],row['gold_answer'],row.get('note',''))
  row['target_granite_tokens']=len(tok.encode(row['target'],add_special_tokens=False))
  if row.get('source_id') in dev_ids or normalized(row['prompt']) in dev_norm:raise ValueError('Development item leaked into candidate set')
  shingles=masked_shingles(row['prompt']);row['max_number_masked_fivegram_jaccard_with_development']=max(len(shingles&s)/len(shingles|s) for s in dev_shingles)
  if row['max_number_masked_fivegram_jaccard_with_development']>=.7:raise ValueError('Candidate too lexically close to development question')
  verify_row(row)
 groups={r['contrast_group'] for r in records if 'contrast_group' in r}
 for group in groups:
  pair=[r for r in records if r.get('contrast_group')==group]
  if len(pair)!=2 or len({r['gold_answer'] for r in pair})!=2:raise ValueError('Counterfactual pair did not change the answer')
 OUT.mkdir(parents=True,exist_ok=True)
 raw=''.join(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n' for row in records).encode()
 (OUT/'candidate_curriculum.jsonl').write_bytes(raw)
 manifest={'schema_version':1,'stage':'untrained_review_seed','candidate_count':len(records),'human_train_questions':9,'authored_counterfactual_examples':6,
  'families':{family:sum(r['family']==family for r in records) for family in sorted({r['family'] for r in records})},
  'candidate_curriculum_sha256':digest(raw),'approved_training_cohort_sha256':digest(COHORT.read_bytes()),'development_source_sha256':digest(DEV.read_bytes()),
  'development_count_checked':200,'exact_id_or_normalized_prompt_overlap':0,'number_masked_fivegram_jaccard_rejection_threshold':.7,
  'maximum_observed_jaccard':max(r['max_number_masked_fivegram_jaccard_with_development'] for r in records),
  'total_target_granite_tokens':sum(r['target_granite_tokens'] for r in records),'maximum_target_granite_tokens':max(r['target_granite_tokens'] for r in records),
  'target_token_scope':'Raw assistant worked-solution text under the pinned Granite tokenizer, excluding chat prefix and EOS. This is not a supervised-token budget.',
  'new_model_calls':0,'new_training':False,'official_test_accessed':False,'added_to_live_training_manifests':False,
  'limitations':['Small posthoc seed set; usefulness is a hypothesis, not a demonstrated training gain.','Exact arithmetic does not certify question semantics; each selected example also received a manual semantic review.','Lexical checks detect only some overlap. These examples deliberately share skills with development errors and are not independent evaluation data.','The nine human questions are from an existing training pool and may have appeared in earlier project runs. No claim of globally novel training data.','Native low-effort training serialization, masks, EOS and save/reload still require a separate trainer preflight.']}
 (OUT/'curriculum_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
 return records,manifest

if __name__=='__main__':
 _,m=build();print(json.dumps(m,indent=2))
