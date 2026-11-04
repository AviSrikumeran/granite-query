"""Read-only batch32 study report; explicit writes target only its new view.

Source/input/call/terminal/full-seven-batch proof gates precede every accuracy.
The completed V3 baseline remains a successful evaluation with a failed runtime
planning gate, never an execution failure or an inferred model-quality gain.
"""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import re

from cloud import native_reasoning_batch_contract_v4 as contract
from cloud import native_reasoning_recovery_report as common
from cloud.evaluation_stats import paired

ROOT = Path(__file__).resolve().parent
DEFAULT = ROOT / 'runs/native_reasoning16k_dev200_seed42_batch32_v4'
PUBLIC = ROOT.parents[1] / 'progress'
DOCS = ROOT.parents[1] / 'docs'
VERSION = 'native-reasoning-batch32-public-v4'
HEX = re.compile(r'[0-9a-f]{64}\Z')


def public_protocol():
    settings = contract.protocol()
    return {'teacher_candidate_pairs': settings['candidate_count'], 'teacher_output_caps': dict(contract.CAPS),
        'loss_tokens_per_adapter': settings['study_token_budget'], 'optimizer_updates': settings['study_optimizer_updates'],
        'tokens_per_update': settings['tokens_per_update'], 'context_limit': settings['context_limit'],
        'evaluation_count': settings['development_count'], 'student_evaluation_count': settings['development_count'],
        'evaluation_split': 'GSM8K TRAIN development', 'native_generation_prefix': 'OPEN',
        'enable_thinking': settings['enable_thinking'], 'max_new_tokens': settings['max_new_tokens'],
        'evaluation_batch_size': settings['evaluation_batch_size'], 'evaluation_batch_count': settings['evaluation_batch_count'],
        'evaluation_partition': settings['evaluation_partition'], 'input_limit': settings['input_limit'],
        'training_seed': settings['seed'], 'memory_telemetry_optional': True}


def _parent(api, output):
    parent = api.parent_for_report(output)
    if (not isinstance(parent, dict) or parent.get('status') != 'completed'
            or type(parent.get('validated_outputs')) is not int or parent['validated_outputs'] != 200
            or parent.get('runtime_infeasible') is not True or parent.get('accuracy_used_as_gate') is not False
            or not re.fullmatch(r'fc-[A-Za-z0-9-]+', str(parent.get('call_id', '')))
            or not HEX.fullmatch(str(parent.get('result_sha256', '')))
            or not HEX.fullmatch(str(parent.get('calibration_sha256', '')))):
        raise ValueError('Actual completed V3 full200 and failed runtime gate must validate')
    return {'status': 'completed_evaluation_runtime_gate_failed', 'call_id': parent['call_id'],
        'validated_evaluation_outputs': 200, 'evaluation_completed': True, 'execution_failed': False,
        'runtime_gate_passed': False, 'accuracy_used_as_gate': False,
        'result_sha256': parent['result_sha256'], 'calibration_sha256': parent['calibration_sha256'],
        'model_quality_gain_claimed': False,
        'detail': 'The prior V3 baseline validly completed all 200 questions. Its measured runtime failed the planning gate for the subsequent training pair. This does not mean the evaluation failed or that batching improves model quality.'}


def _funding(api, output):
    record = api.read(output / 'funding.json')
    if (record != api.funding_record_for_report(output, record.get('created_at_utc'))
            or record.get('funding_sha256') != api.digest({key: value for key, value in record.items() if key != 'funding_sha256'})
            or record.get('transferred_unused_usd') != 3.5 or record.get('additional_new_reservation_usd') != 1.75
            or record.get('funded_envelope_usd') != 5.25 or record.get('total_commitment_increase_usd') != 1.75
            or record.get('new_reservation_created') is not True or type(record.get('parent_validated_outputs')) is not int
            or record['parent_validated_outputs'] != 200 or record.get('parent_runtime_infeasible') is not True
            or type(record.get('new_batch_size')) is not int or record['new_batch_size'] != 32
            or type(record.get('new_max_new_tokens')) is not int or record['new_max_new_tokens'] != contract.protocol()['max_new_tokens']
            or record.get('accuracy_used_as_gate') is not False):
        raise ValueError('Recorded batch-stage transfer plus new reservation proof differs')
    return {'status': 'actual_receipt_verified_ledger_not_queried', 'transferred_existing_unused_usd': 3.5,
        'additional_new_reservation_usd': 1.75, 'funded_envelope_usd': 5.25,
        'new_reservation_created': True, 'total_commitment_increase_usd': 1.75,
        'new_max_new_tokens': record['new_max_new_tokens'],
        'existing_modal_ceiling_usd': 30, 'additional_cash_claimed': False, 'financial_action_by_reporter': False,
        'funding_receipt_sha256': api.sha(output / 'funding.json'), 'funding_sha256': record['funding_sha256']}


