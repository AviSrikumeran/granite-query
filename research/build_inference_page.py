"""Render the inference comparison from validated aggregate evidence."""
import html,json,re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def build():
 d=json.loads((ROOT/'docs/inference-efficiency-results.json').read_text())
 template=(ROOT/'research/inference_page_template.html').read_text(encoding='utf-8')
 out=template.replace('/*RESULTS*/',json.dumps(d).replace('</',r'<\/'))
 (ROOT/'docs/inference-efficiency.html').write_text(out,encoding='utf-8')
 print(json.dumps({'page_bytes':len(out.encode()),'stage':d['stage']}))

if __name__=='__main__':build()
