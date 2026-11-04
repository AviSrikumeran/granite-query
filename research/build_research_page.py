"""Build a self-contained research page and public evidence bundle."""
import html
import json
from pathlib import Path
import re
from markdown_it import MarkdownIt

ROOT=Path(__file__).resolve().parents[1]
RESEARCH=ROOT/'research'
DOCS=ROOT/'docs'

def main():
 d=json.loads((RESEARCH/'diagnostics.json').read_text(encoding='utf-8'))
 d['download']=json.loads((RESEARCH/'granite_download_receipt.json').read_text())
 d['value_audit']=json.loads((RESEARCH/'granite_value_audit.json').read_text())
 d['scalar_samples']=json.loads((RESEARCH/'scalar_samples.json').read_text())
 # Public data has no local paths, credentials, training data or model responses.
 public=json.dumps(d,ensure_ascii=False,indent=2)+'\n'
 (DOCS/'granite-efficiency-evidence.json').write_text(public,encoding='utf-8')
 report=(ROOT/'progress/GRANITE_EFFICIENCY_RESEARCH.md').read_text(encoding='utf-8')
 report=report.replace('](DEVELOPMENT_TEACHER200.md)','](https://github.com/AviSrikumeran/granite-query/blob/main/progress/DEVELOPMENT_TEACHER200.md)').replace('](HUMAN_STUDY_RESULTS.md)','](https://github.com/AviSrikumeran/granite-query/blob/main/progress/HUMAN_STUDY_RESULTS.md)')
 rendered=MarkdownIt('commonmark').enable('table').render(report)
 rendered=re.sub(r'<table>(.*?)</table>',r'<div class="scroll" tabindex="0" role="region" aria-label="Research comparison table"><table>\1</table></div>',rendered,flags=re.S)
 template=(RESEARCH/'page_template.html').read_text(encoding='utf-8')
 output=template.replace('<!--REPORT-->',rendered).replace('/*EVIDENCE*/',json.dumps(d,ensure_ascii=False).replace('</',r'<\/'))
 (DOCS/'granite-efficiency.html').write_text(output,encoding='utf-8')
 print(json.dumps({'page_bytes':len(output.encode()),'public_evidence_bytes':len(public.encode()),'models':len(d['models']),'download_complete':d['download']['complete'],'finite':d['value_audit']['finite']}))

if __name__=='__main__':main()
