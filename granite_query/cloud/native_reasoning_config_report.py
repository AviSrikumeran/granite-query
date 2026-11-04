"""Explicitly generated V3 config-recovery report; default is read-only.

The two prior canonical study histories remain unchanged. No provider, ledger,
attempt mutation, model loading or public generation runs at import time.
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

from cloud import native_reasoning_recovery_report as previous_report
from cloud.evaluation_stats import paired

ROOT = Path(__file__).resolve().parent
DEFAULT = ROOT / 'runs/native_reasoning16k_dev200_seed42_config_v3_final'
PUBLIC = ROOT.parents[1] / 'progress'
DOCS = ROOT.parents[1] / 'docs'
VERSION = 'native-reasoning-config-recovery-public-v1'
PRIOR_CALLS = ('fc-01M6J47BZT6FXBYCC55KC3S6K3', 'fc-01M6J5XRZP90X3RR879RN2A0QE')
ROLES = previous_report.ROLES
HEX = re.compile(r'[0-9a-f]{64}\Z')


def _history(api, output):
    """Whitelisted projection of the new controller's pure evidence validator."""
    items = api.failure_chain_for_report(output)
    if not isinstance(items, list) or len(items) != 2:
        raise ValueError('Require both retained failed attempts')
    result = []
    for index, item in enumerate(items):
        if (not isinstance(item, dict) or item.get('call_id') != PRIOR_CALLS[index]
                or item.get('status') not in ('failed', 'failed_verified')
                or type(item.get('validated_outputs')) is not int or item['validated_outputs'] != 0
                or item.get('model_loaded') is not False or item.get('evaluation_complete') is not False
                or not HEX.fullmatch(str(item.get('evidence_sha256', '')))):
            raise ValueError('Prior failed-call identity or zero-output evidence differs')
        public = {'attempt': 'v1_mount_preflight' if index == 0 else 'v2_config_preflight',
            'call_id': item['call_id'], 'status': 'failed_and_evidence_verified',
            'validated_evaluation_outputs': 0, 'accuracy_percent': None,
            'model_loaded': False, 'evaluation_complete': False,
            'evidence_sha256': item['evidence_sha256']}
        if index == 1:
            if any(item.get(key) is not True for key in ('mount_verified', 'source_verified', 'tokenizer_verified')):
                raise ValueError('V2 completed startup checks must be positively evidenced')
            public.update(mount_verified=True, source_verified=True, tokenizer_verified=True)
            elapsed = item.get('elapsed_seconds')
            if type(elapsed) in (int, float) and 0 < elapsed <= 1805: public['elapsed_seconds'] = elapsed
        result.append(public)
    return result


def _funding(api, output, design):
    """Only a recorded funding transfer is verified; never opens the ledger."""
    record = api.read(output / 'funding.json')
    expected = api.funding_record_for_report(output, record.get('created_at_utc'))
    if (record != expected or record.get('funding_sha256') != api.digest({key: item for key, item in record.items() if key != 'funding_sha256'})
            or type(record.get('validated_outputs')) is not int or record['validated_outputs'] != 0):
        raise ValueError('Recorded config-stage funding differs from reviewed receipt')
    if (record.get('transferred_unused_usd') != 3.5 or record.get('additional_new_reservation_usd') != 1.75
            or record.get('funded_envelope_usd') != 5.25 or record.get('new_reservation_created') is not True
            or record.get('total_commitment_increase_usd') != 1.75):
        raise ValueError('Config-stage funding must disclose the additional reservation')
    return {'status': 'reviewed_funding_receipt_verified_ledger_not_queried',
        'transferred_existing_unused_usd': 3.5, 'additional_new_reservation_usd': 1.75,
        'funded_envelope_usd': 5.25, 'new_reservation_created': True,
        'total_commitment_increase_usd': 1.75, 'existing_modal_ceiling_usd': 30,
        'additional_cash_claimed': False, 'financial_action_by_reporter': False,
        'funding_receipt_sha256': api.sha(output / 'funding.json'), 'funding_sha256': record['funding_sha256'],
        'note': 'A new $1.75 reservation uses the existing $30 Modal ceiling, alongside $3.50 of transferred unused allowance. This is not additional cash or a fresh budget ceiling. The reporter does not query current billing or ledger balances.'}


