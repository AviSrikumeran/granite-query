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
VALUATION_URL = 'https://github.com/AviSrikumeran/granite-query/blob/main/progress/RESEARCH_EXECUTION_PLAN.md'
GRADIENT_URL = 'https://github.com/AviSrikumeran/granite-query/blob/main/progress/NEXT_VALUATION_METHOD.md'
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
    expected_ids=plan.get('development_ids',result.get('plan',{}).get('development_ids',[]))
    complete = (result.get('stage') == 'completed'
                and isinstance(evaluations, dict)
                and all(isinstance(evaluations.get(name), list) and len(evaluations[name]) == 64
                        and len({row.get('id') for row in evaluations[name] if isinstance(row,dict)})==64
                        and (not expected_ids or {row.get('id') for row in evaluations[name]}==set(expected_ids))
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


def _feature_phase(folder):
    plan,launch,status,result=(_read(folder/name) for name in ('plan.json','launch.json','remote_status.json','result.json'))
    protocol=plan.get('protocol',{})
    candidates=len(protocol.get('candidate_ids',[])); targets=len(protocol.get('target_ids',[]))
    checkpoints=len(protocol.get('config',{}).get('checkpoint_updates',[]))
    expected=(candidates+targets)*checkpoints
    public=result.get('public_summary',{})
    complete=(result.get('stage')=='completed' and result.get('projected_features_complete') is True
              and expected>0 and public.get('completed_features')==expected and public.get('total_features')==expected
              and public.get('candidates')==candidates and public.get('selection_development_targets')==targets)
    description=f'{candidates:,} new-cohort candidates and {targets} separate selection-development targets; {checkpoints} planned warmup checkpoints.'
    limitation=' CountSketch gradient alignment is an approximate selection signal, not a measured Granite accuracy gain.'
    if complete:
        return 'completed',f'{expected:,} projected features are saved for {candidates:,} candidates and {targets} held-out selection targets.'+limitation,result
    if result.get('stage') in ('calibration_refused','bounded_stop'):
        reason=('Calibration rejected the projected workload before full collection.' if result['stage']=='calibration_refused'
                else 'The application stopped at its bounded deadline and preserved partial artifacts.')
        return 'stopped',reason+' '+description+' The complete datastore has not been recovered.'+limitation,{}
    if status.get('stage')=='failed':
        return 'failed','The feature worker failed before a complete datastore was recovered. Partial snapshots/features remain separate from completed work.'+limitation,{}
    if launch.get('call_id'):
        stage={'loading_model':'loading pinned Granite','selector_warmup':'warming up the selection adapter',
            'calibration':'checking projected collection time','collecting_candidate':'collecting candidate gradients',
            'collecting_target':'collecting selection-target gradients','checkpoint_features_completed':'finishing a checkpoint datastore',
            'completed':'recovering the feature result'}.get(status.get('stage'),'waiting for a saved worker update')
        saved=_number(status.get('completed_features'))
        return 'running',f'A confirmed Modal call is {stage}; {saved:,}/{expected:,} features reported saved. '+description+limitation,{}
    if launch:
        return 'blocked','Launch record has no confirmed call ID; reconcile it before retrying. '+description+limitation,{}
    if plan:
        return 'queued','Input and feature protocol are frozen; no confirmed Modal function call is recorded. '+description+limitation,{}
    return 'not_started','No feature-stage input or confirmed Modal call is recorded.',{}


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
    multi_teacher=_read(runs/'math_source_teacher1800_v1/teacher_summary.json')
    multi_complete=(multi_teacher.get('stage')=='completed' and multi_teacher.get('completed')==multi_teacher.get('requested')
                    and _number(multi_teacher.get('requested'))>0)
    if multi_teacher:
        teacher_detail=(f"{_number(multi_teacher.get('completed')):,}/{_number(multi_teacher.get('requested')):,} DeepSeek responses saved; "
            f"{_number(multi_teacher.get('eligible')):,} passed complete-response/reference-match checks, supplying "
            f"{_number(multi_teacher.get('supervised_tokens_available')):,} supervised answer tokens. "
            'Sources are SVAMP, TemplateGSM and OpenMath arithmetic augmentation. Human dataset answers, procedural results and synthetic majority-vote references remain distinct; reference match does not independently prove every reasoning step correct. This is teacher-data preparation, not completed Granite training on the new cohort.')
        current.append({'title':'Verify the new multi-source arithmetic teaching pool',
                        'status':'completed' if multi_complete else ('running' if multi_teacher.get('stage')=='collecting' else 'stopped'),
                        'detail':teacher_detail})
        if multi_complete:
            add('New multi-source DeepSeek teaching pool completed',teacher_detail,
                'https://github.com/AviSrikumeran/granite-query/blob/main/progress/MATH_TEACHER.json')
    controlled_results=[]
    controlled=[]
    for seed in (42,43):
        for arm in ('random','valued'):
            arm_folder=runs/f'student_valuation32768_seed{seed}_{arm}_v1'
            if (arm_folder/'plan.json').exists():
                arm_state,arm_detail,arm_result=_phase(arm_folder,(arm,))
                if arm_result:
                    controlled_results.append((arm,arm_result))
                scores=_comparable_scores(arm_result,(arm,))
                controlled.append(dict(seed=seed,arm=arm,state=arm_state,result=arm_result,scores=scores.get(arm)))
                label='skill and diversity' if arm=='valued' else 'random'
                if scores:
                    measured=scores[arm]
                    arm_detail=(f"Measured {measured['numeric_correct']}/64 numeric answers, with {measured['truncated']} truncated outputs counted as failures. "
                        f"Completed {_number(arm_result.get('supervised_tokens')):,} supervised tokens and {_number(arm_result.get('optimizer_updates'))} token-weighted updates. "
                        'This is adaptive development monitoring, not a final-test result.')
                else:
                    arm_detail+=' Frozen plan: 32,768 supervised tokens and 32 token-weighted updates; completed accuracy outputs are still required.'
                current.append({'title':f'Equal-token {label} training, seed {seed}', 'status':arm_state,'detail':arm_detail})
    shared_ids=[{r['id'] for r in item['result']['evaluations'][item['arm']]}
                for item in controlled if item['scores']]
    first_block_complete=(len(controlled)==4 and all(item['scores'] and item['result'].get('supervised_tokens')==32768
        and item['result'].get('optimizer_updates')==32 for item in controlled)
        and all(ids==shared_ids[0] for ids in shared_ids))
    if first_block_complete:
        cells={(item['seed'],item['arm']):item['scores']['numeric_correct'] for item in controlled}
        measurements='; '.join(f"seed {seed}: random {cells[seed,'random']}/64, skill and diversity {cells[seed,'valued']}/64" for seed in (42,43))
        no_advantage=all(cells[seed,'valued']<=cells[seed,'random'] for seed in (42,43))
        interpretation=('The skill heuristic did not beat random in either seed.' if no_advantage
                        else 'These two development seeds require a paired comparison before claiming a robust selection advantage.')
        block_detail=(measurements+'. Every arm completed 32,768 supervised tokens and 32 matched optimizer updates on the same 64 monitoring questions. '
                      +interpretation+' Targeted gradient selection and the new source cohort are separate experiments.')
        add('First equal-token random versus skill experiment completed',block_detail,VALUATION_URL)
    else:
        block_detail='Current controlled results are incomplete or still need protocol reconciliation. A prepared plan or result filename is not proof of a completed matched experiment.'
    if (workspace/'granite_query/cloud/student_valuation.py').exists() or controlled:
        block_state=('completed' if first_block_complete else 'running' if any(r['state']=='running' for r in controlled)
                     else 'failed' if any(r['state']=='failed' for r in controlled) else 'queued')
        current.append({'title':'First student-aware equal-token experiment','status':block_state,'detail':block_detail})
    feature_folder=runs/'gradient_features_math_v1'
    if (feature_folder/'plan.json').exists() or (feature_folder/'launch.json').exists():
        feature_state,feature_detail,feature_result=_feature_phase(feature_folder)
        current.append({'title':'Model-gradient data selection on the new math cohort','status':feature_state,'detail':feature_detail})
        if feature_result:
            add('Student-gradient feature collection completed',feature_detail,GRADIENT_URL)
    if (workspace/'granite_query/cloud/modal_api.py').exists():
        current.append({'title':'Capped Granite API trial', 'status':'queued',
                        'detail':'API source and quota controls are prepared and locally checked. No public model endpoint is deployed. It requires a chosen evaluated checkpoint, completed research GPU work, a serving reservation and an expiring request quota.'})

    eval_scores = _comparable_scores(eval_result, ('baseline', 'ranked32', 'random32'))
    full_scores = _comparable_scores(full_result, ('full120',))
    accuracy_improved = False
    if eval_scores.get('baseline'):
        baseline_count = eval_scores['baseline']['numeric_correct']
        candidates = [row['numeric_correct'] for name, row in eval_scores.items() if name != 'baseline']
        if full_scores and full_result.get('plan', {}).get('development_ids') == eval_result.get('plan', {}).get('development_ids'):
            candidates.append(full_scores['full120']['numeric_correct'])
        for arm,arm_result in controlled_results:
            arm_scores=_comparable_scores(arm_result,(arm,))
            if arm_scores and arm_result.get('plan',{}).get('development_ids')==eval_result.get('plan',{}).get('development_ids'):
                candidates.append(arm_scores[arm]['numeric_correct'])
        accuracy_improved = any(value > baseline_count for value in candidates)

    training_evidenced = smoke.get('stage') == 'completed' or comparison.get('stage') == 'completed'
    summary = ('At least one fine-tuned Granite checkpoint scored higher on the shared 64-question development set; robust final-test improvement is not established.'
               if accuracy_improved else
               ('Granite has been fine-tuned on Modal, but no accuracy improvement has been demonstrated yet. The initial training study used GSM8K; additional source imports and teacher-data stages are tracked separately.'
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
            'Robust or final-test evidence that the new selection method outperforms random.',
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
    cohort=_read(runs/'math_source_cohort1800_v1/manifest.json')
    allowed_repos={'ChilleD/SVAMP','math-ai/TemplateGSM','nvidia/OpenMathInstruct-2'}
    eligible_by_source=multi_teacher.get('eligible_by_source',{})
    origins={'human_dataset_answer':'human dataset answers','procedurally_generated_result':'procedural references',
             'synthetic_majority_vote_answer':'synthetic majority-vote references'}
    for source in cohort.get('sources',[]):
        repo=source.get('repo'); revision=source.get('revision','')
        if repo not in allowed_repos or not isinstance(revision,str) or len(revision)!=40:
            continue
        count=_number(source.get('accepted_prompts'))
        if not count:
            continue
        source_url='https://huggingface.co/datasets/'+repo+'/tree/'+revision
        detail=(f"{count:,} source training prompts imported; {_number(eligible_by_source.get(repo)):,} teacher responses passed the verifier. "
                +'Reference type: '+origins.get(source.get('reference_type'),'explicit source reference origins')+'. New-cohort Granite training/evaluation remains separate from teacher-data collection.')
        item={'name':repo,'actual_source':source_url,'status':'teacher_pool_completed' if multi_complete else 'training_samples_imported',
              'used_for':detail}
        existing=next((row for row in public['dataset_coverage'] if '/datasets/'+repo in row['actual_source']),None)
        if existing:
            existing.update(item)
        else:
            public['dataset_coverage'].append(item)
    public['not_done']=[s.replace('Multiple Hugging Face dataset/repository evaluation and a complete inventory of supplied links.',
        'Completed Granite training/evaluation on the new multi-source math cohort; source imports and teacher collection are separate stages.') for s in public['not_done']]
    inventory=_read(workspace/'progress/HF_SOURCE_INVENTORY.json')
    if inventory.get('actually_imported_sources'):
        public['dataset_coverage'].append({'name':'Broader Hugging Face source audit',
            'actual_source':'https://github.com/AviSrikumeran/granite-query/blob/main/progress/HF_SOURCE_INVENTORY.json',
            'status':'bounded_samples_imported',
            'used_for':f"{_number(inventory.get('actually_imported_sources'))} repositories sampled, with {_number(inventory.get('sample_rows_imported'))} complete training rows across {_number(inventory.get('actually_imported_families'))} declared families. These samples are not entire datasets or evidence of training across all domains."})
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
