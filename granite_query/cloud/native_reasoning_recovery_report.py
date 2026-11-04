"""Read-only report for the separately versioned native mount recovery.

Original failure evidence remains in its original namespace. This module never
polls a provider, reads a ledger, mutates attempts, or exports raw questions,
responses or error text. It never claims a prepared recovery has executed.
Public generation is explicit.
"""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path

from cloud.evaluation_stats import paired

ROOT = Path(__file__).resolve().parent
DEFAULT = ROOT / 'runs/native_reasoning16k_dev200_seed42_mount_v2'
PUBLIC = ROOT.parents[1] / 'progress'
DOCS = ROOT.parents[1] / 'docs'
VERSION = 'native-reasoning-mount-recovery-public-v1'
ORIGINAL_CALL = 'fc-01M6J47BZT6FXBYCC55KC3S6K3'
ROLES = ('baseline', 'concise', 'thinking')
LABELS = {'baseline': 'Fresh untouched Granite', 'concise': 'Concise supervision', 'thinking': 'Native reasoning supervision'}


def _empty(role):
    return {'role': role, 'label': LABELS[role], 'status': 'not_prepared',
        'accuracy_percent': None, 'metrics': None, 'validated_evaluation_outputs': 0,
        'retained_evaluation_count': None, 'actual_supervised_tokens': None,
        'actual_optimizer_updates': None, 'planned_evaluation_count': 200}


def _original(api, output, design):
    """Verify original byte bindings and explicit reviewed execution evidence."""
    source = design['migration_source']
    original = api.safe(api.PRIVATE / source['original_output'])
    folder = api.safe(original / 'arms' / source['original_baseline_run_id'])
    files = {
        'original_design_sha256': original / 'design.json',
        'original_manifest_sha256': original / 'study_manifest.json',
        'original_launch_sha256': folder / 'launch.json',
        'original_provider_terminal_sha256': folder / 'provider_terminal.json',
        'original_call_graph_sha256': folder / 'first_observed_call_graph.private.json',
        'original_error_sha256': folder / 'first_observed_provider_error.private.log',
    }
    if any(api.sha(path) != source.get(key) for key, path in files.items()):
        raise ValueError('Original attempt evidence bytes differ from recovery design')
    if api.read(original / 'design.json').get('source_sha256') != source.get('original_source_sha256'):
        raise ValueError('Original source inventory differs')
    launch = api.read(folder / 'launch.json')
    terminal = api.read(folder / 'provider_terminal.json')
    graph = api.read(folder / 'first_observed_call_graph.private.json')
    call = source.get('original_call_id')
    if (call != ORIGINAL_CALL or launch.get('call_id') != call or terminal.get('call_id') != call
            or terminal.get('kind') != 'failed' or terminal.get('claim_id') != launch.get('claim_id')
            or terminal.get('intent_sha256') != launch.get('intent_sha256')
            or graph.get('queried_call_id') != call
            or not any(item.get('function_call_id') == call and item.get('status') == 'FAILURE'
                for item in graph.get('inputs', []) if isinstance(item, dict))):
        raise ValueError('Original provider failure identity differs')
    review = api.read(output / 'review_recovery.json')
    if (review.get('reviewed') is not True or review.get('phase') != 'recovery'
            or review.get('design_sha256') != api.sha(output / 'design.json')
            or review.get('source_sha256') != design.get('source_sha256')
            or any(review.get(key) is not True for key in ('pre_model_failure_verified', 'remote_owner_absent', 'remote_artifacts_absent'))
            or type(review.get('validated_outputs')) is not int or review['validated_outputs'] != 0):
        raise ValueError('Explicit reviewed pre-model/remote-absence evidence missing')
    return {'status': 'failed_pre_model_attempt_verified', 'call_id': call,
        'validated_evaluation_outputs': 0, 'accuracy_percent': None,
        'failure_category': 'artifact_mount_preflight', 'recovery_evidence_verified': True,
        'training_or_evaluation_completed': False,
        'evidence_sha256': {key: source[key] for key in files},
        'recovery_review_sha256': api.sha(output / 'review_recovery.json'),
        'detail': 'The original call failed before the reviewed remote-owner, model-loading and evaluation stages. Its original failure is retained; it produced 0 validated evaluation outputs.'}