def _calibration(api, output, jobs):
    """Recompute the recorded runtime gate without writing or polling anything."""
    base = jobs[0]; folder = base['folder_path']
    result = api.read(folder / 'result.json'); terminal = api.read(folder / 'provider_terminal.json')
    metrics = api.validate_result(base, result); value = api.read(output / 'calibration.json')
    forecasts = {job['role']: round(80 + 1.25 * metrics['latency_seconds_total'] + .0032 * job['forwarded_input_tokens'], 3) for job in jobs[1:]}
    feasible = result['elapsed_seconds'] < 1550 and max(forecasts.values()) <= 1250
    expected = {'design_sha256': api.sha(output / 'design.json'), 'baseline_call_id': terminal['call_id'],
        'baseline_result_sha256': api.sha(folder / 'result.json'), 'raw_validation_sha256': api.sha(folder / 'raw_validation.json'),
        'baseline_elapsed_seconds': result['elapsed_seconds'], 'baseline_generation_seconds': metrics['latency_seconds_total'],
        'baseline_truncated': metrics['truncated'], 'forecast_seconds': forecasts, 'pair_runtime_feasible': feasible,
        'guards': {'training': 1400, 'evaluation': 1600, 'hard': 1800}}
    if (any(value.get(key) != item for key, item in expected.items())
            or type(value.get('pair_runtime_feasible')) is not bool
            or terminal.get('kind') != 'completed' or terminal.get('result_sha256') != expected['baseline_result_sha256']
            or terminal.get('raw_validation_sha256') != expected['raw_validation_sha256']):
        raise ValueError('Recorded calibration is not the actual completed baseline runtime gate')
    return dict(expected, calibration_sha256=api.sha(output / 'calibration.json'), gate_seconds=1250)


