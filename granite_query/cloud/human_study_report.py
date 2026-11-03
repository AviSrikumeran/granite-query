"""Read-only, aggregate-only reporting for the independent human-reference study.

Imports and build() never call providers, read budgets or repair artifacts. Only
build(write=True, workspace=...) writes the two explicit public report files.
"""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
sys.path.insert(0, str(ROOT.parent))
from cloud import human_study_control as control
from cloud.comparison_metrics import summarize
from cloud.evaluation_stats import paired

SELECTORS = ('baseline', 'random', 'skill')
STAGES = {'loading_model', 'student_scoring', 'training', 'adapter_saved',
          'evaluation', 'completed', 'failed', 'queued', 'awaiting_worker_progress'}
CALL_ID = re.compile(r'fc-[A-Za-z0-9-]+')
CLAIM_ID = re.compile(r'[0-9a-f]{32}')
LIMITATIONS = [
    'This is an exploratory seed42 source and curriculum transfer study, not a robust causal ranking claim.',
    'The new200 questions are training-split development questions. Earlier64-question results are separate history and are not joined into this improvement curve.',
    'The unchanged skill selector uses an earlier development weakness signal. Choosing this study after earlier negative results is adaptive research; these200 are not a sealed final test.',
    'Paired bootstrap intervals resample questions, not training seeds. Three comparisons are exploratory and have no multiplicity correction.',
    'Equal supervised tokens and updates do not equalize examples, forwarded input tokens, runtime or selection overhead.',
    'Numeric final-answer scoring and reference qualification do not verify every reasoning step or answer depth.',
    'Latency is amortized batched GPU generation time, not single-request latency. Recorded worker seconds are not a provider bill.',
    'Local receipts show last observed progress only. This reporter does not refresh providers, infer funding or repair ambiguous calls.',
    'The baseline runtime forecast is an explicit planning estimate. Actual worker checks remain1400 seconds training,1600 seconds evaluation and1800 seconds hard timeout.',
]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def finite_number(value, *, positive=False):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and (value > 0 if positive else value >= 0))


def wilson(correct, count):
    z = 1.959963984540054
    proportion = correct / count
    denominator = 1 + z*z/count
    center = (proportion + z*z/(2*count)) / denominator
    half = z * math.sqrt(proportion*(1-proportion)/count + z*z/(4*count*count)) / denominator
    return [100*max(0, center-half), 100*min(1, center+half)]


def optional(folder, name):
    path = folder/name
    return read(path) if path.exists() else None


def identities(study, manifest):
    """Read only identity receipts and reject shared call/claim IDs globally."""
    records = {}
    for job in manifest['jobs']:
        folder = (study/job['folder']).resolve()
        item = {'job': job, 'folder': folder, 'issue': None}
        try:
            for key, name in (('claim', 'human_claim.json'), ('launch', 'launch.json'),
                              ('terminal', 'study_terminal.json'), ('remote', 'remote_status.json')):
                item[key] = optional(folder, name)
                if item[key] is not None and not isinstance(item[key], dict):
                    raise ValueError('Receipt must be an object')
        except (ValueError, OSError, UnicodeError):
            item['issue'] = 'unreadable_identity_receipt'
        records[job['selector']] = item
    for kind, key in (('claim', 'claim_id'), ('launch', 'call_id')):
        groups = {}
        for selector, item in records.items():
            value = (item.get(kind) or {}).get(key)
            if isinstance(value, str) and value:
                groups.setdefault(value, []).append(selector)
        for selectors in groups.values():
            if len(selectors) > 1:
                for selector in selectors:
                    records[selector]['issue'] = 'duplicate_'+key
    return records


