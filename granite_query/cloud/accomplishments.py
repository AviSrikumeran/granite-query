"""Evidence-derived public accomplishments inventory; never exports private runtime data."""
from datetime import datetime, timezone
import json
import hashlib
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
HUMAN_COHORT_URL = 'https://github.com/AviSrikumeran/granite-query/blob/main/progress/HUMAN_MATH_COHORT.json'
HUMAN_TEACHER_URL = 'https://github.com/AviSrikumeran/granite-query/blob/main/progress/HUMAN_MATH_TEACHER.json'
MODEL = 'ibm-granite/granite-4.2-3b'
REVISION = '4e9c275e232f10211ec88644d106a1f6a1b60e06'
SOURCE = 'https://github.com/openai/grade-school-math'
SOURCE_REVISION = '3101c7d5072418e28b9008a6636bde82a006892c'
APP_URLS = {
    'smoke': 'https://modal.com/apps/avisrikumeran/main/ap-WS6yWYh6OmC0C0Lne7UiMb',
    'comparison': 'https://modal.com/apps/avisrikumeran/main/ap-yOuxoTkxDoBeMso5YZ5xBd',
    'eval64': 'https://modal.com/apps/avisrikumeran/main/ap-KMIiovWHG4Bt4CyMzjrU5b',
    'batched_baseline':'https://modal.com/apps/avisrikumeran/main/ap-8sDpW3oOzIOpKk8VAOWrhj',
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
            'restoring_saved_artifacts':'restoring saved adapters, optimizer snapshots and feature files',
            'calibration':'checking projected collection time','collecting_candidate':'collecting candidate gradients',
            'collecting_target':'collecting selection-target gradients','checkpoint_features_completed':'finishing a checkpoint datastore',
            'completed':'recovering the feature result'}.get(status.get('stage'),'waiting for a saved worker update')
        saved=_number(status.get('completed_features'))
        recovery=_read(folder/'recovery_decision.json')
        verified=_number(recovery.get('completed_features'))
        recovery_valid=(plan.get('resume_from') and recovery.get('protocol_hash')==plan.get('protocol_hash')
            and 0<verified<=expected and recovery.get('remaining_features')==expected-verified)
        if recovery_valid and saved<=verified:
            return 'running',(f'A confirmed continuation call is {stage}. {verified:,} already verified features are being restored or rechecked; '
                'no new missing-feature completions have been reported by this call. '+description+limitation),{}
        return 'running',f'A confirmed Modal call is {stage}; {saved:,}/{expected:,} features reported saved. '+description+limitation,{}
    if launch:
        return 'blocked','Launch record has no confirmed call ID; reconcile it before retrying. '+description+limitation,{}
    if plan:
        return 'queued','Input and feature protocol are frozen; no confirmed Modal function call is recorded. '+description+limitation,{}
    return 'not_started','No feature-stage input or confirmed Modal call is recorded.',{}


def _latest_feature_folder(runs):
    original=runs/'gradient_features_math_v1';initial=_read(original/'plan.json')
    if not initial:
        return original
    known={original.name:(original,0)}
    remaining={p.name:p for p in runs.glob('gradient_features_math*') if p.is_dir() and p.name!=original.name}
    changed=True
    while changed:
        changed=False
        for name,folder in list(remaining.items()):
            plan=_read(folder/'plan.json')
            if (plan.get('resume_from') in known and plan.get('protocol_hash')==initial.get('protocol_hash')
                    and plan.get('protocol')==initial.get('protocol')):
                known[name]=(folder,known[plan['resume_from']][1]+1)
                del remaining[name];changed=True
    return max(known.values(),key=lambda item:(item[1],bool(_read(item[0]/'launch.json').get('call_id')),
        _read(item[0]/'plan.json').get('created_at_utc',''),item[0].name))[0]