def build(output=DEFAULT, *, write=False, control_api=None):
    value = {'schema_version': 1, 'version': VERSION, 'run_id': Path(output).name,
        'updated_at_utc': datetime.now(timezone.utc).isoformat(), 'stage': 'config_recovery_unprepared',
        'current_work': {'stage': 'config_recovery_unprepared', 'detail': 'The separate config-fix study is being prepared. Both earlier attempts remain failed with 0 validated outputs; no new metrics are established.'},
        'prior_attempts': [{'call_id': call, 'status': 'failed_reported_awaiting_evidence_validation',
            'validated_evaluation_outputs': 0, 'accuracy_percent': None} for call in PRIOR_CALLS],
        'jobs': [previous_report._empty(role) for role in ROLES], 'comparisons': None, 'teacher': None,
        'protocol': {'teacher_candidate_pairs': 256, 'teacher_output_caps': {'concise': 1024, 'thinking': 4096},
            'loss_tokens_per_adapter': 16384, 'optimizer_updates': 16, 'tokens_per_update': 1024,
            'context_limit': 4096, 'evaluation_count': 200, 'student_evaluation_count': 200,
            'evaluation_split': 'GSM8K TRAIN development', 'native_generation_prefix': 'OPEN',
            'enable_thinking': True, 'max_new_tokens': 1024, 'evaluation_batch_size': 8,
            'input_limit': 1536, 'training_seed': 42},
        'config_fix': {'scope': 'Versioned correction to the configuration raw-byte check; not a model-quality improvement.',
            'official_config_bytes': 905,
            'official_config_sha256': 'e4f44b9c6924a283f1d1d36057a89f1a04404bf1561fc2c0b64cf98180e72915',
            'model_revision_changed': False},
        'funding': {'status': 'planned_not_verified', 'planned_transferred_existing_unused_usd': 3.5,
            'planned_additional_new_reservation_usd': 1.75, 'planned_envelope_usd': 5.25,
            'existing_modal_ceiling_usd': 30, 'additional_cash_claimed': False, 'financial_action_by_reporter': False},
        'strong_teacher_reference': {'status': 'pending_separate_review_and_funding', 'proposed_thinking_output_cap': 8192},
        'official_test_used': False, 'paid_work_launched_by_reporter': False,
        'limitations': ['Two earlier failed attempts remain separately preserved; this is a new reviewed version, not an automatic retry.',
            'Prepared code and funding reservations do not establish GPU completion or model improvement.',
            'The additional $1.75 is a reservation within the existing $30 ceiling, not additional cash.',
            'All student metrics require exact new controller/input/manifest/dispatch/provider-terminal/full-raw-replay receipts.',
            'Adaptive 200-question TRAIN-development evaluation, one training seed and OPEN/1024 inference; prior nonthinking 512-token results are separate.',
            'Complete 16k-token supervision matches loss-token exposure, not example counts or compute; this is a recipe comparison, not ranker superiority.',
            'No guaranteed improvement or verification of every intermediate reasoning step is implied.']}
    try:
        api = control_api or importlib.import_module('cloud.native_reasoning_control_v3')
        output = api.safe(output)
        if (output / 'design.json').exists():
            design = api.verify_design(output)
            value['design_sha256'] = api.sha(output / 'design.json')
            value['prior_attempts'] = _history(api, output)
            value['original_attempt'] = value['prior_attempts'][0]
            value['most_recent_prior_attempt'] = value['prior_attempts'][1]
            from cloud import native_reasoning_report as historical
            value['teacher'] = historical._teacher(api.safe(api.PRIVATE / design['collection']))
            value['stage'] = 'config_recovery_design_verified'
            value['current_work'] = {'stage': value['stage'], 'detail': 'Both prior failed attempts and the new config-fix design validate. The new study has no completed result yet.'}
            if (output / 'funding.json').exists(): value['funding'] = _funding(api, output, design)
            if (output / 'study_manifest.json').exists():
                jobs = api.load_jobs(output)
                if len(jobs) != 3 or [job['role'] for job in jobs] != list(ROLES): raise ValueError('Require exact three-role new manifest')
                controller = api.Controller(output); public, rows = [], {}
                for job in jobs:
                    try:
                        item, outputs = previous_report._job(api, controller, job)
                        if item.get('call_id') in PRIOR_CALLS:
                            raise ValueError('A retained failed call cannot be reused as a new V3 attempt')
                    except (ValueError, KeyError, TypeError, OSError):
                        item, outputs = dict(previous_report._empty(job['role']), status='receipt_validation_failed'), None
                    public.append(item)
                    if outputs is not None: rows[job['role']] = outputs
                value['jobs'] = public
                value['stage'] = 'config_recovery_plans_prepared'
                value['current_work'] = {'stage': value['stage'], 'detail': 'The new three-arm plans are prepared. Pending metrics are unavailable; neither prior failed call is counted as new evaluation.'}
                if any(item['status'] == 'running_or_awaiting_terminal' for item in public):
                    value['stage'] = 'config_recovery_call_awaiting_terminal_validation'
                    value['current_work'] = {'stage': value['stage'], 'detail': 'A new call acknowledgement exists. Its terminal and complete evaluation receipts are pending, so no pending-run accuracy is published.'}
                elif any(item['status'] == 'dispatch_claimed' for item in public):
                    value['stage'] = 'config_recovery_dispatch_awaiting_call_receipt'
                    value['current_work'] = {'stage': value['stage'], 'detail': 'A new dispatch intent exists; it does not establish completed GPU work or accuracy.'}
                if any(item['status'] == 'receipt_validation_failed' for item in public):
                    value['stage'] = 'config_recovery_receipt_validation_failed'
                    value['current_work'] = {'stage': value['stage'], 'detail': 'A new attempt has mismatched or incomplete receipt bindings. Its accuracy remains unavailable pending reconciliation.'}
                if any(item['status'] == 'failed_or_incomplete' for item in public):
                    value['stage'] = 'config_recovery_attempt_failed_requires_review'
                    value['current_work'] = {'stage': value['stage'], 'detail': 'A new config-recovery attempt failed or remained incomplete. Preserve its receipts and review before any further dispatch; no partial-denominator accuracy is published.'}
                if public[0]['status'] == 'completed' and (output / 'calibration.json').exists():
                    value['calibration'] = _calibration(api, output, jobs)
                    if value['calibration']['pair_runtime_feasible'] is False:
                        value['stage'] = 'config_recovery_baseline_complete_pair_runtime_infeasible'
                        value['current_work'] = {'stage': value['stage'], 'detail': 'The full 200-question OPEN/1024 baseline and raw replay validate. Its measured runtime exceeds the training-pair forecast gate; neither adapter was launched. Preserve this completed baseline and review a separately versioned protocol within the original budget.'}
                    else:
                        value['stage'] = 'config_recovery_baseline_completed_awaiting_pair_review'
                        value['current_work'] = {'stage': value['stage'], 'detail': 'The complete baseline and measured runtime gate validate. Both adapters still require an exact source, funding and calibration review before dispatch.'}
                if set(rows) == set(ROLES):
                    value['comparisons'] = {'concise_minus_baseline': paired(rows['baseline'], rows['concise']),
                        'thinking_minus_baseline': paired(rows['baseline'], rows['thinking']),
                        'thinking_minus_concise': paired(rows['concise'], rows['thinking'])}
                    value['stage'] = 'config_recovery_all_three_completed_and_validated'
                    value['current_work'] = {'stage': value['stage'], 'detail': 'All three new fixed-200 results and raw replay receipts validate. Both earlier failed calls remain separately recorded.'}
    except ImportError:
        value['stage'] = 'config_recovery_implementation_pending'
        value['current_work'] = {'stage': value['stage'], 'detail': 'The separate V3 controller is not yet available. No new GPU work or metrics are established.'}
    except (ValueError, KeyError, TypeError, AttributeError, OSError):
        value['stage'] = 'config_recovery_evidence_requires_reconciliation'
        value['current_work'] = {'stage': value['stage'], 'detail': 'The new source, prior failure or funding bindings need reconciliation. No new metrics are established.'}
        value['jobs'] = [previous_report._empty(role) for role in ROLES]; value['comparisons'] = None
    if write: _publish(value)
    return value


