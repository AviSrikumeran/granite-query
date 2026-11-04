"""Build the static, prompt-private low-effort error review page."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def build():
 data=json.loads((ROOT/'docs/low-effort-error-review.json').read_text(encoding='utf-8'))
 if data['selected_misses']!=5 or data['curriculum']['candidate_count']!=15:raise ValueError('Review scope changed; update static editorial copy')
 template=(ROOT/'research/low_effort_page_template.html').read_text(encoding='utf-8')
 output=template.replace('/*REVIEW*/',json.dumps(data,ensure_ascii=False).replace('</',r'<\/'))
 (ROOT/'docs/low-effort-error-review.html').write_text(output,encoding='utf-8')
 print(json.dumps({'page_bytes':len(output.encode()),'cases':len(data['cases']),'candidates':data['curriculum']['candidate_count']}))
if __name__=='__main__':build()