def _job(api, controller, job):
    role, folder = job['role'], job['folder_path']
    public = dict(_empty(role), status='prepared')
    if (folder / 'dispatch.json').exists(): public['status'] = 'dispatch_claimed'
    if (folder / 'launch.json').exists(): public['status'] = 'running_or_awaiting_terminal'
    if not (folder / 'provider_terminal.json').exists(): return public, None
    dispatch = controller._dispatch(job)
    launch = api.validate_launch(folder, job, dispatch, api.read(folder / 'launch.json'))
    terminal = api.read(folder / 'provider_terminal.json')
    if (terminal.get('call_id') != launch['call_id'] or terminal.get('claim_id') != dispatch['claim_id']
            or terminal.get('intent_sha256') != dispatch['intent_sha256']):
        raise ValueError('Recovery provider terminal belongs to another actual call')
    public['call_id'] = launch['call_id']
    if terminal.get('kind') != 'completed':
        public['status'] = 'failed_or_incomplete'
        partial = folder / 'provider_result.json'
        if partial.exists() and terminal.get('partial_result_sha256') == api.sha(partial):
            value = api.read(partial); count = value.get('retained_evaluation_count')
            if type(count) is int and 0 <= count <= 200: public['retained_evaluation_count'] = count
        return public, None
    if (terminal.get('result_sha256') != api.sha(folder / 'result.json')
            or terminal.get('raw_validation_sha256') != api.sha(folder / 'raw_validation.json')):
        raise ValueError('Recovery terminal/result/raw proof bytes differ')
    result = api.read(folder / 'result.json')
    if (result.get('dispatch') != dispatch or result.get('dispatch_sha256') != api.digest(dispatch)
            or result.get('call_id') != launch['call_id'] or result.get('arm') != role
            or result.get('protocol_hash') != job['plan']['protocol_hash']):
        raise ValueError('Recovery result is not bound to this versioned dispatch')
    metrics = api.validate_result(job, result)
    proof = api.read(folder / 'raw_validation.json')
    if (proof.get('raw_batches_verified') != 25 or proof.get('fixed_denominator') != 200
            or proof.get('metrics') != metrics or proof.get('dispatch_sha256') != api.digest(dispatch)):
        raise ValueError('Recovery raw replay proof is incomplete')
    arm = job['data'].get('arm')
    public.update(status='completed', accuracy_percent=metrics['numeric_correct'] / 2,
        metrics=metrics, validated_evaluation_outputs=200, retained_evaluation_count=200,
        actual_supervised_tokens=result['supervised_tokens'], actual_optimizer_updates=result['optimizer_updates'],
        unique_teaching_questions=len(arm['training']) if arm else 0,
        result_sha256=terminal['result_sha256'], raw_validation_sha256=terminal['raw_validation_sha256'],
        provider_terminal_receipt_verified=True)
    return public, result['evaluations'][role]


def _migration(api, output, design):
    """Validate only the recorded transfer; deliberately do not open a ledger."""
    record = api.read(output / 'migration.json')
    body = {key: value for key, value in record.items() if key != 'migration_sha256'}
    source = design['migration_source']
    if (record.get('version') != api.MIGRATION_VERSION or record.get('migration_sha256') != api.digest(body)
            or record.get('original_envelope_id') != Path(source['original_output']).name + '-envelope'
            or record.get('new_envelope_id') != output.name + '-envelope'
            or type(record.get('migrated_usd')) not in (int, float) or record['migrated_usd'] != 5.25
            or record.get('new_reservation_created') is not False
            or record.get('old_failed_child_run_id') != source['original_baseline_run_id']
            or type(record.get('old_failed_child_allowance_held_usd')) not in (int, float)
            or record['old_failed_child_allowance_held_usd'] != 1.75
            or record.get('original_failure') != source
            or record.get('new_design_sha256') != api.sha(output / 'design.json')
            or record.get('new_manifest_sha256') != api.sha(output / 'study_manifest.json')
            or record.get('recovery_review_sha256') != api.sha(output / 'review_recovery.json')
            or record.get('new_source_sha256') != design['source_sha256']
            or record.get('remote_owner_absent') is not True or record.get('remote_artifacts_absent') is not True
            or type(record.get('validated_outputs')) is not int or record['validated_outputs'] != 0):
        raise ValueError('Recorded unused-envelope migration bindings differ')
    stamp = datetime.fromisoformat(record['created_at_utc'].replace('Z', '+00:00'))
    if stamp.tzinfo is None: raise ValueError('Migration receipt timestamp requires timezone')
    return {'status': 'reviewed_receipt_verified_ledger_not_queried', 'migrated_existing_envelope_usd': 5.25,
        'old_failed_child_allowance_recorded_held_usd': 1.75, 'new_credit_reserved_by_reporter': False,
        'migration_receipt_sha256': api.sha(output / 'migration.json'), 'migration_sha256': record['migration_sha256'],
        'note': 'This verifies the recorded transfer, not current ledger or provider billing. The reporter performs no financial action.'}


