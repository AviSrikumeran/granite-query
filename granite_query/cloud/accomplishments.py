"""Evidence-derived public accomplishments inventory; never exports private runtime data."""
from datetime import datetime, timezone
import json
from pathlib import Path

try:
    from .comparison_metrics import summarize
except ImportError:
    from comparison_metrics import summarize

WORKSPACE = Path(__file__).resolve().parents[2]
REPORT_URL = 'https://github.com/AviSrikumeran/granite-query/blob/main/progress/RESULTS.md'
RUNS_URL = 'https://github.com/AviSrikumeran/granite-query/blob/main/progress/IMPROVEMENT_PLAN.md'
MODEL = 'ibm-granite/granite-4.2-3b'
REVISION = '4e9c275e232f10211ec88644d106a1f6a1b60e06'
SOURCE = 'https://github.com/openai/grade-school-math'
SOURCE_REVISION = '3101c7d5072418e28b9008a6636bde82a006892c'
APP_URLS = {
    'smoke': 'https://modal.com/apps/avisrikumeran/main/ap-WS6yWYh6OmC0C0Lne7UiMb',
    'comparison': 'https://modal.com/apps/avisrikumeran/main/ap-yOuxoTkxDoBeMso5YZ5xBd',
    'eval64': 'https://modal.com/apps/avisrikumeran/main/ap-KMIiovWHG4Bt4CyMzjrU5b',
}


def _read(path):
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _number(value, default=0):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def _phase(folder, expected_variants):
    """A plan is not a launch; a worker stage is not a recovered complete result."""
    plan = _read(folder / 'plan.json')
    launch = _read(folder / 'launch.json')
    status = _read(folder / 'remote_status.json')
    result = _read(folder / 'result.json')
    evaluations = result.get('evaluations', {})
    complete = (result.get('stage') == 'completed'
                and isinstance(evaluations, dict)
                and all(isinstance(evaluations.get(name), list) and len(evaluations[name]) == 64
                        for name in expected_variants))
    if complete:
        return 'completed', 'All required outputs on the 64 monitoring questions are saved.', result
    if status.get('stage') == 'failed':
        return 'failed', 'The worker ended before a complete evaluation result was recovered.', {}
    if launch.get('call_id'):
        stage = {
            'loading_model': 'loading the model',
            'baseline_evaluation': 'evaluating original Granite',
            'ranked32_evaluation': 'evaluating the saved BM25 adapter',
            'random32_evaluation': 'evaluating the saved random adapter',
            'full120_training': 'training the 120-example adapter',
            'full120_evaluation': 'evaluating the 120-example adapter',
            'completed': 'recovering the final results',
        }.get(status.get('stage'), 'waiting for the next saved worker update')
        return 'running', 'A Modal function call was submitted; currently ' + stage + '.', {}
    if launch:
        return 'blocked', 'A launch record exists without a confirmed call ID; it must be reconciled before retrying.', {}
    if plan:
        return 'queued', 'The input and plan are prepared. No Modal function call has been submitted.', {}
    return 'not_started', 'No prepared plan or submitted Modal call is recorded.', {}


def _comparable_scores(result, variants):
    evaluations = result.get('evaluations', {})
    if not isinstance(evaluations, dict):
        return {}
    selected = {name: evaluations[name] for name in variants if isinstance(evaluations.get(name), list)}
    if not selected:
        return {}
    id_sets = [{row.get('id') for row in rows} for rows in selected.values()]
    if any(len(ids) != 64 for ids in id_sets) or any(ids != id_sets[0] for ids in id_sets):
        return {}
    try:
        return {name: summarize(rows) for name, rows in selected.items()}
    except (KeyError, TypeError, ValueError):
        return {}