def _human_teacher_phase(folder, summary, expected):
    """Describe receipts and lock PID separately from model-training evidence."""
    received, requested = _number(summary.get('completed')), _number(summary.get('requested'))
    stage = summary.get('stage')
    complete = stage == 'completed' and requested == expected and received == expected and expected > 0
    lock = folder / 'collector.lock'
    pid = None
    if lock.exists():
        try:
            raw = lock.read_text(encoding='ascii').strip()
            if raw.isdecimal() and 0 < int(raw) <= 2**32-1:
                pid = int(raw)
        except (OSError, UnicodeError, ValueError):
            pass
    if complete:
        state = 'completed'
    elif stage == 'collecting':
        state = 'running' if pid else 'blocked'
    elif stage in ('prepared_unpaid', 'awaiting_next_chunk'):
        state = 'blocked' if lock.exists() else 'queued'
    elif stage in ('halted', 'stopped'):
        state = 'stopped'
    else:
        state = 'blocked'
    detail = (f"{received:,}/{requested:,} human-reference teaching responses saved; "
        f"{_number(summary.get('eligible')):,} passed complete-response/reference-match/token checks, supplying "
        f"{_number(summary.get('supervised_tokens_available')):,} answer tokens. "
        'Each invocation is limited to one separately funded 512-request chunk. The separate 200-question development holdout is withheld from teacher requests and training selection; it is not the official test. ')
    if pid:
        detail += f'Collector lock records process PID {pid}; the supervisor must verify that process before any resume. '
    elif lock.exists():
        detail += 'A collector lock has no valid recorded PID; reconcile it before another launch. '
    elif stage == 'collecting':
        detail += 'The last summary says collecting, but no collector lock is present; reconcile process and receipt state before resuming. '
    if stage == 'awaiting_next_chunk':
        detail += 'The previous chunk ended; no later chunk is inferred to be running. '
    elif stage == 'prepared_unpaid':
        detail += 'Requests are frozen; this summary records no paid collection launch. '
    detail += 'Arithmetic annotations were checked exactly, while semantic sufficiency and complete ancestry decontamination remain unproven. Teacher collection is not evidence that Granite used these questions or improved.'
    return state, detail, complete


def _watch_snapshot_detail(folder):
    """Publish a narrow recorded-state summary, never infer process liveness."""
    snapshot = _read(folder/'study_watch_state.json')
    if not isinstance(snapshot, dict) or not snapshot:
        return ''
    try:
        stamp = datetime.fromisoformat(snapshot['updated_at_utc']).isoformat()
    except (KeyError, TypeError, ValueError):
        return ''
    stage = snapshot.get('stage')
    if stage == 'stopped':
        description = 'stopped; saved calls require inspection before resuming'
    elif stage == 'watching':
        current = snapshot.get('current', {})
        result = current.get('result', {}) if isinstance(current, dict) else {}
        result = result.get('stage') if isinstance(result, dict) else None
        description = {
            'waiting_for_protected_phase_funding': 'waiting for billing reconciliation and protected phase funding',
            'waiting_for_budget_settlement': 'waiting for billing reconciliation',
            'owned_call_running': 'monitoring its existing GPU call',
            'spawned': 'launched the next separately funded GPU call',
            'approved_grid_completed': 'finished its approved study block; later project stages remain',
        }.get(result, 'checking the bounded study; inspect current artifacts for the next action')
    else:
        return ''
    return f' Unattended controller snapshot at {stamp}: {description}. This is a recorded snapshot, not a live process check.'