def build(output=DEFAULT, *, write=False, control_api=None):
    """Return sanitized local evidence. Dependency injection supports offline tests."""
    value = {'schema_version': 1, 'version': VERSION, 'run_id': Path(output).name,
        'updated_at_utc': datetime.now(timezone.utc).isoformat(),
        'stage': 'recovery_unprepared', 'current_work': {'stage': 'recovery_unprepared',
            'detail': 'A separately versioned mount recovery is being prepared. No new GPU work or accuracy is established.'},
        'original_attempt': {'status': 'failed_original_attempt_reported', 'call_id': ORIGINAL_CALL,
            'validated_evaluation_outputs': 0, 'accuracy_percent': None, 'recovery_evidence_verified': False},
        'jobs': [_empty(role) for role in ROLES], 'comparisons': None, 'teacher': None,
        'protocol': {'teacher_candidate_pairs': 256, 'teacher_output_caps': {'concise': 1024, 'thinking': 4096},
            'loss_tokens_per_adapter': 16384, 'optimizer_updates': 16, 'tokens_per_update': 1024, 'context_limit': 4096,
            'evaluation_count': 200, 'student_evaluation_count': 200, 'evaluation_split': 'GSM8K TRAIN development',
            'native_generation_prefix': 'OPEN', 'enable_thinking': True, 'max_new_tokens': 1024,
            'evaluation_batch_size': 8, 'input_limit': 1536, 'training_seed': 42},
        'budget_migration': {'planned_existing_remaining_envelope_usd': 5.25,
            'status': 'not_verified_by_reporter', 'new_credit_reserved_by_reporter': False},
        'strong_teacher_reference': {'status': 'pending_separate_review_and_funding', 'proposed_thinking_output_cap': 8192},
        'official_test_used': False, 'paid_work_launched_by_reporter': False,
        'limitations': ['The original failed call remains a separate historical attempt; recovery is a new reviewed version, not an automatic retry.',
            'Prepared sources, migrated reservations and dispatch claims are not completed GPU work.',
            'All metrics require the new controller source/input/manifest, actual call, provider-terminal and full raw-replay receipt bindings.',
            'Adaptive 200-question TRAIN development and one training seed; this is separate from prior nonthinking 512-token results.',
            'Equal complete loss tokens do not match example counts, forwarded compute or wall time. This tests a supervision recipe, not ranker superiority.',
            'No guaranteed improvement or intermediate-reasoning correctness is implied.']}
    try:
        api = control_api or importlib.import_module('cloud.native_reasoning_control_v2')
        output = api.safe(output); value['run_id'] = output.name
        if (output / 'design.json').exists():
            design = api.verify_design(output)
            value['design_sha256'] = api.sha(output / 'design.json')
            # The historical helper returns only its explicit sanitized teacher
            # aggregate. Never call the old report builder or old load_jobs.
            from cloud import native_reasoning_report as historical
            value['teacher'] = historical._teacher(api.safe(api.PRIVATE / design['collection']))
            value['original_attempt'] = _original(api, output, design)
            value['stage'] = 'recovery_design_reviewed'
            value['current_work'] = {'stage': value['stage'], 'detail': 'The original pre-model failure and separate recovery design validate. New GPU metrics remain unavailable until the new calls and full receipts complete.'}
            if (output / 'migration.json').exists():
                value['budget_migration'] = _migration(api, output, design)
            if (output / 'study_manifest.json').exists():
                jobs = api.load_jobs(output)
                if len(jobs) != 3 or [job['role'] for job in jobs] != list(ROLES): raise ValueError('Exact three-role recovery manifest required')
                controller = api.Controller(output); public, rows = [], {}
                for job in jobs:
                    try:
                        item, outputs = _job(api, controller, job)
                    except (ValueError, KeyError, TypeError, OSError):
                        item, outputs = dict(_empty(job['role']), status='receipt_validation_failed'), None
                    public.append(item)
                    if outputs is not None: rows[job['role']] = outputs
                value['jobs'] = public
                value['stage'] = 'recovery_prepared_or_active'
                value['current_work'] = {'stage': value['stage'], 'detail': 'The new baseline, concise and reasoning conditions use the same fixed protocol. Pending metrics are unavailable; no old failed attempt is counted as new evaluation.'}
                if all(item['status'] == 'prepared' for item in public):
                    value['stage'] = 'recovery_plans_prepared'
                    value['current_work'] = {'stage': value['stage'], 'detail': 'The three new plans are prepared. No new call receipt establishes GPU execution, and all new metrics remain unavailable. The original failed call is retained separately.'}
                elif any(item['status'] == 'running_or_awaiting_terminal' for item in public):
                    value['stage'] = 'recovery_call_awaiting_terminal_validation'
                    value['current_work'] = {'stage': value['stage'], 'detail': 'A new call acknowledgement exists, but its terminal and complete evaluation receipts are still pending. No pending-run accuracy is published.'}
                elif any(item['status'] == 'dispatch_claimed' for item in public):
                    value['stage'] = 'recovery_dispatch_awaiting_call_receipt'
                    value['current_work'] = {'stage': value['stage'], 'detail': 'A new dispatch intent is recorded. It does not establish GPU completion or accuracy; reconcile the exact call receipt before another dispatch.'}
                if any(item['status'] == 'receipt_validation_failed' for item in public):
                    value['stage'] = 'recovery_receipt_validation_failed'
                    value['current_work'] = {'stage': value['stage'], 'detail': 'A new attempt has incomplete or mismatched receipt bindings. Its accuracy is unavailable until the evidence is reconciled.'}
                if any(item['status'] == 'failed_or_incomplete' for item in public):
                    value['stage'] = 'recovery_attempt_failed_requires_review'
                    value['current_work'] = {'stage': value['stage'], 'detail': 'A new recovery attempt failed or remained incomplete. Preserve its receipts and review before any further dispatch; no partial-denominator accuracy is published.'}
                if set(rows) == set(ROLES):
                    value['comparisons'] = {'concise_minus_baseline': paired(rows['baseline'], rows['concise']),
                        'thinking_minus_baseline': paired(rows['baseline'], rows['thinking']),
                        'thinking_minus_concise': paired(rows['concise'], rows['thinking'])}
                    value['stage'] = 'recovery_all_three_completed_and_validated'
                    value['current_work'] = {'stage': value['stage'], 'detail': 'All three new fixed-200 development results and raw replay receipts validate. The original failed call remains separately recorded.'}
    except ImportError:
        value['stage'] = 'recovery_implementation_pending'
        value['current_work'] = {'stage': value['stage'], 'detail': 'The separate recovery controller is not yet available. No new GPU work or metrics are established.'}
    except (ValueError, KeyError, TypeError, OSError):
        value['stage'] = 'recovery_evidence_requires_reconciliation'
        value['current_work'] = {'stage': value['stage'], 'detail': 'The versioned recovery source or evidence bindings need reconciliation. No new metrics are established.'}
        value['jobs'] = [_empty(role) for role in ROLES]; value['comparisons'] = None
    if write: _publish(value)
    return value