def validate_completed(job, plan, data, result):
    """Strict complete-result contract; no partial result can earn an accuracy."""
    selector = job['selector']
    budget = job['token_budget']
    updates = budget//1024
    arm = data.get('arm')
    if (not isinstance(result, dict) or result.get('stage') != 'completed'
            or result.get('run_id') != job['run_id'] or result.get('plan') != plan
            or result.get('arm') != (arm['arm'] if arm else 'evaluation_only')
            or type(result.get('supervised_tokens')) is not int or result['supervised_tokens'] != budget
            or type(result.get('optimizer_updates')) is not int or result['optimizer_updates'] != updates
            or result.get('held_out_test_used') is not False
            or set(result.get('evaluations', {})) != {selector}
            or not finite_number(result.get('elapsed_seconds'), positive=True)
            or result['elapsed_seconds'] > 1805):
        raise ValueError('Completed worker identity or exposure differs')
    losses = result.get('weighted_losses')
    if not isinstance(losses, list) or len(losses) != updates or any(not finite_number(x) for x in losses):
        raise ValueError('Completed optimizer history differs')
    rows = result['evaluations'][selector]
    expected = data['development']
    if (not isinstance(rows, list) or len(rows) != 200
            or [r['id'] for r in rows] != [r['id'] for r in expected]
            or len({r['id'] for r in rows}) != 200):
        raise ValueError('Completed evaluation question identities differ')
    for row, reference in zip(rows, expected):
        if (str(row['gold_answer']) != str(reference['gold_answer'])
                or not isinstance(row.get('response'), str) or type(row.get('truncated')) is not bool
                or type(row.get('generated_tokens')) is not int or not 0 <= row['generated_tokens'] <= 512
                or type(row.get('batch_size')) is not int or row['batch_size'] != 8
                or not finite_number(row.get('batch_elapsed_seconds'))
                or not finite_number(row.get('elapsed_seconds'))
                or not math.isclose(row['elapsed_seconds'], row['batch_elapsed_seconds']/row['batch_size'], rel_tol=1e-9)):
            raise ValueError('Completed evaluation reference or generation differs')
    for offset in range(0, len(rows), 8):
        batch = rows[offset:offset+8]
        if any(not math.isclose(row['batch_elapsed_seconds'], batch[0]['batch_elapsed_seconds'], rel_tol=1e-9)
               for row in batch):
            raise ValueError('Completed batch timing is inconsistent within a frozen batch8')
    if sum(row['elapsed_seconds'] for row in rows) > result['elapsed_seconds'] + .001:
        raise ValueError('Generation wall time exceeds the enclosing worker duration')
    return rows