def _job(api, controller, job, parent_call):
    role, folder = job['role'], job['folder_path']
    public = dict(common._empty(role), status='prepared')
    if (folder / 'dispatch.json').exists(): public['status'] = 'dispatch_claimed'
    if (folder / 'launch.json').exists(): public['status'] = 'running_or_awaiting_terminal'
    if not (folder / 'provider_terminal.json').exists(): return public, None
    dispatch = controller._dispatch(job)
    launch = api.validate_launch(folder, job, dispatch, api.read(folder / 'launch.json'))
    terminal = api.read(folder / 'provider_terminal.json')
    if (launch['call_id'] == parent_call or terminal.get('call_id') != launch['call_id']
            or terminal.get('claim_id') != dispatch['claim_id'] or terminal.get('intent_sha256') != dispatch['intent_sha256']):
        raise ValueError('New batch attempt must bind its own actual call')
    public['call_id'] = launch['call_id']
    if terminal.get('kind') != 'completed':
        public['status'] = 'failed_or_incomplete'
        partial = folder / 'provider_result.json'
        if partial.exists() and terminal.get('partial_result_sha256') == api.sha(partial):
            count = api.read(partial).get('retained_evaluation_count')
            if type(count) is int and 0 <= count <= 200: public['retained_evaluation_count'] = count
        return public, None
    if (terminal.get('result_sha256') != api.sha(folder / 'result.json')
            or terminal.get('raw_validation_sha256') != api.sha(folder / 'raw_validation.json')):
        raise ValueError('New result/raw proof bytes changed')
    plan = job['plan']; settings = contract.protocol()
    if any(plan.get(key) != settings[key] for key in ('evaluation_batch_size', 'evaluation_batch_count', 'evaluation_partition',
            'max_new_tokens', 'enable_thinking', 'input_limit')):
        raise ValueError('Current batch/output protocol differs')
    result = api.read(folder / 'result.json')
    if (result.get('dispatch') != dispatch or result.get('dispatch_sha256') != api.digest(dispatch)
            or result.get('call_id') != launch['call_id'] or result.get('arm') != role
            or result.get('protocol_hash') != plan['protocol_hash']):
        raise ValueError('New result does not bind the frozen source/input/dispatch')
    metrics = api.validate_result(job, result)
    proof = api.read(folder / 'raw_validation.json')
    partition = contract.evaluation_batches()
    inventory = result.get('raw_batches')
    if (proof.get('raw_batches_verified') != len(partition) or proof.get('fixed_denominator') != 200
            or proof.get('metrics') != metrics or proof.get('dispatch_sha256') != api.digest(dispatch)
            or not isinstance(inventory, list) or len(inventory) != len(partition)
            or any(entry.get('start') != start or entry.get('stop') != stop or not HEX.fullmatch(str(entry.get('sha256', '')))
                for entry, (start, stop) in zip(inventory, partition))):
        raise ValueError('Exactly seven complete raw batches, including tail8, must validate')
    arm = job['data'].get('arm')
    public.update(status='completed', accuracy_percent=metrics['numeric_correct'] / 2,
        metrics=metrics, validated_evaluation_outputs=200, retained_evaluation_count=200,
        actual_supervised_tokens=result['supervised_tokens'], actual_optimizer_updates=result['optimizer_updates'],
        unique_teaching_questions=len(arm['training']) if arm else 0,
        result_sha256=terminal['result_sha256'], raw_validation_sha256=terminal['raw_validation_sha256'],
        raw_batches_verified=len(partition), provider_terminal_receipt_verified=True)
    # Optional CUDA diagnostics are intentionally not a score/publication gate.
    return public, result['evaluations'][role]


def _calibration(api, output, jobs):
    """Read/recompute the recorded gate, after the exact-seven-batch baseline."""
    from cloud.native_reasoning_config_report import _calibration as verified_runtime_gate
    recorded = api.read(output / 'calibration.json')
    formula = '80+1.25*baseline_generation_seconds+0.0032*forwarded_input_tokens'
    if (recorded.get('formula') != formula
            or any(type(job.get('forwarded_input_tokens')) is not int or job['forwarded_input_tokens'] <= 0 for job in jobs[1:])):
        raise ValueError('Frozen calibration formula or actual exposure forecast counts differ')
    return dict(verified_runtime_gate(api, output, jobs), formula=formula)