def _grid_phase(folder):
    grid=_read(folder/'grid_manifest.json')
    review=_read(folder/'reviewed_for_launch.json')
    budgets=review.get('approved_token_budgets')
    scope=set(budgets) if review.get('reviewed') is True and isinstance(budgets,list) and all(type(b) is int for b in budgets) else None
    scope_total=scope_completed=0
    counts={'completed':0,'running':0,'queued':0,'failed':0,'blocked':0,'not_started':0}
    prepared=0;next_items=[];planned=0
    for descriptor in grid.get('studies',[]):
        study=(folder/descriptor.get('folder','')).resolve()
        if not study.is_relative_to(folder.resolve()):
            raise ValueError('Data-efficiency study path escapes its declared grid')
        manifest=_read(study/'manifest.json')
        jobs=manifest.get('jobs',[])
        expected_jobs=_number(descriptor.get('jobs'),6)
        planned+=expected_jobs
        counts['blocked']+=abs(expected_jobs-len(jobs))
        for job in jobs:
            arm_folder=(study/job.get('folder','')).resolve()
            if not arm_folder.is_relative_to(study):
                raise ValueError('Data-efficiency arm path escapes its study')
            prepared+=int((arm_folder/'plan.json').exists())
            selector=job.get('checkpoint_name',job.get('selector'))
            state,_,result=_phase(arm_folder,(selector,))
            budget=manifest.get('token_budget')
            actual=result.get('plan',{})
            if result and (not isinstance(budget,int) or result.get('supervised_tokens')!=budget
                    or result.get('optimizer_updates')!=budget//1024 or actual.get('checkpoint_name')!=selector
                    or actual.get('selector_name')!=job.get('selector') or actual.get('seed')!=job.get('seed')
                    or actual.get('common_pool_sha256')!=manifest.get('common_pool',{}).get('sha256')):
                state='failed'
            counts[state if state in counts else 'blocked']+=1
            if scope is not None and budget in scope:
                scope_total+=1;scope_completed+=int(state=='completed')
            if state!='completed':
                next_items.append((state,job.get('selector','unknown'),job.get('seed'),budget))
    if not planned:
        return 'blocked','A grid manifest exists, but its arm plans have not been recovered; no completed training is inferred.'
    state=('completed' if counts['completed']==planned and not counts['blocked'] else 'running' if counts['running'] else
           'blocked' if counts['blocked'] else 'failed' if counts['failed'] else 'queued')
    if (scope_total and scope_total==scope_completed and counts['completed']<planned
            and not any(counts[k] for k in ('running','blocked','failed'))):
        state='deferred'
    waiting=counts['queued']+counts['not_started']
    waiting_detail=(f"{waiting} deferred reference {'plan' if waiting==1 else 'plans'}" if state=='deferred'
                    else f'{waiting} queued')
    detail=(f"{prepared}/{planned} arm plans prepared; {counts['completed']} completed, {counts['running']} running, "
            f"{waiting_detail}, {counts['failed']} failed and {counts['blocked']} requiring launch reconciliation. "
            'Random, skill and gradient arms use a separately frozen common pool and matched token budgets; these are separate from the earlier four-arm results. ')
    if state=='deferred':
        detail+=f'The {scope_total} reviewed arms are complete; remaining higher-budget plans are deferred and need a separate review. Later human-reference and reasoning stages remain.'
    elif next_items:
        priority={'running':0,'blocked':1,'failed':2,'queued':3,'not_started':4}
        next_state,selector,seed,budget=min(next_items,key=lambda item:priority.get(item[0],5))
        action=('Poll the existing call for' if next_state=='running' else 'Reconcile the stopped or ambiguous attempt for'
                if next_state in ('blocked','failed') else 'The next prepared arm is')
        detail+=f'{action} {selector}, seed {seed}, {budget:,} supervised tokens. The separately bounded experiment controller owns paid launches.'
    else:
        detail+='All arm results are available for the new-cohort report; final-test evaluation and model serving remain separate stages.'
    return state,detail+_watch_snapshot_detail(folder)


def _human_study_phase(folder, workspace):
    try:
        from .human_study_report import build as report
    except ImportError:
        from human_study_report import build as report
    value=report(study=folder,workspace=workspace,write=False)
    state={'action_required':'blocked','partial':'queued'}.get(value['status'],value['status'])
    jobs=value['jobs']
    outcomes=[]
    for name in ('baseline','random','skill'):
        job=jobs[name];metrics=job.get('metrics')
        outcomes.append(name+': '+(f"{metrics['numeric_correct']}/200" if job['status']=='completed' and metrics else job['status']))
    review=value['runtime_and_review']
    detail=(f"{value['completed_jobs']}/3 validated jobs completed on 200 separate training-split development questions. "
            +'; '.join(outcomes)+'. Each training arm uses 65,536 supervised tokens and 64 updates from the same 1,930-example human-reference pool. '
            +'Baseline runtime calibration: '+review['calibration']['status']+'. Pair review: '+review['pair_review']+'. '
            +'These 200 questions are separate from the earlier 64-question monitoring set. One training seed does not establish robust selection benefit.')
    baseline=jobs['baseline'].get('metrics') if jobs['baseline']['status']=='completed' else None
    improved=[]
    if baseline:
        for name in ('random','skill'):
            job=jobs[name]
            if (value['comparisons'][name+'_vs_baseline']['status']=='completed' and job['status']=='completed'
                    and job.get('metrics') and job['metrics']['numeric_correct']>baseline['numeric_correct']):
                improved.append((name,job['metrics']['numeric_correct'],baseline['numeric_correct']))
    return state,detail,improved


