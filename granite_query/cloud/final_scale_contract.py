"""Dependency-free, pre-access design contract for1000/full1319 final questions.

No imports/build/validation read files, datasets, accounts or providers. A digest
seals a proposal, not a checkpoint, access permit, funded job or ready executor.
The CLI prints a contract summary only and never saves or authorizes anything.
"""
import argparse
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import hashlib
import json
import math
import random
import re

VERSION = 'final-scale-contract-v1'
POPULATION = 1319
TARGETS = (1000, 1319)
SEED = 20261110
MODEL = 'ibm-granite/granite-4.2-3b'
REVISION = '4e9c275e232f10211ec88644d106a1f6a1b60e06'
PREFIX = ('Solve the math problem. Explain only the necessary calculation steps concisely. '
          'Finish with #### followed by the numeric final answer.\n\n')
SOURCE_ROLES = ('contract', 'receipts', 'loader', 'granite_executor', 'teacher_executor',
                'checkpoint_validator', 'model_image', 'scoring', 'paired_statistics')
HASH = re.compile(r'[a-f0-9]{64}')
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}')
PRICING = {'modal_a10080_per_second': '0.000694', 'modal_cpu_core_per_second': '0.0000131',
    'modal_gib_per_second': '0.00000222', 'teacher_input_per_million': '1.32',
    'teacher_output_per_million': '3.96', 'modal_source': 'https://modal.com/pricing',
    'teacher_source': 'https://api-docs.deepseek.com/quick_start/pricing/',
    'scope': 'Standard preemptible function rates, no region premium; recheck before execution.'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def require_hash(value):
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise ValueError('Require a lowercase SHA256')
    return value


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Integer is outside the bounded contract')
    return value


def money(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError('Require a finite nonnegative money amount')
    try:
        number = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError('Invalid money amount') from error
    if not number.is_finite() or number < 0:
        raise ValueError('Require finite nonnegative money')
    return number


def amount(value):
    return format(value, 'f')


def _sources(source_hashes, source_roles):
    if not isinstance(source_hashes, dict):
        raise ValueError('Source hashes must be an explicit mapping')
    for name, value in source_hashes.items():
        if not isinstance(name, str) or not NAME.fullmatch(name) or not name.endswith('.py') or '..' in name:
            raise ValueError('Source names must be safe Python basenames')
        require_hash(value)
    if source_roles is None:
        source_roles = {role: [] for role in SOURCE_ROLES}
        if 'final_scale_contract.py' in source_hashes:
            source_roles['contract'] = ['final_scale_contract.py']
    if not isinstance(source_roles, dict) or set(source_roles) != set(SOURCE_ROLES):
        raise ValueError('All required source-role slots must be declared')
    for names in source_roles.values():
        if (not isinstance(names, list) or any(not isinstance(n, str) for n in names)
                or len(names) != len(set(names)) or any(n not in source_hashes for n in names)):
            raise ValueError('Source role inventory differs from source hashes')
    used = {name for names in source_roles.values() for name in names}
    if used != set(source_hashes):
        raise ValueError('Every helper source hash needs a declared role')
    if source_roles['contract'] and 'final_scale_contract.py' not in source_roles['contract']:
        raise ValueError('Contract implementation must be source bound')
    return json.loads(json.dumps(source_hashes)), json.loads(json.dumps(source_roles))


def _selected(value):
    if value is None:
        return None
    fields = {'model', 'revision', 'checkpoint_id', 'adapter_inventory_sha256', 'development_evidence_sha256'}
    if (not isinstance(value, dict) or set(value) != fields or value['model'] != MODEL
            or value['revision'] != REVISION or not isinstance(value['checkpoint_id'], str)
            or not NAME.fullmatch(value['checkpoint_id'])):
        raise ValueError('Selected checkpoint metadata must match the pinned model')
    require_hash(value['adapter_inventory_sha256'])
    require_hash(value['development_evidence_sha256'])
    return dict(value)


def _indices(count, seed):
    return list(range(POPULATION)) if count == POPULATION else sorted(random.Random(seed).sample(range(POPULATION), count))


def _ids(indices):
    return [f'gsm8k:test:{index:05d}' for index in indices]


def build_contract(target_count=1000, *, source_hashes=None, source_roles=None, selected=None,
                   seed=SEED, max_shard_questions=368):
    """Construct metadata only; None selected/incomplete sources remain blocked."""
    integer(target_count, 1000, POPULATION)
    if target_count not in TARGETS:
        raise ValueError('Choose1000 or full1319 before access')
    integer(seed, 0, 2**32-1)
    integer(max_shard_questions, 8, 368)
    if max_shard_questions % 8:
        raise ValueError('Only the final shard may end in a partial batch')
    sources, roles = _sources({} if source_hashes is None else source_hashes, source_roles)
    indices = _indices(target_count, seed)
    shards = []
    for start in range(0, target_count, max_shard_questions):
        stop = min(start+max_shard_questions, target_count)
        subset = indices[start:stop]
        shards.append({'id': f'shard{len(shards):03d}', 'start': start, 'stop': stop,
            'indices': subset, 'indices_sha256': digest(subset), 'question_ids_sha256': digest(_ids(subset)),
            'batch_counts': [min(8, stop-offset) for offset in range(start, stop, 8)]})
    calls = 2*len(shards)
    rate = (Decimal(PRICING['modal_a10080_per_second'])
        + 4*Decimal(PRICING['modal_cpu_core_per_second']) + 32*Decimal(PRICING['modal_gib_per_second']))
    per_call = rate*1922
    teacher = Decimal(target_count)*(2000*Decimal('1.32')+512*Decimal('3.96'))/1000000
    protocol = {'role': 'final_eval_only', 'training_eligible': False,
        'dataset': {'repository': 'openai/grade-school-math',
            'revision': '3101c7d5072418e28b9008a6636bde82a006892c',
            'relative_path': 'grade_school_math/data/test.jsonl',
            'expected_population': POPULATION, 'sample_count': target_count,
            'sampling_seed': seed, 'sampling_algorithm': 'range(1319)' if target_count == POPULATION else
                'sorted(random.Random(seed).sample(range(1319),1000))',
            'indices': indices, 'indices_sha256': digest(indices), 'question_ids_sha256': digest(_ids(indices)),
            'full_test_evaluation': target_count == POPULATION, 'source_split': 'test'},
        'base': {'model': MODEL, 'revision': REVISION}, 'selected': _selected(selected),
        'source_hashes': sources, 'source_roles': roles,
        'inference': {'user_prefix': PREFIX, 'evaluation_batch_size': 8, 'max_new_tokens': 512,
            'enable_thinking': False, 'do_sample': False, 'context_limit': 2048,
            'max_prompt_tokens': 1536, 'over_context_outcome': 'input_limit',
            'same_user_prompt_for_all_roles': True, 'same_ids_for_all_roles': True,
            'latency_scope': 'Granite amortized batch GPU time; teacher API round trips are separate.'},
        'model_roles': {'base': {'questions': target_count, 'training_performed': False},
            'chosen': {'questions': target_count, 'selection_before_access': True},
            'teacher': {'questions': target_count, 'model': 'deepseek-v4-pro', 'max_attempts': target_count,
                'max_tokens': 512, 'thinking_enabled': False, 'max_concurrent_requests': 4,
                'automatic_retries': 0, 'input_token_cap': 2000,
                'input_cap_scope': 'Precommitted request cap to validate after authorized access, not an observed official-test maximum.'}},
        'sharding': {'max_shard_questions': max_shard_questions, 'batch_size': 8,
            'granite_calls': calls, 'max_active_gpus': 1}, 'shards': shards,
        'pricing': dict(PRICING),
        'bounds': {'gpu': 'A100-80GB', 'cpu_cores': 4, 'memory_gib': 32,
            'hard_timeout_seconds': 1800, 'application_guard_seconds': 1600,
            'startup_allowance_seconds': 120, 'scaledown_allowance_seconds': 2,
            'resource_seconds_per_gpu_call': 1922, 'modal_resource_usd_per_second': amount(rate),
            'per_gpu_call_resource_bound_usd': amount(per_call),
            'all_gpu_call_resource_bound_usd': amount(per_call*calls),
            'all_gpu_call_resource_bound_including_recovery_usd': amount(per_call*(calls+1)),
            'gpu_call_reservation_usd': '1.75', 'modal_compute_bundle_usd': amount(Decimal('1.75')*calls),
            'max_gpu_recovery_calls': 1, 'modal_recovery_allowance_usd': '1.75',
            'modal_bundle_including_recovery_usd': amount(Decimal('1.75')*(calls+1)),
            'teacher_input_tokens_bound': 2000*target_count, 'teacher_output_tokens_bound': 512*target_count,
            'granite_input_tokens_bound_per_checkpoint': 1536*target_count,
            'granite_output_tokens_bound_per_checkpoint': 512*target_count,
            'all_roles_output_tokens_bound': 3*512*target_count,
            'teacher_peak_token_bound_usd': amount(teacher),
            'teacher_reservation_usd': amount(teacher.quantize(Decimal('1'), rounding=ROUND_CEILING)),
            'teacher_paid_retries': 0, 'planning_shard_forecast_seconds': 1250,
            'planning_completion_seconds': 1550, 'service_ceilings_usd': {'modal': '30', 'deepseek': '20'}},
        'policies': {'complete_denominator': target_count,
            'retained_outcomes': ['correct', 'wrong', 'truncated', 'input_limit', 'api_failure', 'execution_failure'],
            'filter_failures': False, 'resample_questions': False, 'train_on_final_outputs': False,
            'tune_after_access': False, 'test_access_owners': 1, 'zero_automatic_retries': True,
            'durable_permit_before_source_read': True,
            'partial_results_are_complete': False, 'raw_receipts_required': True,
            'terminal_identity_required_before_recovery': True,
            'recovery_same_contract_and_missing_prefix_only': True,
            'protected5_reallocation_requires_explicit_final_stage_review': True,
            'existing256_protocol_remains_prepared_only': True, 'no256_peek_before_target_choice': True}}
    return {'schema_version': 1, 'version': VERSION, 'stage': 'contract_only_not_authorized',
        'official_test_accessed': False, 'execution_ready': False, 'protocol': protocol,
        'freeze_sha256': digest(protocol)}


def validate(contract):
    try:
        p = contract['protocol']
        expected = build_contract(p['dataset']['sample_count'], source_hashes=p['source_hashes'],
            source_roles=p['source_roles'], selected=p['selected'], seed=p['dataset']['sampling_seed'],
            max_shard_questions=p['sharding']['max_shard_questions'])
        if contract != expected:
            raise ValueError('Contract content or digest differs from the fixed bounded policy')
    except (KeyError, TypeError, OverflowError) as error:
        raise ValueError('Malformed scale contract') from error
    return contract


def expected_ids(contract, shard_id=None):
    validate(contract)
    if shard_id is None:
        return _ids(contract['protocol']['dataset']['indices'])
    matches = [s for s in contract['protocol']['shards'] if s['id'] == shard_id]
    if len(matches) != 1:
        raise ValueError('Unknown shard identity')
    return _ids(matches[0]['indices'])


def batches(contract, shard_id):
    """Return global ordered positions, legitimate tail counts and ID hashes."""
    validate(contract)
    shard = next((s for s in contract['protocol']['shards'] if s['id'] == shard_id), None)
    if shard is None:
        raise ValueError('Unknown shard identity')
    indices = contract['protocol']['dataset']['indices']
    return [{'start': start, 'stop': min(start+8, shard['stop']),
        'count': min(8, shard['stop']-start),
        'ids_sha256': digest(_ids(indices[start:min(start+8, shard['stop'])]))}
        for start in range(shard['start'], shard['stop'], 8)]


def validate_sources(contract, actual_source_hashes, *, complete=True):
    validate(contract)
    p = contract['protocol']
    if actual_source_hashes != p['source_hashes']:
        raise ValueError('Current source hashes differ from the reviewed bundle')
    if complete and (any(not p['source_roles'][r] for r in SOURCE_ROLES)
            or 'final_scale_contract.py' not in p['source_roles']['contract']
            or 'final_scale_receipts.py' not in p['source_roles']['receipts']):
        raise ValueError('Unimplemented or unreviewed source roles remain')
    return digest(actual_source_hashes)


def calibration(contract, *, base_generation_seconds, chosen_generation_seconds,
                evidence_hashes, load_allowance_seconds=80):
    """Bind measured200-development metadata only; never measure final data."""
    validate(contract)
    if not isinstance(evidence_hashes, dict) or set(evidence_hashes) != {'base', 'chosen'}:
        raise ValueError('Both independent development evidence hashes are required')
    for value in evidence_hashes.values():
        require_hash(value)
    for value in (base_generation_seconds, chosen_generation_seconds, load_allowance_seconds):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value <= 0):
            raise ValueError('Calibration requires finite positive observed seconds')
    if load_allowance_seconds < 80:
        raise ValueError('Do not weaken the minimum load allowance')
    forecasts = {role: [round(load_allowance_seconds + 1.25*seconds*(s['stop']-s['start'])/200, 6)
        for s in contract['protocol']['shards']] for role, seconds in
        (('base', base_generation_seconds), ('chosen', chosen_generation_seconds))}
    value = {'role': 'development_calibration', 'development_count': 200,
        'freeze_sha256': contract['freeze_sha256'], 'evidence_hashes': dict(evidence_hashes),
        'base_generation_seconds': base_generation_seconds, 'chosen_generation_seconds': chosen_generation_seconds,
        'load_allowance_seconds': load_allowance_seconds, 'safety_multiplier': 1.25,
        'forecast_seconds_by_role': forecasts,
        'runtime_feasible': max(x for values in forecasts.values() for x in values) <= 1250}
    return dict(value, calibration_sha256=digest(value))


def validate_calibration(contract, value):
    try:
        expected = calibration(contract, base_generation_seconds=value['base_generation_seconds'],
            chosen_generation_seconds=value['chosen_generation_seconds'], evidence_hashes=value['evidence_hashes'],
            load_allowance_seconds=value['load_allowance_seconds'])
        if value != expected or value['runtime_feasible'] is not True:
            raise ValueError('Whole bundle needs exact feasible200-development calibration')
    except (KeyError, TypeError) as error:
        raise ValueError('Malformed calibration') from error
    return value['calibration_sha256']


def review_template(contract):
    """An unapproved record. Constructing it never grants access or funding."""
    validate(contract)
    p = contract['protocol']
    return {'reviewed': False, 'freeze_sha256': contract['freeze_sha256'],
        'source_bundle_sha256': digest(p['source_hashes']), 'selected_sha256': digest(p['selected']),
        'pricing_sha256': digest(p['pricing']), 'caps_sha256': digest(p['bounds']),
        'calibration_sha256': None, 'funding_snapshot_sha256': None,
        'approved_model_roles': ['base', 'chosen', 'teacher'],
        'approved_shard_ids': [s['id'] for s in p['shards']],
        'budget_envelope': {'modal_compute_bundle_usd': p['bounds']['modal_compute_bundle_usd'],
            'modal_recovery_allowance_usd': p['bounds']['modal_recovery_allowance_usd'],
            'deepseek_teacher_usd': p['bounds']['teacher_reservation_usd'],
            'additional_protected_modal_usd': '5', 'additional_protected_deepseek_usd': '0'},
        'final_stage_protected5_allocation_reviewed': False,
        'no_tuning_after_access_acknowledged': False, 'complete_denominator_acknowledged': False,
        'all_source_roles_reviewed': False}


def _time(value):
    if not isinstance(value, str):
        raise ValueError('Require an explicit timezone-aware observation time')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise ValueError('Invalid observation time') from error
    if result.tzinfo is None:
        raise ValueError('Observation time must include timezone')
    return result


def validate_review(contract, review, *, actual_source_hashes, calibration_record,
                    funding_snapshot, as_of_utc, actual_pricing_sha256):
    """Validate explicit whole-bundle review; does not authorize/test/dispatch."""
    validate_sources(contract, actual_source_hashes, complete=True)
    if contract['protocol']['selected'] is None:
        raise ValueError('A final chosen checkpoint identity remains pending')
    template = review_template(contract)
    calibration_hash = validate_calibration(contract, calibration_record)
    if not isinstance(review, dict) or set(review) != set(template):
        raise ValueError('Whole-bundle review shape differs')
    for name in ('freeze_sha256', 'source_bundle_sha256', 'selected_sha256', 'pricing_sha256',
                 'caps_sha256', 'approved_model_roles', 'approved_shard_ids'):
        if review[name] != template[name]:
            raise ValueError('Review no longer binds exact sources/checkpoint/count/caps')
    for name in ('reviewed', 'no_tuning_after_access_acknowledged',
                 'complete_denominator_acknowledged', 'all_source_roles_reviewed'):
        if review[name] is not True:
            raise ValueError('Explicit whole-bundle acknowledgments remain pending')
    if (review['calibration_sha256'] != calibration_hash
            or review['funding_snapshot_sha256'] != digest(funding_snapshot)
            or actual_pricing_sha256 != review['pricing_sha256']):
        raise ValueError('Calibration, funding or current pricing changed after review')
    envelope = review['budget_envelope']
    if not isinstance(envelope, dict) or set(envelope) != set(template['budget_envelope']):
        raise ValueError('Budget must cover the whole bundle and explicit recovery')
    for name in ('modal_compute_bundle_usd', 'modal_recovery_allowance_usd', 'deepseek_teacher_usd'):
        if money(envelope[name]) < money(template['budget_envelope'][name]):
            raise ValueError('Review underfunds theoretical caps or recovery allowance')
    protected = money(envelope['additional_protected_modal_usd'])
    if protected < 5 and review['final_stage_protected5_allocation_reviewed'] is not True:
        raise ValueError('Protected5 cannot silently fund a new final bundle')
    if type(review['final_stage_protected5_allocation_reviewed']) is not bool:
        raise ValueError('Final allocation review must be an explicit boolean')
    now = _time(as_of_utc)
    try:
        for service, ceiling in (('modal', 30), ('deepseek', 20)):
            age = (now-_time(funding_snapshot['observed_at_utc'][service])).total_seconds()
            if not 0 <= age <= 900 or funding_snapshot['new_paid_work_allowed'][service] is not True:
                raise ValueError('Fresh supported funding observations are required')
            limit = money(funding_snapshot['limits_usd'][service])
            if not 0 < limit <= ceiling:
                raise ValueError('Existing service ceiling cannot increase')
            free = limit-money(funding_snapshot['spent_usd'][service])-money(funding_snapshot['reserved_usd'][service])
            required = (money(envelope['modal_compute_bundle_usd'])+money(envelope['modal_recovery_allowance_usd'])+protected
                if service == 'modal' else money(envelope['deepseek_teacher_usd'])+money(envelope['additional_protected_deepseek_usd']))
            if free < required:
                raise ValueError('Whole final bundle plus declared protections does not fit')
    except (KeyError, TypeError) as error:
        raise ValueError('Malformed normalized funding snapshot') from error
    return {'stage': 'review_record_validated_not_execution_authorized',
        'freeze_sha256': contract['freeze_sha256'], 'review_sha256': digest(review),
        'question_count': contract['protocol']['dataset']['sample_count'],
        'official_test_accessed': False, 'paid_work_launched': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=int, choices=TARGETS, default=1000)
    args = parser.parse_args()
    result = build_contract(args.target)
    print(json.dumps({'stage': result['stage'], 'target_count': args.target,
        'shard_counts': [s['stop']-s['start'] for s in result['protocol']['shards']],
        'selected_checkpoint_pending': True, 'source_review_pending': True,
        'execution_ready': False, 'official_test_accessed': False}))