def build(output=DEFAULT, *, write=False, control_api=None):
    value = {'schema_version': 1, 'version': VERSION, 'run_id': Path(output).name,
        'updated_at_utc': datetime.now(timezone.utc).isoformat(), 'stage': 'batch32_unprepared',
        'current_work': {'stage': 'batch32_unprepared', 'detail': 'The separate batch32 implementation is prospective. No new study plans, calls or metrics are established by this report.'},
        'completed_parent': {'status': 'not_yet_verified_by_reporter', 'accuracy_percent': None,
            'evaluation_completed': None, 'runtime_gate_passed': None, 'execution_failed': None},
        'protocol': public_protocol(), 'teacher': None,
        'jobs': [common._empty(role) for role in common.ROLES], 'comparisons': None, 'calibration': None,
        'funding': {'status': 'planned_not_verified', 'planned_transferred_existing_unused_usd': 3.5,
            'planned_additional_new_reservation_usd': 1.75, 'planned_envelope_usd': 5.25,
            'existing_modal_ceiling_usd': 30, 'additional_cash_claimed': False, 'financial_action_by_reporter': False},
        'official_test_used': False, 'paid_work_launched_by_reporter': False,
        'limitations': ['The prior V3 evaluation completed successfully; its runtime planning gate failed. Batching changes do not establish a quality gain.',
            f"The new condition changes both batching and the generation cap to {contract.protocol()['max_new_tokens']} tokens. A fresh untouched baseline must share that same inference condition with both adapters; the prior V3 score is not its matched baseline.",
            'The new baseline and both adapters must use the same newly frozen inference protocol and exact 200 TRAIN-development questions.',
            'Pending, failed or receipt-mismatched attempts have no published accuracy; no partial-denominator score is substituted.',
            'Adaptive development and one training seed; paired intervals do not cover training-seed variation or correct for multiple comparisons.',
            'Equal complete loss tokens do not match unique examples or forwarded compute. This compares supervision recipes, not ranker superiority.',
            'CUDA memory telemetry is optional; unavailable measurements remain None and do not invalidate otherwise valid answers or timing.',
            'The new $1.75 reservation is within the existing $30 ceiling, alongside $3.50 of transferred allowance; it is not additional cash.']}
    try:
        api = control_api or importlib.import_module('cloud.native_reasoning_batch_control_v4')
        output = api.safe(output)
        if (output / 'design.json').exists():
            design = api.verify_design(output); value['design_sha256'] = api.sha(output / 'design.json')
            value['completed_parent'] = _parent(api, output)
            from cloud import native_reasoning_report as historical
            value['teacher'] = historical._teacher(api.safe(api.PRIVATE / design['collection']))
            value['stage'] = 'batch32_parent_and_design_verified'
            value['current_work'] = {'stage': value['stage'], 'detail': 'The prior baseline validly completed 200 questions but failed the runtime gate. The new batching design validates; no new student result is complete.'}
            if (output / 'funding.json').exists(): value['funding'] = _funding(api, output)
            if (output / 'study_manifest.json').exists():
                jobs = api.load_jobs(output)
                if len(jobs) != 3 or [job['role'] for job in jobs] != list(common.ROLES): raise ValueError('Exact three-role new manifest required')
                controller = api.Controller(output); public, rows = [], {}
                for job in jobs:
                    try: item, outputs = _job(api, controller, job, value['completed_parent']['call_id'])
                    except (ValueError, KeyError, TypeError, OSError): item, outputs = dict(common._empty(job['role']), status='receipt_validation_failed'), None
                    public.append(item)
                    if outputs is not None: rows[job['role']] = outputs
                value['jobs'] = public; value['stage'] = 'batch32_plans_prepared'
                value['current_work'] = {'stage': value['stage'], 'detail': 'The new batch32 plans are prepared. All pending metrics remain unavailable; a fresh baseline must calibrate the new runtime.'}
                for status, stage, detail in (
                    ('dispatch_claimed', 'batch32_dispatch_awaiting_call_receipt', 'A new dispatch intent exists; it does not establish completed GPU work or accuracy.'),
                    ('running_or_awaiting_terminal', 'batch32_call_awaiting_terminal_validation', 'A new acknowledgement exists. Its complete terminal/raw receipts remain pending; pending-run accuracy is unavailable.'),
                    ('receipt_validation_failed', 'batch32_receipt_validation_failed', 'A new attempt has mismatched or incomplete receipt bindings; its accuracy remains unavailable.'),
                    ('failed_or_incomplete', 'batch32_attempt_failed_requires_review', 'A new batch32 attempt failed or remained incomplete. Preserve its original receipts and review before further dispatch; no partial score is published.')):
                    if any(item['status'] == status for item in public):
                        value['stage'] = stage; value['current_work'] = {'stage': stage, 'detail': detail}
                if public[0]['status'] == 'completed' and (output / 'calibration.json').exists():
                    value['calibration'] = _calibration(api, output, jobs)
                    if all(item['status'] == 'prepared' for item in public[1:]):
                        if value['calibration']['pair_runtime_feasible'] is False:
                            value['stage'] = 'batch32_baseline_complete_pair_runtime_infeasible'
                            value['current_work'] = {'stage': value['stage'],
                                'detail': f"The full 200-question OPEN/{value['protocol']['max_new_tokens']} baseline and seven raw batches validate. Its measured runtime fails the training-pair forecast gate. Accuracy does not override this gate; preserve the completed baseline and review before any new dispatch."}
                        else:
                            value['stage'] = 'batch32_baseline_completed_awaiting_pair_review'
                            value['current_work'] = {'stage': value['stage'],
                                'detail': 'The complete baseline and measured runtime gate validate. Both adapters still require an exact source, funding and calibration review before dispatch.'}
                if set(rows) == set(common.ROLES):
                    value['comparisons'] = {'concise_minus_baseline': paired(rows['baseline'], rows['concise']),
                        'thinking_minus_baseline': paired(rows['baseline'], rows['thinking']),
                        'thinking_minus_concise': paired(rows['concise'], rows['thinking'])}
                    value['stage'] = 'batch32_all_three_completed_and_validated'
                    value['current_work'] = {'stage': value['stage'], 'detail': 'All three new fixed 200 results and seven-batch raw replay proofs validate. The completed V3 parent and earlier failed attempts remain separate history.'}
    except ImportError:
        value['stage'] = 'batch32_implementation_pending'; value['current_work'] = {'stage': value['stage'], 'detail': 'The separate batch32 controller is unavailable; no new metrics are established.'}
    except (ValueError, KeyError, TypeError, AttributeError, OSError):
        value['stage'] = 'batch32_evidence_requires_reconciliation'
        value['current_work'] = {'stage': value['stage'], 'detail': 'The new source, completed-parent or funding bindings need reconciliation; no new metrics are established.'}
        value['jobs'] = [common._empty(role) for role in common.ROLES]; value['comparisons'] = None; value['calibration'] = None
    if write: _publish(value)
    return value