def _grid_development_gain(folder):
    """Recheck private immutable artifacts, never public report counts or filenames.

    A gain versus the zero-training batch8 control is development evidence for
    a checkpoint. It does not establish that selection outperforms random.
    Validated arm completion is tracked separately from gains or baseline readiness.
    """
    if not (folder/'grid_manifest.json').exists():
        return None
    try:
        try:
            from . import data_efficiency_report as report
        except ImportError:
            import data_efficiency_report as report
        report.control.verify(folder)
        grid=report.read(folder/'grid_manifest.json')
        studies=[]
        for descriptor in grid['studies']:
            study=report.private_child(folder,descriptor['folder'])
            manifest=report.read(study/'manifest.json')
            if (manifest['token_budget']!=descriptor['token_budget']
                    or manifest['common_pool']['sha256']!=grid['common_pool_sha256']
                    or manifest['sources']!=grid['sources']):
                raise ValueError('New-grid common cohort differs')
            studies.append((study,manifest))
        study,manifest=studies[0]
        first=report.private_child(study,manifest['jobs'][0]['folder'])
        plan=report.read(first/'plan.json');data=report.read(first/'input.json')
        expected={row['id']:row for row in data['development']}
        base,base_rows=report.baseline_context(folder.parent/'student_baseline_batched64_v1',
            expected_development_sha256=plan['development_source_sha256'],expected_ids=plan['development_ids'],
            expected_gold={key:row['gold_answer'] for key,row in expected.items()},
            expected_prompts={key:row['prompt'] for key,row in expected.items()})
        baseline=base['metrics']['numeric_correct'] if base_rows is not None and base.get('status')=='completed' else None
        improved=[];validated_completed=0
        for study,manifest in studies:
            for job in manifest['jobs']:
                arm_folder=report.private_child(study,job['folder'])
                arm_plan=report.read(arm_folder/'plan.json');arm_data=report.read(arm_folder/'input.json')
                arm_expected={row['id']:row for row in arm_data['development']}
                if (arm_plan['development_source_sha256']!=plan['development_source_sha256']
                        or arm_plan['development_ids']!=plan['development_ids'] or arm_expected!=expected):
                    raise ValueError('New-grid development input differs from matched base')
                public,rows=report.summarize_arm(study,manifest,job)
                if rows is not None:
                    validated_completed+=1
                    if baseline is not None and public['metrics']['numeric_correct']>baseline:
                        improved.append({'selector':job['selector'],'seed':job['seed'],
                            'token_budget':manifest['token_budget'],'numeric_correct':public['metrics']['numeric_correct']})
        return {'baseline_numeric_correct':baseline,'improved':improved,
                'validated_completed_arms':validated_completed}
    except (KeyError,TypeError,ValueError,OSError,IndexError,StopIteration):
        # An incomplete/mutated evidence bundle cannot establish an accuracy gain.
        return None


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
    batch_folder=runs/'student_baseline_batched64_v1'
    if (batch_folder/'plan.json').exists():
        try:
            from .data_efficiency_report import baseline_context
        except ImportError:
            from data_efficiency_report import baseline_context
        development=canonical/'development.jsonl'
        expected_rows=([json.loads(line) for line in development.read_text(encoding='utf-8-sig').split('\n') if line.strip()]
                       if development.exists() else [])
        batch, _=baseline_context(batch_folder,
            expected_development_sha256=hashlib.sha256(development.read_bytes()).hexdigest() if development.exists() else None,
            expected_ids=_read(canonical/'plan.json').get('development_ids') or None,
            expected_gold={r['id']:r['gold_answer'] for r in expected_rows} if expected_rows else None,
            expected_prompts={r['id']:r['prompt'] for r in expected_rows} if expected_rows else None)
        batch_state={'prepared':'queued','ambiguous_launch':'blocked','invalid_plan':'failed','invalid_result':'failed'}.get(batch['status'],batch['status'])
        batch_detail='Evaluation-only plan: untouched pinned Granite, no adapter, the same 64 questions, non-thinking 512-token generation and batch8 evaluation. '
        if batch_state=='completed':
            batch_detail+=f"Completed {_number(batch['metrics'].get('numeric_correct'))}/64 numeric answers, with zero actual training tokens and updates. This matched-batch control is separate from the earlier serial58/64 result."
            add('Untouched Granite batch8 control completed',batch_detail,APP_URLS['batched_baseline'])
        else:
            batch_detail+='The complete matched result is not available; no accuracy is assigned. '+batch.get('detail','')
        current.append({'title':'Untouched Granite control with matched batch8 evaluation','status':batch_state,'detail':batch_detail})

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
            'Sources are SVAMP, TemplateGSM and OpenMath arithmetic augmentation. Human dataset answers, procedural results and synthetic majority-vote references remain distinct; reference match does not independently prove every reasoning step correct. These teacher receipts alone are not completed Granite training; separate validated arm results establish any later training/evaluation.')
        current.append({'title':'Verify the new multi-source arithmetic teaching pool',
                        'status':'completed' if multi_complete else ('running' if multi_teacher.get('stage')=='collecting' else 'stopped'),
                        'detail':teacher_detail})
        if multi_complete:
            add('New multi-source DeepSeek teaching pool completed',teacher_detail,
                'https://github.com/AviSrikumeran/granite-query/blob/main/progress/MATH_TEACHER.json')
    human_cohort = _read(workspace/'progress/HUMAN_MATH_COHORT.json')
    human_teacher = _read(workspace/'progress/HUMAN_MATH_TEACHER.json')
    human_ready = (human_cohort.get('stage') == 'prepared_unpaid'
                   and _number(human_cohort.get('actual_teaching_prompts')) > 0
                   and _number(human_cohort.get('actual_development_holdout')) > 0)
    human_detail = ''
    if human_ready:
        human_detail = (f"{_number(human_cohort.get('actual_teaching_prompts')):,} new GSM training questions and "
            f"{_number(human_cohort.get('actual_development_holdout')):,} separate training-split development questions are frozen. "
            f"{_number(human_cohort.get('actual_valid_capacity')):,} questions passed exact arithmetic-annotation/final-link checks after "
            f"{_number(human_cohort.get('ancestry_exclusions',{}).get('combined_unique_gsm_exclusions')):,} prior-question or detectable-ancestry exclusions. "
            'These checks do not prove semantic correctness; TemplateGSM ancestry uses a conservative proxy and OpenMath lineage is incomplete. No official test questions were used. Data preparation is separate from teacher generation and Granite training.')
        add('New human-reference teaching and development split frozen', human_detail, HUMAN_COHORT_URL)
        current.append({'title':'Future human-reference arithmetic cohort preparation','status':'completed','detail':human_detail})
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
    feature_folder=_latest_feature_folder(runs)
    if (feature_folder/'plan.json').exists() or (feature_folder/'launch.json').exists():
        feature_state,feature_detail,feature_result=_feature_phase(feature_folder)
        if feature_folder.name!='gradient_features_math_v1':
            feature_detail='Separate continuation of the same frozen feature protocol. '+feature_detail
        current.append({'title':'Model-gradient data selection on the new math cohort','status':feature_state,'detail':feature_detail})
        if feature_result:
            add('Student-gradient feature collection completed',feature_detail,GRADIENT_URL)
    grid_folder=runs/'data_efficiency_math_v1'
    if (grid_folder/'grid_manifest.json').exists():
        grid_state,grid_detail=_grid_phase(grid_folder)
        current.append({'title':'New math-cohort data-efficiency training grid','status':grid_state,'detail':grid_detail})
    human_study=runs/'human_study64k_dev200_seed42_v2'
    human_gains=[]
    teacher200=_read(workspace/'progress/DEVELOPMENT_TEACHER200.json')
    if teacher200.get('stage')=='completed_validated':
        detail=(f"DeepSeek scored {_number(teacher200.get('teacher_correct'))}/200 on the same development questions "
                'as original Granite179/200, random-trained174/200 and skill-trained171/200. '
                'All used the same prompt, nonthinking mode and512-token output cap. '
                'This diagnostic controls output budget; strongest-practical DeepSeek remains a separate target. '
                'No Granite accuracy improvement is established. Official test data remains sealed.')
        current.append({'title':'Matched DeepSeek versus Granite on200 development questions','status':'completed','detail':detail})
        add('Matched200-question teacher reference measured',detail,
            'https://github.com/AviSrikumeran/granite-query/blob/main/progress/DEVELOPMENT_TEACHER200.md')
        native=_read(workspace/'progress/NATIVE_REASONING_STUDY.json')
        recovery_native=_read(workspace/'progress/NATIVE_REASONING_RECOVERY.json')
        is_recovery=bool(recovery_native.get('stage') and recovery_native['stage']!='recovery_unprepared')
        if is_recovery:
            native=recovery_native
        config_native=_read(workspace/'progress/NATIVE_REASONING_CONFIG_RECOVERY.json')
        is_config=bool(config_native.get('stage') and config_native['stage']!='config_recovery_unprepared')
        if is_config:
            native=config_native
        batch_native=_read(workspace/'progress/NATIVE_REASONING_BATCH32_V4.json')
        is_batch=bool(batch_native.get('stage') and batch_native['stage']!='batch32_unprepared')
        if is_batch:
            native=batch_native
        config_base=next((job for job in config_native.get('jobs',[]) if job.get('role')=='baseline'),{})
        if config_base.get('status')=='completed' and config_base.get('validated_evaluation_outputs')==200:
            measured=config_base['metrics']
            detail=f"Validated untouched OPEN/1024 baseline: {measured['numeric_correct']}/200, with {measured['truncated']} truncated outputs counted as failures. All25physical raw batches and the provider terminal validate. The training-pair runtime forecast failed, so neither V3adapter launched. The earlier nonthinking512 baseline179/200 remains a separate, stronger practical reference."
            current.append({'title':'Native OPEN1024 baseline and runtime calibration','status':'completed','detail':detail})
            add('Native OPEN1024 baseline measured',detail,'https://github.com/AviSrikumeran/granite-query/blob/main/progress/NATIVE_REASONING_CONFIG_RECOVERY.md')
        if native.get('stage') and native['stage']!='unprepared':
            teacher=native.get('teacher') or {}; jobs=native.get('jobs',[])
            running=(teacher.get('stage')=='collecting' or any(j.get('status')=='running_or_awaiting_terminal' for j in jobs))
            state=('completed' if native['stage'] in ('all_three_completed_and_locally_validated','recovery_all_three_completed_and_validated','config_recovery_all_three_completed_and_validated','batch32_all_three_completed_and_validated') else
                   'blocked' if native['stage'] in ('design_or_source_validation_failed','teacher_collection_halted_requires_reconciliation') else 'running' if running else 'queued')
            count=teacher.get('retained_original_outcomes')
            detail=native.get('current_work',{}).get('detail','Native study preparation.')
            detail+=(f' Paired teacher outcomes retained: {count}/512.' if isinstance(count,int) else '')
            cap=native.get('protocol',{}).get('max_new_tokens',1024)
            detail+=f' Two planned adapters each receive16,384 complete loss tokens/16updates. The fresh baseline and both adapters use native OPEN/{cap} on the same200 TRAIN development questions. This is a supervision-recipe comparison, not a ranking benefit or final-test result.'
            current.append({'title':('Native reasoning transfer: batch32 and2048output tokens' if is_batch else 'Native reasoning transfer: official config recovery' if is_config else 'Native reasoning transfer: versioned mount recovery' if is_recovery else 'Native reasoning transfer: concise versus thinking supervision'),'status':state,'detail':detail})
        else:
            current.append({'title':'Reasoning transfer and learning-curve study design','status':'queued',
                'detail':'Prioritize a separately reviewed, funded experiment that tests learning from useful reasoning examples. Current concise-answer training regressed. More examples or a larger final benchmark cannot guarantee improvement. Keep random controls, measure actual training tokens and protect an honest final evaluation and capped API.'})
    if (human_study/'study_manifest.json').exists():
        human_study_state,human_study_detail,human_gains=_human_study_phase(human_study,workspace)
        current.append({'title':'Human-reference training with separate 200-question development evaluation',
                        'status':human_study_state,'detail':human_study_detail})
    human_teacher_complete = False
    if human_teacher:
        human_state, human_teacher_detail, human_teacher_complete = _human_teacher_phase(
            runs/'human_math_teacher2048_v1', human_teacher,
            _number(human_cohort.get('actual_teaching_prompts'),2048))
        current.append({'title':'Human-reference DeepSeek teaching chunks','status':human_state,'detail':human_teacher_detail})
        if human_teacher_complete:
            add('Human-reference DeepSeek teaching pool completed',human_teacher_detail,HUMAN_TEACHER_URL)
    depth=_read(workspace/'progress/TEACHER_DEPTH_PILOT.json')
    if depth:
        depth_stage=depth.get('stage');received=_number(depth.get('completed_original_calls'))
        depth_state=('completed' if depth_stage=='completed' and received==64 else
                     'running' if depth_stage=='collecting' and (runs/'teacher_depth32_v1/collector.lock').exists() else
                     'queued' if depth_stage=='prepared_unpaid' else 'blocked')
        current.append({'title':'Paired teacher-reasoning feasibility pilot','status':depth_state,
            'detail':f'Last recorded snapshot: {received}/64 original responses across 32 separate training questions; '
                +f"{_number(depth.get('eligible_question_pairs'))} complete, reference-matched pairs fit the student context. "
                +'The separately funded pilot compares concise and thinking outputs under different output caps. '
                +'It prepares data for a future reasoning study; it is not completed Granite training or an accuracy gain.'})
    final_scale=_read(workspace/'progress/FINAL_SCALE_IMPLEMENTATION.json')
    if final_scale.get('stage')=='partial_implementation_not_execution_ready':
        implemented=final_scale.get('implementation_phase')=='executor_controller_fixture_checked'
        current.append({'title':'Larger final benchmark implementation and funding review','status':'queued',
            'detail':('Separate sharded GPU/teacher executors, portable artifact checks, whole-bundle escrow and controller recovery now pass offline software fixtures. A development-only adapter-reload producer is implemented; its funded production entrypoint and actual GPU/PEFT reload are still pending. Actual final benchmark execution and serving remain incomplete. Finish the entrypoint/review, validate the chosen weight bytes on development data and review whole-bundle funding before final selection/freezing or official-test access. No paid call, test access or model endpoint is created by this software status.'
                if implemented else
                'Separate count/shard, receipt, physical-seal and permit-first loader components are locally checked. Sharded GPU/teacher execution, paid dispatch integration and runtime adapter compatibility remain incomplete. Finish those components and review whole-bundle funding before selecting/freezing a checkpoint or accessing official test data. The prepared API follows final evaluation; no new paid call is authorized by this status.')})
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

    grid_gain=_grid_development_gain(grid_folder)
    if grid_gain and grid_gain['improved']:
        accuracy_improved=True
        measurements='; '.join(f"{row['selector']}, seed {row['seed']}, {row['token_budget']:,} tokens: {row['numeric_correct']}/64"
                              for row in grid_gain['improved'])
        add('New-cohort checkpoint measured a development gain',
            measurements+f". Matched untouched batch8 Granite scored {grid_gain['baseline_numeric_correct']}/64 on the same frozen questions and inference protocol. "
            'This is an adaptive development gain, not final-test validation or evidence that a selector beats random.',
            'https://github.com/AviSrikumeran/granite-query/blob/main/progress/DATA_EFFICIENCY_RESULTS.md')
    if human_gains:
        accuracy_improved=True
        for selector,correct,base_correct in human_gains:
            add('Human-reference checkpoint measured a development gain',
                f'{selector} scored {correct}/200 versus the matched untouched baseline {base_correct}/200. '
                'This is single-seed development evidence on the separate human study; final-test validation and a robust selection benefit remain pending.',
                'https://github.com/AviSrikumeran/granite-query/blob/main/progress/HUMAN_STUDY_RESULTS.md')

    validated_multi_source_arms=grid_gain['validated_completed_arms'] if grid_gain else 0
    training_evidenced = (smoke.get('stage') == 'completed' or comparison.get('stage') == 'completed'
                          or validated_multi_source_arms>0)
    summary = ('At least one fine-tuned Granite checkpoint scored higher in a matched training-split development comparison. Final-test validation and a robust selection advantage remain unestablished.'
               if accuracy_improved else
               ('Granite has been fine-tuned on Modal, but no accuracy improvement has been demonstrated yet.'
                if training_evidenced else
                'No completed Modal fine-tuning result has been recovered in this evidence set. Plans and submitted jobs are reported separately from completed work.'))
    if validated_multi_source_arms:
        summary+=f" The new multi-source math cohort has {validated_multi_source_arms} validated Granite training/evaluation {'arm' if validated_multi_source_arms==1 else 'arms'}."
    elif training_evidenced:
        summary+=' The initial training study used GSM8K; additional source imports and teacher-data stages are tracked separately.'
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
            'Robust or final-test evidence that the new selection method outperforms random.',
            'Independent explanation-quality/depth evaluation.',
            'Official GSM8K test evaluation of a final frozen checkpoint.',
            'Public Granite model-serving API and Vercel deployment.',
        ],
        'accuracy_improved': accuracy_improved,
        'updated_at_utc': datetime.now(timezone.utc).isoformat(),
    }
    public['dataset_coverage']=[r for r in public['dataset_coverage'] if r['name']!='Other previously mentioned Hugging Face repositories']
    model_artifacts=_read(workspace/'progress/MODEL_ARTIFACTS.json')
    if (model_artifacts.get('model')==MODEL and model_artifacts.get('revision')==REVISION
            and model_artifacts.get('private_local_snapshots_available') is True
            and len(model_artifacts.get('checkpoint_snapshots',[]))==2):
        public['model']['training_method']+=' Trained adapters are saved in persistent Modal storage; both recent adapters now have private local copies. This dashboard is not connected to a live inference endpoint yet.'
        add('Two recent trained adapters saved and copied locally',
            'Both human-study adapters have verified nine-file private snapshots, including 10.5MB learned-weight files. Each has160q/v tensors and2,621,440trainable adapter parameters after65,536supervised tokens/64updates. The original3B base model plus an adapter are required for inference. Header/value inspection is complete; a fresh GPU reload is pending.',
            'https://github.com/AviSrikumeran/granite-query/blob/main/progress/MODEL_ARTIFACTS.json')
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
    if not validated_multi_source_arms:
        public['not_done'].insert(1,'Completed Granite training/evaluation on the new multi-source math cohort; source imports and teacher collection are separate stages.')
    inventory=_read(workspace/'progress/HF_SOURCE_INVENTORY.json')
    if inventory.get('actually_imported_sources'):
        public['dataset_coverage'].append({'name':'Broader Hugging Face source audit',
            'actual_source':'https://github.com/AviSrikumeran/granite-query/blob/main/progress/HF_SOURCE_INVENTORY.json',
            'status':'bounded_samples_imported',
            'used_for':f"{_number(inventory.get('actually_imported_sources'))} repositories sampled, with {_number(inventory.get('sample_rows_imported'))} complete training rows across {_number(inventory.get('actually_imported_families'))} declared families. These samples are not entire datasets or evidence of training across all domains."})
    if human_ready:
        public['dataset_coverage'].append({'name':'New human-reference GSM training expansion',
            'actual_source':SOURCE+'/tree/'+SOURCE_REVISION,
            'status':'teacher_pool_completed' if human_teacher_complete else 'teaching_and_development_questions_frozen',
            'used_for':human_detail+(f" Current teacher receipts: {_number(human_teacher.get('completed')):,}/{_number(human_teacher.get('requested')):,}. "
                'These artifacts do not themselves evidence Granite training or accuracy improvement.' if human_teacher else '')})
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