def build(workspace=None):
    workspace = Path(workspace) if workspace is not None else WORKSPACE
    runs = workspace / 'granite_query/cloud/runs'
    completed = []
    current = []

    def add(title, detail, evidence_url=REPORT_URL):
        completed.append({'title': title, 'detail': detail, 'evidence_url': evidence_url})

    preparation = _read(workspace / 'granite_query/ranking/data/prepared/preparation_manifest.json')
    source_manifest = _read(workspace / 'granite_query/ranking/data/raw/source_manifest.json')
    source_url = source_manifest.get('repository') if source_manifest.get('repository') == SOURCE else SOURCE
    source_revision = source_manifest.get('revision')
    if source_revision != SOURCE_REVISION:
        source_revision = SOURCE_REVISION
    train_count = _number(preparation.get('source_files', {}).get('train', {}).get('count'))
    if train_count:
        add('GSM8K training data prepared',
            f'{train_count:,} official training records were prepared. 128 questions were reserved as ranking probes; the remainder supplied candidate questions. This is one dataset, not a survey of all Hugging Face repositories.',
            'https://github.com/AviSrikumeran/granite-query/blob/main/progress/COMPARISON_PLAN.md')
    preview=_read(workspace/'granite_query/ranking/runs/gsm8k_preview_128_seed42/manifest.json')
    eligible_count=_number(preview.get('counts',{}).get('eligible_after_pruning'))
    if eligible_count:
        add('Prompt ranking and duplicate pruning completed',
            f'{eligible_count:,} candidate question prompts were scored by BM25 against 128 training probes after duplicate pruning. This is relevance ranking, not evidence of causal training value, and it does not mean every question was sent to DeepSeek or used for training.',
            'https://github.com/AviSrikumeran/granite-query/blob/main/progress/COMPARISON_PLAN.md')

    smoke = _read(runs / 'granite42_3b_smoke_seed42_v1/result.json')
    if smoke.get('stage') == 'completed':
        add('Granite was actually fine-tuned on Modal',
            f"The A100 smoke test completed {_number(smoke.get('steps'))} LoRA updates on 12 teacher examples, saved the adapter, and reloaded it. This changed adapter parameters; it was not full-parameter training or evidence of generalization improvement. Modal evidence requires account access.",
            APP_URLS['smoke'])

    teacher_pool = _read(runs / 'ranked_random_32_seed42_v1/teacher_summary.json')
    if teacher_pool.get('completed'):
        add('DeepSeek teacher examples generated and verified',
            f"{_number(teacher_pool.get('completed'))} candidate responses were collected through the DeepSeek API; {_number(teacher_pool.get('eligible'))} passed the strict final-answer verifier. Rejected outputs were preserved and excluded from both training arms.")

    comparison = _read(runs / 'ranked_random_32_seed42_v1/result.json')
    metrics = _read(runs / 'ranked_random_32_seed42_v1/metrics.json')
    if comparison.get('stage') == 'completed' and metrics.get('baseline') and metrics.get('arms'):
        arms = metrics['arms']
        ranked, random = arms.get('ranked', {}), arms.get('random', {})
        add('Ranked and random LoRA adapters trained on Modal',
            f"Separate adapters each received 32 examples and 32 updates. Ranked used {_number(ranked.get('supervised_tokens')):,} supervised tokens; random used {_number(random.get('supervised_tokens')):,}. The budgets matched examples and updates, not tokens. Modal evidence requires account access.",
            APP_URLS['comparison'])
        add('First accuracy comparison completed: a tie',
            f"Original Granite: {_number(metrics['baseline'].get('numeric_correct'))}/16. BM25-trained Granite: {_number(ranked.get('numeric_correct'))}/16. Random-trained Granite: {_number(random.get('numeric_correct'))}/16. This single-seed development pilot demonstrated no accuracy gain; the official test set was not used.")

    teacher16 = _read(runs / 'matched_teacher16_v1/summary.json')
    if teacher16.get('completed_count') == 16:
        add('DeepSeek measured on the identical 16 questions',
            f"DeepSeek Pro scored {_number(teacher16.get('numeric_correct'))}/16. The Granite variants scored 13/16 on these same questions. DeepSeek used thinking and a 4096-token cap; Granite used non-thinking and a 512-token cap. API and GPU timing scopes differ.")
    teacher64 = _read(runs / 'matched_eval64_v1/teacher/summary.json')
    if teacher64.get('completed_count') == 64:
        add('DeepSeek side of the new 64-question benchmark completed',
            f"DeepSeek scored {_number(teacher64.get('numeric_correct'))}/64, including {_number(teacher64.get('truncated'))} truncated response counted as a failure. Do not compare this 64-question score with Granite's earlier 16-question score.", RUNS_URL)

    canonical = runs / 'matched_eval64_v1'
    recovered_path=canonical/'recovered_baseline64.json'
    if recovered_path.exists():
        try:
            recovered=json.loads(recovered_path.read_text(encoding='utf-8'))
            expected=set(_read(canonical/'plan.json').get('development_ids',[]))
            if len(recovered)==64 and len(expected)==64 and {r['id'] for r in recovered}==expected:
                counts=summarize(recovered)
                add('Original Granite baseline completed on the same 64 questions',
                    f"Original Granite scored {counts['numeric_correct']}/64, with {counts['truncated']} truncated outputs counted as failures. DeepSeek scored 63/64 on those identical questions. This is a baseline comparison, not evidence that training improved Granite.",APP_URLS['eval64'])
        except (OSError,ValueError,KeyError,TypeError):
            pass
    resume = runs / 'matched_eval64_resume1'
    original_status = _read(canonical / 'remote_status.json')
    resume_plan = _read(resume / 'plan.json')
    resumed = resume_plan.get('resume_from') == 'matched_eval64_v1'
    if original_status.get('stage') == 'failed' or resumed:
        current.append({'title': 'Original 64-question Granite attempt', 'status': 'failed',
                        'detail': 'The original attempt reached its application deadline before completing all checkpoints. Completed phase outputs were preserved; this is not a completed comparison across all checkpoints.'})
    else:
        state, detail, _ = _phase(canonical, ('baseline', 'ranked32', 'random32'))
        current.append({'title': '64-question Granite benchmark', 'status': state, 'detail': detail})
    if resumed or (resume / 'launch.json').exists():
        state, detail, _ = _phase(resume, ('baseline', 'ranked32', 'random32'))
        current.append({'title': 'Resume of unfinished 64-question evaluations', 'status': state,
                        'detail': detail + ' It is a separate attempt and should reuse completed outputs instead of rerunning them.'})
    _, _, eval_result = _phase(canonical, ('baseline', 'ranked32', 'random32'))
    if eval_result:
        add('64-question Granite benchmark fully recovered',
            'All three Granite checkpoint evaluations on the same 64 monitoring questions are saved. This is development monitoring, not the official final test.', RUNS_URL)
    full_state, full_detail, full_result = _phase(runs / 'granite_full120_v1', ('full120',))
    current.append({'title': 'Larger 120-example Granite training round', 'status': full_state,
                    'detail': full_detail + ' Its purpose is to measure whether more verified data helps; improvement is not guaranteed.'})

    pool = _read(runs/'student_valuation_pool512_v1/teacher_summary.json')
    if pool:
        pool_stage=pool.get('stage','unknown')
        current.append({'title':'New verified teacher pool for token-matched controls',
                        'status':'running' if pool_stage=='collecting' else ('completed' if pool_stage=='completed' else 'stopped'),
                        'detail':f"{_number(pool.get('completed'))}/{_number(pool.get('requested'))} separate training questions answered; {_number(pool.get('eligible'))} passed eligibility checks, with {_number(pool.get('supervised_tokens_available')):,} available answer tokens. Uses DeepSeek V4-Pro non-thinking concise responses; original raw answers remain private. Collection is not a completed training experiment."})
    if (workspace/'granite_query/cloud/student_valuation.py').exists():
        current.append({'title':'Student-aware selector and equal-token experiment', 'status':'queued',
                        'detail':'Selection and worker code is implemented; controlled results are pending. The rule uses adaptive development skill gaps and diversity. Each planned arm receives32,768 supervised tokens,32 matched token-weighted updates and the same shuffle policy. This has not yet demonstrated data value.'})

    eval_scores = _comparable_scores(eval_result, ('baseline', 'ranked32', 'random32'))
    full_scores = _comparable_scores(full_result, ('full120',))
    accuracy_improved = False
    if eval_scores.get('baseline'):
        baseline_count = eval_scores['baseline']['numeric_correct']
        candidates = [row['numeric_correct'] for name, row in eval_scores.items() if name != 'baseline']
        if full_scores and full_result.get('plan', {}).get('development_ids') == eval_result.get('plan', {}).get('development_ids'):
            candidates.append(full_scores['full120']['numeric_correct'])
        accuracy_improved = any(value > baseline_count for value in candidates)

    training_evidenced = smoke.get('stage') == 'completed' or comparison.get('stage') == 'completed'
    summary = ('At least one fine-tuned Granite checkpoint scored higher on the shared 64-question development set; robust final-test improvement is not established.'
               if accuracy_improved else
               ('Granite has been fine-tuned on Modal, but no accuracy improvement has been demonstrated yet. Only GSM8K has been processed for this training study.'
                if training_evidenced else
                'No completed Modal fine-tuning result has been recovered in this evidence set. Plans and submitted jobs are reported separately from completed work.'))
    public = {
        'summary': summary,
        'dataset_coverage': [
            {'name': 'GSM8K', 'actual_source': source_url + '/tree/' + source_revision,
             'status': 'processed', 'used_for': 'Ranking probes, teacher questions, LoRA training examples, and development evaluation. Downloaded from the canonical GitHub source; not a claim that all Hugging Face datasets were processed.'},
            {'name': 'Alpaca', 'actual_source': 'Earlier project discussion; no ingestion artifact for this study',
             'status': 'not_used', 'used_for': 'Mentioned in an older direction, then explicitly superseded by the GSM8K scope.'},
            {'name': 'Other previously mentioned Hugging Face repositories', 'actual_source': 'Not fully inventoried in the current evidence',
             'status': 'not_audited', 'used_for': 'No claim that every supplied repository has been reviewed, downloaded, trained on, or evaluated.'},
        ],
        'model': {'name': MODEL, 'revision': REVISION,
                  'training_method': 'LoRA adapters on a pinned 3B Granite checkpoint, on Modal A100 workers; not full-parameter training and not the earlier local 8B model.'},
        'completed': completed,
        'current_work': current,
        'not_done': [
            'Robust or final-test Granite accuracy improvement has not been established.',
            'Multiple Hugging Face dataset/repository evaluation and a complete inventory of supplied links.',
            'Multiple training/selection seeds and matched supervised-token controls.',
            'A completed controlled evaluation of the new student-aware selection method.',
            'Independent explanation-quality/depth evaluation.',
            'Official GSM8K test evaluation of a final frozen checkpoint.',
            'Public Granite model-serving API and Vercel deployment.',
        ],
        'accuracy_improved': accuracy_improved,
        'updated_at_utc': datetime.now(timezone.utc).isoformat(),
    }
    public['dataset_coverage']=[r for r in public['dataset_coverage'] if r['name']!='Other previously mentioned Hugging Face repositories']
    candidates=_read(workspace/'progress/DATASET_CANDIDATES.json')
    for row in candidates.get('sources',[]):
        if all(isinstance(row.get(k),str) for k in ('name','card_url','purpose')):
            public['dataset_coverage'].append({'name':row['name'],'actual_source':row['card_url'],
                'status':row.get('status') if row.get('status') in ('researched_not_imported','inspected_no_eligible_data') else 'researched_not_imported',
                'used_for':row['purpose']})
    public['not_done']=[s.replace('Multiple Hugging Face dataset/repository evaluation and a complete inventory of supplied links.',
        'Training/evaluation on additional math datasets; candidate sources are researched but not imported.') for s in public['not_done']]
    (workspace / 'docs').mkdir(parents=True, exist_ok=True)
    (workspace / 'progress').mkdir(parents=True, exist_ok=True)
    (workspace / 'docs/project-status.json').write_text(json.dumps(public, indent=2) + '\n', encoding='utf-8')
    lines = ['# What Granite Query has actually accomplished', '', public['summary'], '',
             '## Dataset coverage', '']
    for row in public['dataset_coverage']:
        lines += [f"- **{row['name']} — {row['status']}**. {row['used_for']} Source: {row['actual_source']}", '']
    lines += ['## Model actually trained', '', public['model']['name'] + ' at revision ' + public['model']['revision'] + '.', '',
              public['model']['training_method'], '', '## Completed work', '']
    for row in completed:
        lines += [f"### {row['title']}", '', row['detail'], '', f"[Evidence]({row['evidence_url']})", '']
    lines += ['## Current work and failures', '']
    for row in current:
        lines += [f"- **{row['title']} — {row['status']}**. {row['detail']}", '']
    lines += ['## Not completed', ''] + ['- ' + item for item in public['not_done']]
    lines += ['', 'Updated: ' + public['updated_at_utc'], '']
    (workspace / 'progress/ACCOMPLISHMENTS.md').write_text('\n'.join(lines), encoding='utf-8')
    return public


if __name__ == '__main__':
    data = build()
    print(json.dumps({'completed_items': len(data['completed']), 'current_work': data['current_work'],
                      'accuracy_improved': data['accuracy_improved']}))