def _publish(value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    for path in (PUBLIC / 'NATIVE_REASONING_RECOVERY.json', DOCS / 'native-reasoning-recovery.json'): _replace(path, raw)
    view = dict(value, report_kind='derived_current_study_view', derived_current_study_view=True,
        source_report='native-reasoning-recovery.json', source_report_sha256=hashlib.sha256(raw).hexdigest(),
        original_historical_report='progress/NATIVE_REASONING_STUDY.json',
        original_historical_journal='progress/NATIVE_REASONING_STUDY.md',
        original_historical_report_url='https://github.com/AviSrikumeran/granite-query/blob/main/progress/NATIVE_REASONING_STUDY.json',
        provider_export=False,
        derivation='Dashboard compatibility view of the canonical sanitized recovery report. The original canonical progress report and journal remain unchanged.')
    _replace(DOCS / 'native-reasoning-study.json', (json.dumps(view, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8'))
    lines = ['# Native reasoning mount recovery', '', value['current_work']['detail'], '',
        f"Original failed call: `{ORIGINAL_CALL}`. Validated evaluation outputs: 0. Its accuracy is unavailable.", '',
        '| New condition | Status | Accuracy |', '|---|---|---|']
    for job in value['jobs']:
        accuracy = f"{job['accuracy_percent']:.1f}%" if job['accuracy_percent'] is not None else 'Unavailable'
        lines.append(f"| {job['label']} | {job['status']} | {accuracy} |")
    lines.extend([''] + ['- ' + text for text in value['limitations']])
    _replace(PUBLIC / 'NATIVE_REASONING_RECOVERY.md', ('\n'.join(lines) + '\n').encode('utf-8'))


def _replace(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True); temporary = path.with_name(path.name + '.recovery-report.pending')
    with temporary.open('wb') as handle: handle.write(raw); handle.flush(); os.fsync(handle.fileno())
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--run', type=Path, default=DEFAULT)
    parser.add_argument('--write', action='store_true'); args = parser.parse_args()
    value = build(args.run, write=args.write)
    print(json.dumps({'stage': value['stage'], 'current_work': value['current_work'],
        'original_failure_verified': value['original_attempt']['recovery_evidence_verified'],
        'completed_new_roles': sum(job['status'] == 'completed' for job in value['jobs'])}))


if __name__ == '__main__': main()
