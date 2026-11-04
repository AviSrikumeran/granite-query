"""Reproducible tokenizer and tensor-layout diagnostics using public artifacts."""
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import struct
import numpy as np
from tokenizers import Tokenizer

ROOT = Path(__file__).resolve().parent
PROBES = [
 ('english_math','A shop sells 12 boxes with 8 pencils in each box. It gives away 17 pencils. How many pencils remain?'),
 ('english_math','A train travels 180 miles in 3 hours. If its speed stays constant, how far will it travel in 5 hours?'),
 ('english_math','Three friends split a bill of $48.60 equally and each adds a $2.50 tip. How much does each person pay?'),
 ('english_math','A tank is 3/4 full. After using 18 liters, it is 1/2 full. What is the capacity of the tank?'),
 ('english_math','The original price is 250 dollars. Apply a 20 percent discount followed by a 10 percent sales tax.'),
 ('english_math','The ratio of red to blue beads is 5:7. There are 84 blue beads. Find the total number of beads.'),
 ('english_prose','Training data should be checked for correctness, duplicates, coverage, and contamination before examples are ranked.'),
 ('english_prose','The report separates measured results from hypotheses. A smaller model may be useful if it meets the required quality at a lower cost.'),
 ('code','def total_price(items, tax_rate):\n    subtotal = sum(price * count for price, count in items)\n    return round(subtotal * (1 + tax_rate), 2)\n'),
 ('code','SELECT customer_id, SUM(amount) AS revenue FROM orders WHERE status = \'paid\' GROUP BY customer_id ORDER BY revenue DESC;'),
 ('structured','{"model":"granite","correct":179,"questions":200,"thinking":false,"max_new_tokens":512}'),
 ('structured','Compute 123456789 + 987654321, then explain why 0.1 + 0.2 can differ from 0.3 in floating point arithmetic.'),
 ('french','Un magasin vend douze boîtes contenant chacune huit crayons. Il donne dix-sept crayons. Combien en reste-t-il ?'),
 ('chinese','一家商店有十二盒铅笔，每盒八支。送出十七支后，还剩多少支铅笔？'),
 ('arabic','لدى متجر اثنا عشر صندوقا، في كل صندوق ثمانية أقلام. أعطى سبعة عشر قلما. كم قلما بقي؟'),
]

def write(path, data):
 path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def main():
 inventory=json.loads((ROOT/'model_inventory.json').read_text(encoding='utf-8'))
 models=[]
 for d in inventory['models']:
  p=ROOT/'models'/d['repo'].replace('/','--')
  c=d.get('config',{}); c=c.get('text_config',c)
  hs={}
  for name in d.get('canonical_weight_files',[]):
   f=p/(name+'.header.json')
   if f.exists(): hs.update({k:v for k,v in json.loads(f.read_text()).items() if k!='__metadata__'})
  elements=sum(math.prod(t['shape']) for t in hs.values())
  # Quantization scale tensors are stored elements too, not learned weights.
  scales=sum(math.prod(t['shape']) for k,t in hs.items() if 'scale' in k)
  types=Counter()
  for t in hs.values(): types[t['dtype']]+=math.prod(t['shape'])
  layout=[{'name':k,'shape':v['shape'],'dtype':v['dtype'],'elements':math.prod(v['shape'])} for k,v in hs.items() if ('layers.0.' in k and ('proj.weight' in k or 'A_log' in k)) or k.endswith('embed_tokens.weight') or k=='lm_head.weight']
  row={k:d.get(k) for k in ['repo','revision','license','gated','status','header_inventory_complete','header_shards_inspected','weight_bytes']}
  row.update(layers=c.get('num_hidden_layers'),hidden=c.get('hidden_size'),intermediate=c.get('intermediate_size'),vocab=c.get('vocab_size'),model_type=c.get('model_type'),stored_elements=elements,scale_elements=scales,dtype_elements=dict(types),layout=layout)
  if (p/'tokenizer.json').exists():
   try:
    tok=Tokenizer.from_file(str(p/'tokenizer.json'))
    counts=[len(tok.encode(text,add_special_tokens=False).ids) for _,text in PROBES]
    row['probe_counts']=counts
    row['probe_groups']={g:sum(n for (group,_),n in zip(PROBES,counts) if group==g) for g in dict(PROBES)}
   except Exception as e: row['tokenizer_error']=str(e)
  models.append(row)
 granite=next(m for m in models if m['repo']=='ibm-granite/granite-4.2-3b')
 for row in models:
  if 'probe_counts' in row:
   row['granite_to_model_english_math_ratio']=granite['probe_groups']['english_math']/row['probe_groups']['english_math']
 summary={'observed_date':'2026-11-03','priority':'high','models':models,'probes':[{'id':i+1,'group':g,'text':t,'utf8_bytes':len(t.encode('utf-8'))} for i,(g,t) in enumerate(PROBES)],'probe_method':'15 authored diagnostic strings, six English math. Raw encoding with add_special_tokens=False. Counts exclude chat templates and generated answers. No inference or evaluation questions were used. These strings are not a representative benchmark.','sparse_illustration':{'base_parameters':3659737600,'mlp_parameters_per_layer':3*2560*8192,'selected_layers':8,'experts_per_layer':4,'top_k':1,'additional_expert_parameters':8*3*2560*8192*3,'router_parameters_without_bias':8*2560*4,'total_parameters':3659737600+8*3*2560*8192*3+8*2560*4,'status':'illustrative design only; not implemented or trained'}}
 write(ROOT/'diagnostics.json',summary)
 print(json.dumps({'tokenizer_math_counts':{r['repo']:r.get('probe_groups',{}).get('english_math') for r in models},'granite_parameters':granite['stored_elements'],'sparse_total':summary['sparse_illustration']['total_parameters']},indent=2))

if __name__=='__main__':main()
