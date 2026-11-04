"""Build a self-contained research page and public evidence bundle."""
import html
import json
from pathlib import Path
import re
from markdown_it import MarkdownIt

ROOT=Path(__file__).resolve().parents[1]
RESEARCH=ROOT/'research'
DOCS=ROOT/'docs'

def render_markdown(text):
 rendered=MarkdownIt('commonmark').enable('table').render(text)
 return re.sub(r'<table>(.*?)</table>',r'<div class="scroll" tabindex="0" role="region" aria-label="Research comparison table"><table>\1</table></div>',rendered,flags=re.S)

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
 rendered=render_markdown(report)
 proposal=json.loads((ROOT/'progress/TARGETED_RANDOM_VERIFIED_PLAN.json').read_text(encoding='utf-8'))
 if proposal['status']!='planning_only_no_execution_scheduled' or proposal['new_training_jobs']!=0:
  raise ValueError('Decision page requires an explicitly unexecuted proposal')
 if proposal['model_decision']['student']!='ibm-granite/granite-4.2-3b' or proposal['model_decision']['revision']!='4e9c275e232f10211ec88644d106a1f6a1b60e06':
  raise ValueError('Accepted student checkpoint differs')
 (DOCS/'targeted-random-verified-plan.json').write_text(json.dumps(proposal,indent=2)+'\n',encoding='utf-8')
 decision=(RESEARCH/'decision_plan_sections.html').read_text(encoding='utf-8')
 values={'LOSS_POOL':proposal['pretraining_gates']['common_pool']['minimum_complete_serialized_assistant_loss_tokens'],
  'LOSS_BUDGET':proposal['arms']['both_training_arms']['assistant_loss_tokens'],'UPDATES':proposal['arms']['both_training_arms']['optimizer_updates'],
  'SEED':proposal['arms']['both_training_arms']['training_seed'],'TARGET_CASES':proposal['pretraining_gates']['transfer_development']['target_questions']}
 for key,value in values.items():decision=decision.replace('{{'+key+'}}',format(value,','))
 decision=decision.replace('<!--EXPERIMENT_PLAN-->',render_markdown((ROOT/'progress/TARGETED_RANDOM_VERIFIED_PLAN.md').read_text(encoding='utf-8')))
 template=(RESEARCH/'page_template.html').read_text(encoding='utf-8')
 if template.count('<!--DECISION_SECTIONS-->')!=1:raise ValueError('Decision insertion point missing or duplicated')
 output=template.replace('<!--DECISION_SECTIONS-->',decision).replace('<!--REPORT-->',rendered).replace('/*EVIDENCE*/',json.dumps(d,ensure_ascii=False).replace('</',r'<\/'))
 (DOCS/'granite-efficiency.html').write_text(output,encoding='utf-8')
 print(json.dumps({'page_bytes':len(output.encode()),'public_evidence_bytes':len(public.encode()),'models':len(d['models']),'download_complete':d['download']['complete'],'finite':d['value_audit']['finite']}))

if __name__=='__main__':main()