def _publish(value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    for path in (PUBLIC / 'NATIVE_REASONING_BATCH32_V4.json', DOCS / 'native-reasoning-batch32-v4.json'): _replace(path, raw)
    view = dict(value, report_kind='derived_current_study_view', derived_current_study_view=True,
        source_report='native-reasoning-batch32-v4.json', source_report_sha256=hashlib.sha256(raw).hexdigest(), provider_export=False,
        original_historical_report='progress/NATIVE_REASONING_STUDY.json',
        historical_reports=['progress/NATIVE_REASONING_STUDY.json', 'progress/NATIVE_REASONING_RECOVERY.json', 'progress/NATIVE_REASONING_CONFIG_RECOVERY.json'],
        derivation='Current dashboard view of the canonical batch32 report; earlier canonical study and recovery histories are unchanged.')
    _replace(DOCS / 'native-reasoning-study.json', (json.dumps(view, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8'))
    lines = ['# Native reasoning batch32 study', '', value['current_work']['detail'], '',
        'The prior V3 baseline completed evaluation; its runtime planning gate failed. This is not an execution failure or a model-quality improvement claim.', '',
        '| New condition | State | Accuracy |', '|---|---|---|']
    for item in value['jobs']:
        accuracy = f"{item['accuracy_percent']:.1f}%" if item['accuracy_percent'] is not None else 'Unavailable'
        lines.append(f"| {item['label']} | {item['status']} | {accuracy} |")
    lines.extend([''] + ['- ' + text for text in value['limitations']])
    _replace(PUBLIC / 'NATIVE_REASONING_BATCH32_V4.md', ('\n'.join(lines) + '\n').encode('utf-8'))


def _replace(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True); pending = path.with_name(path.name + '.batch-report.pending')
    with pending.open('wb') as handle: handle.write(raw); handle.flush(); os.fsync(handle.fileno())
    pending.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--run', type=Path, default=DEFAULT)
    parser.add_argument('--write', action='store_true'); args = parser.parse_args(); value = build(args.run, write=args.write)
    print(json.dumps({'stage': value['stage'], 'current_work': value['current_work'],
        'completed_new_roles': sum(item['status'] == 'completed' for item in value['jobs'])}))


if __name__ == '__main__': main()