def summarize_job(item, manifest_hash):
    job, folder = item['job'], item['folder']
    plan, data = read(folder/'plan.json'), read(folder/'input.json')
    forecast = job['forecast']
    public = {'selector': job['selector'], 'seed': 42, 'status': 'queued',
        'observation': 'No unique local dispatch receipt is present.',
        'planned_supervised_tokens': job['token_budget'], 'planned_optimizer_updates': job['token_budget']//1024,
        'planned_exposure': forecast if job['selector'] != 'baseline' else
            {'examples': 0, 'response_windows': 0, 'forwarded_input_tokens': 0, 'supervised_tokens': 0, 'updates': 0},
        'actual_supervised_tokens': None, 'actual_optimizer_updates': None, 'actual_exposure': None,
        'metrics': None, 'accuracy_percent': None, 'question_wilson_95_interval_percent': None,
        'worker_elapsed_seconds': None, 'observed_supervised_tokens': None, 'observed_optimizer_updates': None,
        'unique_call_observed': False, 'protocol_hash': job['protocol_hash'], 'result_sha256': None,
        'last_observed_worker_stage': None}

    def unavailable(status, reason):
        public.update(status=status, observation=reason)
        return public, None

    if item['issue']:
        return unavailable('ambiguous', item['issue'])
    claim, launch, terminal, remote = (item.get(k) for k in ('claim', 'launch', 'terminal', 'remote'))
    if not any(x is not None for x in (claim, launch, terminal)):
        if (folder/'result.json').exists() or remote is not None:
            return unavailable('ambiguous', 'orphaned_output_without_dispatch_identity')
        return public, None
    if (not claim or not CLAIM_ID.fullmatch(str(claim.get('claim_id', '')))
            or claim.get('run_id') != job['run_id'] or claim.get('protocol_hash') != job['protocol_hash']
            or claim.get('study_manifest_sha256') != manifest_hash):
        return unavailable('ambiguous', 'missing_or_mismatched_unique_claim')
    if (not launch or launch.get('run_id') != job['run_id']
            or not CALL_ID.fullmatch(str(launch.get('call_id', '')))):
        return unavailable('ambiguous', 'claim_without_complete_matching_call_receipt')
    call_id = launch['call_id']
    public['unique_call_observed'] = True
    if remote:
        if remote.get('run_id', job['run_id']) != job['run_id']:
            return unavailable('ambiguous', 'remote_observation_identity_differs')
        stage = remote.get('stage')
        if not isinstance(stage, str):
            return unavailable('ambiguous', 'saved_worker_stage_is_not_a_string')
        public['last_observed_worker_stage'] = stage if stage in STAGES else 'unknown'
        for source, target, maximum in (('supervised_tokens', 'observed_supervised_tokens', job['token_budget']),
                ('updates', 'observed_optimizer_updates', job['token_budget']//1024)):
            value = remote.get(source)
            if type(value) is int and 0 <= value <= maximum:
                public[target] = value
    if terminal is None:
        if (folder/'result.json').exists():
            return unavailable('ambiguous', 'result_awaits_matching_durable_terminal_receipt')
        if remote and remote.get('stage') == 'failed':
            return unavailable('failed', 'saved_worker_failure_awaits_terminal_reconciliation')
        return unavailable('queued' if remote and remote.get('stage') == 'queued' else 'running',
            'Unique submitted call; this is last observed local progress, not a live provider check.')
    if terminal.get('call_id') != call_id or terminal.get('kind') not in ('completed', 'failed'):
        return unavailable('ambiguous', 'terminal_call_identity_or_kind_differs')
    if terminal.get('result_sha256'):
        if not (folder/'result.json').exists() or control.sha(folder/'result.json') != terminal['result_sha256']:
            return unavailable('ambiguous', 'terminal_result_hash_differs')
    if terminal['kind'] == 'failed':
        return unavailable('failed', 'confirmed_failed_terminal_receipt')
    if remote and remote.get('stage') == 'failed':
        return unavailable('ambiguous', 'completed_receipt_conflicts_with_saved_worker_failure')
    if not terminal.get('result_sha256'):
        return unavailable('ambiguous', 'completed_terminal_has_no_result_hash')
    try:
        result = read(folder/'result.json')
        rows = validate_completed(job, plan, data, result)
        metrics = summarize(rows)
    except (KeyError, TypeError, ValueError, OSError, UnicodeError, ArithmeticError):
        return unavailable('failed', 'completed_result_failed_exact200_contract')
    public.update(status='completed', observation='Unique terminal call and all200 development outcomes validated.',
        actual_supervised_tokens=result['supervised_tokens'], actual_optimizer_updates=result['optimizer_updates'],
        actual_exposure=public['planned_exposure'], metrics=metrics,
        accuracy_percent=100*metrics['numeric_correct']/200,
        question_wilson_95_interval_percent=wilson(metrics['numeric_correct'], 200),
        worker_elapsed_seconds=result['elapsed_seconds'], result_sha256=terminal['result_sha256'])
    return public, rows


def calibration_status(study, manifest, records, jobs):
    public = {'status': 'pending_baseline', 'pair_runtime_feasible': None, 'forecast_seconds': None,
        'planning_forecast_limit_seconds': 1250, 'planning_completion_guard_seconds': 1550,
        'actual_worker_guards_seconds': {'training': 1400, 'evaluation': 1600, 'hard_timeout': 1800}}
    path = study/'calibration.json'
    if jobs['baseline']['status'] != 'completed':
        if path.exists():
            public['status'] = 'unverified_without_completed_baseline'
        return public
    public['status'] = 'pending_calibration_artifact'
    if not path.exists():
        return public
    try:
        value = read(path)
        if not isinstance(value, dict):
            raise ValueError('Calibration must be an object')
        base = jobs['baseline']
        forecasts = {j['selector']: round(80 + 1.25*base['metrics']['latency_seconds_total']
            + .0032*j['forecast']['forwarded_input_tokens'], 3) for j in manifest['jobs'] if j['selector'] != 'baseline'}
        expected = {'schema_version': 1, 'study_manifest_sha256': control.sha(study/'study_manifest.json'),
            'baseline_call_id': records['baseline']['launch']['call_id'],
            'baseline_result_sha256': base['result_sha256'],
            'baseline_elapsed_seconds': base['worker_elapsed_seconds'],
            'baseline_generation_seconds': base['metrics']['latency_seconds_total'],
            'baseline_truncated': base['metrics']['truncated'], 'forecast_seconds': forecasts,
            'formula': manifest['calibration_contract']['formula'],
            'pair_runtime_feasible': base['worker_elapsed_seconds'] < 1550 and max(forecasts.values()) <= 1250,
            'actual_worker_guards': {'training': 1400, 'evaluation': 1600, 'hard_timeout': 1800}}
        if {k: v for k, v in value.items() if k != 'created_at_utc'} != expected:
            raise ValueError('Calibration differs from observed baseline')
        public.update(status='validated', pair_runtime_feasible=expected['pair_runtime_feasible'],
                      forecast_seconds=forecasts)
    except (KeyError, TypeError, ValueError, OSError, UnicodeError):
        public['status'] = 'invalid_calibration_artifact'
    return public


def review_status(study, manifest, phase, calibration):
    if phase == 'pair' and (calibration['status'] != 'validated' or not calibration['pair_runtime_feasible']):
        return 'blocked_by_baseline_calibration'
    path = study/('review_'+phase+'.json')
    if not path.exists():
        return 'pending_review'
    try:
        value = read(path)
        if not isinstance(value, dict):
            raise ValueError('Review must be an object')
        expected = [j['run_id'] for j in manifest['jobs'] if (j['selector'] == 'baseline') == (phase == 'baseline')]
        if (value.get('reviewed') is not True or value.get('phase') != phase
                or value.get('study_manifest_sha256') != control.sha(study/'study_manifest.json')
                or value.get('controller_sha256') != manifest['controller_sha256']
                or value.get('protected_modal_usd') != 5 or value.get('approved_run_ids') != expected
                or phase == 'pair' and value.get('calibration_sha256') != control.sha(study/'calibration.json')):
            raise ValueError('Review does not bind frozen phase')
        return 'reviewed'
    except (KeyError, TypeError, ValueError, OSError, UnicodeError):
        return 'invalid_review'


def markdown(public):
    lines = ['# Human-reference development study', '',
        'New200 development questions; earlier64-question studies remain separate. Official test data remains sealed.', '',
        f"Status: {public['status']}. Validated completed jobs: {public['completed_jobs']}/3.", '',
        '| Checkpoint | Status | Numeric correct | Truncated | Actual answer tokens | Updates | Planned examples | Planned forwarded tokens |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for selector in SELECTORS:
        job = public['jobs'][selector]
        metrics = job['metrics']
        exposure = job['planned_exposure']
        correct = str(metrics['numeric_correct'])+'/200' if metrics else 'unavailable'
        lines.append(f"| {selector} | {job['status']} | {correct} | {metrics['truncated'] if metrics else 'unavailable'} | {job['actual_supervised_tokens'] if job['actual_supervised_tokens'] is not None else 'pending'} | {job['actual_optimizer_updates'] if job['actual_optimizer_updates'] is not None else 'pending'} | {exposure['examples']} | {exposure['forwarded_input_tokens']} |")
    lines += ['', '## Same200 paired comparisons', '']
    for label, value in public['comparisons'].items():
        if value['status'] != 'completed':
            lines.append('- '+label+': unavailable until both complete evaluations validate.')
            continue
        stats = value['statistics']
        low, high = stats['paired_bootstrap_95_interval_pp']
        lines.append(f"- {label}: {stats['difference_percentage_points']:+.2f} percentage points; corrected {stats['corrected']}, regressed {stats['regressed']}; paired question-bootstrap95% [{low:+.2f}, {high:+.2f}] pp; exploratory McNemar p={stats['mcnemar_exact_two_sided_p']:.4f}.")
    gates = public['runtime_and_review']
    lines += ['', '## Runtime calibration and review', '',
        f"Baseline calibration: {gates['calibration']['status']}. Baseline review: {gates['baseline_review']}. Pair review: {gates['pair_review']}.",
        'A separately funded pair still requires a calibrated baseline and exact phase review. This report does not inspect funding or authorize work.', '',
        '## Limits', '', *['- '+text for text in public['limitations']], '',
        'Public outputs contain aggregates and hashes only. Questions, responses, per-question outcomes, credentials, account details and private source paths stay local.', '']
    return '\n'.join(lines)


def write_outputs(public, workspace):
    """Explicit local writes only; no journal mutation, regeneration or publish."""
    workspace = Path(workspace)
    files = [(workspace/'docs/human-study-results.json', json.dumps(public, indent=2, ensure_ascii=False)+'\n'),
             (workspace/'progress/HUMAN_STUDY_RESULTS.md', markdown(public))]
    for path, contents in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name+'.human-report.'+str(os.getpid())+'.tmp')
        for attempt in range(4):
            try:
                temporary.write_text(contents, encoding='utf-8', newline='\n')
                temporary.replace(path)
                break
            except PermissionError:
                if attempt == 3:
                    raise
                time.sleep(.05*(2**attempt))


def build(*, study=control.DEFAULT, workspace=WORKSPACE, write=False, paired_fn=paired):
    """Return sanitized aggregates; writing requires an explicit write=True."""
    study = control.safe_folder(study)
    control.verify(study)
    manifest = read(study/'study_manifest.json')
    manifest_hash = control.sha(study/'study_manifest.json')
    records = identities(study, manifest)
    jobs, outcomes = {}, {}
    for selector in SELECTORS:
        jobs[selector], outcomes[selector] = summarize_job(records[selector], manifest_hash)
    comparisons = {}
    for candidate, reference in (('skill', 'random'), ('random', 'baseline'), ('skill', 'baseline')):
        ready = outcomes[candidate] is not None and outcomes[reference] is not None
        comparisons[candidate+'_vs_'+reference] = {'status': 'completed' if ready else 'unavailable',
            'statistics': paired_fn(outcomes[reference], outcomes[candidate]) if ready else None}
    completed = sum(j['status'] == 'completed' for j in jobs.values())
    statuses = {j['status'] for j in jobs.values()}
    status = ('completed' if completed == 3 else 'action_required' if statuses & {'ambiguous', 'failed'}
              else 'running' if 'running' in statuses else 'partial' if completed else 'queued')
    calibration = calibration_status(study, manifest, records, jobs)
    observed = sum(j['unique_call_observed'] for j in jobs.values())
    public = {'schema_version': 1, 'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'title': 'Human-reference random versus skill development study', 'study_id': manifest['version'],
        'study_manifest_sha256': manifest_hash, 'status': status, 'completed_jobs': completed, 'planned_jobs': 3,
        'official_test_used': False, 'launch_evidence': {'uniquely_observed_calls': observed,
            'ambiguous_jobs': sum(j['status'] == 'ambiguous' for j in jobs.values()),
            'preparation_manifest_is_not_live_launch_status': True},
        'cohort': {'development_count': 200, 'development_source_sha256': manifest['sources']['development'],
            'split': 'train', 'role': 'development', 'legacy64_included': False,
            'legacy64_results_merged': False, 'candidate_examples': 1930, 'available_supervised_tokens': 223827,
            'teacher_pool_sha256': manifest['sources']['teacher_pool'],
            'reference_provenance': 'DeepSeek responses to human GSM training questions, qualified against independent dataset answers; responses are not human-authored.'},
        'protocol': {k: control.COMMON[k] for k in ('model', 'revision', 'seed', 'tokens_per_update',
            'learning_rate', 'lora_r', 'lora_alpha', 'context_limit', 'max_new_tokens',
            'enable_thinking', 'do_sample', 'evaluation_batch_size', 'latency_measurement')},
        'jobs': jobs, 'comparisons': comparisons,
        'runtime_and_review': {'calibration': calibration,
            'baseline_review': review_status(study, manifest, 'baseline', calibration),
            'pair_review': review_status(study, manifest, 'pair', calibration), 'funding_inspected': False},
        'points': [{'selector': selector, 'supervised_tokens': job['actual_supervised_tokens'],
            'numeric_correct': job['metrics']['numeric_correct'], 'count': 200,
            'accuracy_percent': job['accuracy_percent'],
            'question_wilson_95_interval_percent': job['question_wilson_95_interval_percent']}
            for selector, job in jobs.items() if job['status'] == 'completed'],
        'limitations': LIMITATIONS}
    if write:
        write_outputs(public, workspace)
    return public


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, default=control.DEFAULT)
    parser.add_argument('--workspace', type=Path, default=WORKSPACE)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    result = build(study=args.study, workspace=args.workspace, write=args.write)
    print(json.dumps({k: result[k] for k in ('status', 'completed_jobs')}))