def _publish(value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    for path in (PUBLIC / 'NATIVE_REASONING_CONFIG_RECOVERY.json', DOCS / 'native-reasoning-config-recovery.json'): _replace(path, raw)
    view = dict(value, report_kind='derived_current_study_view', derived_current_study_view=True,
        source_report='native-reasoning-config-recovery.json', source_report_sha256=hashlib.sha256(raw).hexdigest(),
        original_historical_report='progress/NATIVE_REASONING_STUDY.json',
        previous_recovery_historical_report='progress/NATIVE_REASONING_RECOVERY.json',
        historical_reports=['progress/NATIVE_REASONING_STUDY.json', 'progress/NATIVE_REASONING_RECOVERY.json'],
        provider_export=False, derivation='Current dashboard compatibility view of the canonical V3 config recovery; V1 and V2 canonical progress histories remain unchanged.')
    _replace(DOCS / 'native-reasoning-study.json', (json.dumps(view, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8'))
    lines = ['# Native reasoning configuration recovery', '', value['current_work']['detail'], '',
        'Both prior attempts remain failed with 0 validated evaluation outputs and no accuracy.', '',
        'Planned funding: $3.50 transferred unused allowance plus a NEW $1.75 reservation within the original $30 ceiling. This is not additional cash.', '',
        '| New condition | Status | Accuracy |', '|---|---|---|']
    for job in value['jobs']:
        accuracy = f"{job['accuracy_percent']:.1f}%" if job['accuracy_percent'] is not None else 'Unavailable'
        lines.append(f"| {job['label']} | {job['status']} | {accuracy} |")
    if value['jobs'][0]['status'] == 'completed':
        lines.extend(['', '![Two inference conditions, not a training improvement curve](../docs/figures/native-completion-budget.svg)', ''])
    lines.extend([''] + ['- ' + item for item in value['limitations']])
    _replace(PUBLIC / 'NATIVE_REASONING_CONFIG_RECOVERY.md', ('\n'.join(lines) + '\n').encode('utf-8'))


def _replace(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True); temporary = path.with_name(path.name + '.config-report.pending')
    with temporary.open('wb') as handle: handle.write(raw); handle.flush(); os.fsync(handle.fileno())
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--run', type=Path, default=DEFAULT)
    parser.add_argument('--write', action='store_true'); args = parser.parse_args(); value = build(args.run, write=args.write)
    print(json.dumps({'stage': value['stage'], 'current_work': value['current_work'],
        'completed_new_roles': sum(item['status'] == 'completed' for item in value['jobs'])}))


if __name__ == '__main__': main()
