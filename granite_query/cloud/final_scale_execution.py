"""Pure contracts for a future bounded scaled-final GPU dispatch.

No imports/functions read paths, source content, providers or budgets. Metadata
authorization is not permission to launch. Controllers own fresh funding,
global GPU serialization and provider-confirmed termination.
"""
from copy import deepcopy
import hashlib
import json
import re
from pathlib import PurePosixPath
import math

from cloud import final_scale_contract as contract_api
from cloud import final_scale_receipts as receipts
from cloud import final_scale_loader as loader
from cloud.valuation_contract import trim_generation

VERSION = 'final-scale-gpu-execution-v1'
ROLE = 'final_eval_only'
MAX_INPUT_BYTES = 16*1024*1024
MODEL_CONFIG_SHA256 = '65105f30da56ea03465f7424540a51b66f3a77bcff2af06f6288d093c65905b0'
ROW_FIELDS = {'id', 'source_index', 'prompt', 'gold_answer', 'source_split', 'role', 'training_eligible'}
REQUIRED_SOURCE_ROLES = {
    'contract': {'final_scale_contract.py', 'final_scale_seal.py', 'comparison_control.py', 'budget_reconcile.py'},
    'receipts': {'final_scale_receipts.py'}, 'loader': {'final_scale_loader.py'},
    'granite_executor': {'modal_final_scale.py', 'final_scale_execution.py'},
    'checkpoint_validator': {'final_scale_artifacts.py', 'granite_lora_layout.py', 'valuation_contract.py'},
    'model_image': {'modal_train.py'}, 'scoring': {'comparison_metrics.py'},
    'paired_statistics': {'evaluation_stats.py'},
}
DESCRIPTOR_FIELDS = {'volume_path', 'sha256', 'bytes', 'authorization_sha256', 'binding_sha256',
    'sample_sha256', 'full_source_sha256', 'checkpoint', 'shard_id', 'prefix_sha256', 'retained_count', 'parent_call_id'}
FIXED = {'max_new_tokens': 512, 'enable_thinking': False, 'do_sample': False,
    'evaluation_batch_size': 8, 'max_input_tokens': 1536, 'context_limit': 2048,
    'hard_timeout_seconds': 1800, 'application_guard_seconds': 1600,
    'hard_cpu_cores': 4, 'hard_memory_gib': 32, 'automatic_retries': 0}


def digest(value):
    return contract_api.digest(value)


def payload_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)+'\n').encode('utf-8')


def _record(value, field):
    return dict(value, **{field: digest(value)})


def _check(value, field):
    if not isinstance(value, dict):
        raise ValueError('Hash-bound metadata must be an object')
    contract_api.require_hash(value.get(field))
    if digest({key: item for key, item in value.items() if key != field}) != value[field]:
        raise ValueError('Immutable execution metadata differs')


def volume_path(value):
    if (not isinstance(value, str) or not value or len(value) > 512 or '\\' in value
            or PurePosixPath(value).is_absolute() or str(PurePosixPath(value)) != value
            or any(part in ('.', '..') or part.rstrip(' .') != part or not contract_api.NAME.fullmatch(part)
                or re.fullmatch(r'(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])', part.split('.')[0], re.I)
                for part in value.split('/'))):
        raise ValueError('Volume paths must be explicit safe relative POSIX paths')
    return value


def _sealed(sealed):
    _check(sealed, 'seal_sha256')
    if (type(sealed.get('schema_version')) is not int or sealed['schema_version'] != 1 or sealed.get('version') != 'physical-final-scale-seal-v1'
            or sealed.get('official_test_accessed_by_seal') is not False or sealed.get('paid_work_launched') is not False):
        raise ValueError('Require an unchanged pre-access physical seal')
    contract = contract_api.validate(sealed['contract']); p = contract['protocol']
    contract_api.validate_sources(contract, p['source_hashes'], complete=True)
    if p['selected'] is None or sealed['checkpoint']['selected'] != p['selected']:
        raise ValueError('Chosen model must be frozen before final execution')
    for role, names in REQUIRED_SOURCE_ROLES.items():
        if not names <= set(p['source_roles'][role]):
            raise ValueError('New scaled executor/helper source role is incomplete: '+role)
    inventory = sealed['checkpoint']['adapter_files_sha256']
    if (not isinstance(inventory, dict) or not 2 <= len(inventory) <= 256
            or not {'adapter_config.json', 'adapter_model.safetensors'} <= set(inventory)
            or digest(inventory) != p['selected']['adapter_inventory_sha256']):
        raise ValueError('Sealed adapter inventory differs')
    for name, sha in inventory.items():
        volume_path(name); contract_api.require_hash(sha)
    contract_api.validate_review(contract, sealed['review'], actual_source_hashes=p['source_hashes'],
        calibration_record=sealed['calibration'], funding_snapshot=sealed['funding_snapshot'],
        as_of_utc=sealed['reviewed_as_of_utc'], actual_pricing_sha256=sealed['pricing_sha256'])
    return contract


def validate_sealed_metadata(sealed):
    """Public pre-access preflight. Pure metadata only; grants no source permit."""
    return _sealed(sealed)


def authorization_bundle(sealed, permit, dataset_receipt, *, adapter_path, model_config_descriptor):
    value = {'schema_version': 1, 'sealed': deepcopy(sealed), 'permit': deepcopy(permit),
        'dataset_receipt': deepcopy(dataset_receipt), 'adapter_path': adapter_path,
        'model_config': deepcopy(model_config_descriptor)}
    result = _record(value, 'authorization_sha256')
    validate_authorization(result)
    return result


def validate_authorization(value):
    _check(value, 'authorization_sha256')
    if set(value) != {'schema_version', 'sealed', 'permit', 'dataset_receipt', 'adapter_path', 'model_config', 'authorization_sha256'} or type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ValueError('Unknown execution authorization schema')
    sealed = value['sealed']; contract = _sealed(sealed); p = contract['protocol']
    permit, data = value['permit'], value['dataset_receipt']
    _check(permit, 'permit_sha256'); _check(data, 'receipt_sha256')
    identity = {'protocol_family': 'physical-final-scale-seal-v1', 'role': ROLE,
        'freeze_sha256': contract['freeze_sha256'], 'seal_sha256': sealed['seal_sha256'],
        'owner_sha256': sealed['owner_sha256'], 'test_access_count': 1}
    if (any(permit.get(key) != expected or data.get(key) != expected for key, expected in identity.items())
            or type(permit.get('test_access_count')) is not int or type(data.get('test_access_count')) is not int
            or permit.get('stage') != 'access_begun_before_source_read'
            or not isinstance(permit.get('destination'), str) or not permit['destination']
            or data.get('destination') != permit['destination'] or data.get('permit_sha256') != permit['permit_sha256']
            or type(data.get('population_count')) is not int or data['population_count'] != 1319
            or type(data.get('sample_count')) is not int or data['sample_count'] != p['dataset']['sample_count']
            or data.get('indices_sha256') != p['dataset']['indices_sha256']
            or data.get('input_hash_convention') != loader.INPUT_HASH_CONVENTION):
        raise ValueError('Final source owner, role or persisted dataset receipt differs')
    contract_api._time(permit.get('began_at_utc'))
    for key in ('full_source_sha256', 'sample_sha256', 'binding_sha256'):
        contract_api.require_hash(data.get(key))
    adapter = volume_path(value['adapter_path']); config = value['model_config']
    if (not isinstance(config, dict) or set(config) != {'volume_path', 'sha256', 'bytes'}
            or config.get('sha256') != MODEL_CONFIG_SHA256 or type(config.get('bytes')) is not int
            or not 0 < config['bytes'] <= 1024*1024):
        raise ValueError('Pinned model configuration descriptor differs')
    config_path = volume_path(config['volume_path'])
    if adapter.split('/')[0] != config_path.split('/')[0]:
        raise ValueError('Adapter and model configuration belong to different bundles')
    return contract


def _identity(contract, data, checkpoint, shard_id):
    if checkpoint not in ('base', 'chosen') or not isinstance(shard_id, str) or not any(s['id'] == shard_id for s in contract['protocol']['shards']):
        raise ValueError('Unknown final checkpoint or shard')
    p = contract['protocol']
    return {'role': ROLE, 'freeze_sha256': contract['freeze_sha256'],
        'source_bundle_sha256': digest(p['source_hashes']),
        **{key: data[key] for key in ('full_source_sha256', 'sample_sha256', 'binding_sha256')},
        'checkpoint': checkpoint, 'checkpoint_sha256': digest(p['base'] if checkpoint == 'base' else p['selected']),
        'model': p['base']['model'], 'revision': p['base']['revision'], 'shard_id': shard_id}


def _payload(authorization, payload, checkpoint, shard_id):
    contract = validate_authorization(authorization); data = authorization['dataset_receipt']
    _identity(contract, data, checkpoint, shard_id)
    if not isinstance(payload, dict) or set(payload) != {'binding', 'rows', 'prior_attempts'}:
        raise ValueError('Unknown staged final payload schema')
    binding, rows = payload['binding'], payload['rows']
    receipts.validate_binding(contract, binding)
    if any(binding.get(key) != data[key] for key in ('full_source_sha256', 'sample_sha256', 'binding_sha256')):
        raise ValueError('Payload sample binding differs from persisted source receipt')
    shard = next(s for s in contract['protocol']['shards'] if s['id'] == shard_id)
    expected = binding['questions'][shard['start']:shard['stop']]
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise ValueError('Payload must retain the whole ordered shard')
    for row, question in zip(rows, expected):
        if (not isinstance(row, dict) or set(row) != ROW_FIELDS or row.get('id') != question['id']
                or type(row.get('source_index')) is not int or row['source_index'] != question['source_index']
                or row.get('gold_answer') != question['gold_answer'] or row.get('role') != ROLE
                or row.get('source_split') != 'test' or row.get('training_eligible') is not False
                or not isinstance(row.get('prompt'), str) or not row['prompt'].strip()
                or loader.question_input_hash(row, contract) != question['input_sha256']):
            raise ValueError('Payload row identity, role, reference or exact user input differs')
    prior = payload['prior_attempts']
    if not isinstance(prior, list):
        raise ValueError('Prior attempts must be an ordered terminal lineage')
    if prior:
        if any(not isinstance(attempt, dict) or not isinstance(attempt.get('terminal'), dict)
                or attempt['terminal'].get('raw_pending') is not False for attempt in prior):
            raise ValueError('Uncommitted or unknown raw outcomes must be reconciled without a paid rerun')
        prefix = receipts.recover_prefix(contract, binding, checkpoint, shard_id, prior)
        if not prefix['can_resume']:
            raise ValueError('No authorized remaining prefix/recovery allowance')
    else:
        prefix = {'rows': [], 'retained_count': 0, 'prefix_sha256': digest([]), 'last_call_id': None}
    return contract, shard, prefix


def make_payload(authorization, binding, shard_rows, *, checkpoint, shard_id, prior_attempts=None):
    rows = [{key: row[key] for key in ROW_FIELDS} for row in shard_rows]
    value = {'binding': deepcopy(binding), 'rows': rows,
        'prior_attempts': deepcopy([] if prior_attempts is None else prior_attempts)}
    _payload(authorization, value, checkpoint, shard_id)
    return value


def describe_input(payload, authorization, *, volume_path, checkpoint, shard_id):
    _, _, prefix = _payload(authorization, payload, checkpoint, shard_id)
    raw = payload_bytes(payload)
    if not 0 < len(raw) <= MAX_INPUT_BYTES:
        raise ValueError('Staged shard payload exceeds its byte cap')
    globals()['volume_path'](volume_path)
    if volume_path.split('/')[0] != authorization['adapter_path'].split('/')[0]:
        raise ValueError('Input and selected artifacts belong to different bundles')
    data = authorization['dataset_receipt']
    return {'volume_path': volume_path, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
        'authorization_sha256': authorization['authorization_sha256'],
        **{key: data[key] for key in ('binding_sha256', 'sample_sha256', 'full_source_sha256')},
        'checkpoint': checkpoint, 'shard_id': shard_id, 'prefix_sha256': prefix['prefix_sha256'],
        'retained_count': prefix['retained_count'], 'parent_call_id': prefix['last_call_id']}


def build_intent(sealed, input_descriptor, *, run_id, checkpoint, shard_id, recovery=None):
    contract = _sealed(sealed); p = contract['protocol']; desc = deepcopy(input_descriptor)
    if not isinstance(run_id, str) or not contract_api.NAME.fullmatch(run_id):
        raise ValueError('Unsafe execution run identity')
    if not isinstance(desc, dict) or set(desc) != DESCRIPTOR_FIELDS:
        raise ValueError('Unknown staged input descriptor')
    path = volume_path(desc['volume_path']); bundle_id = path.split('/')[0]
    if (run_id == bundle_id or desc['checkpoint'] != checkpoint or desc['shard_id'] != shard_id
            or type(desc['bytes']) is not int or not 0 < desc['bytes'] <= MAX_INPUT_BYTES
            or type(desc['retained_count']) is not int or desc['retained_count'] < 0):
        raise ValueError('Input descriptor identity or bound differs')
    for key in ('sha256', 'authorization_sha256', 'binding_sha256', 'sample_sha256', 'full_source_sha256', 'prefix_sha256'):
        contract_api.require_hash(desc[key])
    identity = _identity(contract, desc, checkpoint, shard_id)
    shard = next(s for s in p['shards'] if s['id'] == shard_id)
    if desc['retained_count'] >= shard['stop']-shard['start'] or desc['retained_count'] % 8:
        raise ValueError('Recovery prefix must leave an exact missing batch suffix')
    if recovery is None:
        if desc['parent_call_id'] is not None or desc['retained_count'] or desc['prefix_sha256'] != digest([]):
            raise ValueError('Fresh dispatch cannot conceal a prior prefix')
    elif (not isinstance(recovery, dict) or set(recovery) != {'parent_call_id', 'prefix_sha256', 'retained_count'}
            or any(recovery[key] != desc[key] for key in recovery)
            or not isinstance(desc['parent_call_id'], str) or not receipts.CALL.fullmatch(desc['parent_call_id'])):
        raise ValueError('Recovery declaration differs from its terminal-confirmed input prefix')
    value = dict(identity, schema_version=1, version=VERSION, run_id=run_id, bundle_id=bundle_id,
        seal_sha256=sealed['seal_sha256'], authorization_sha256=desc['authorization_sha256'],
        input_descriptor=desc, recovery=deepcopy(recovery), start=shard['start'], stop=shard['stop'],
        count=shard['stop']-shard['start'], seed=p['dataset']['sampling_seed'], **FIXED)
    return _record(value, 'intent_sha256')


def validate_remote_metadata(intent, input_descriptor, authorization):
    contract = validate_authorization(authorization)
    expected = build_intent(authorization['sealed'], input_descriptor, run_id=intent['run_id'],
        checkpoint=intent['checkpoint'], shard_id=intent['shard_id'], recovery=intent.get('recovery'))
    if intent != expected or input_descriptor != intent['input_descriptor'] or intent['authorization_sha256'] != authorization['authorization_sha256']:
        raise ValueError('Dispatch intent differs from its exact metadata bundle')
    data = authorization['dataset_receipt']
    if any(input_descriptor[key] != data[key] for key in ('binding_sha256', 'sample_sha256', 'full_source_sha256')):
        raise ValueError('Input descriptor differs from global dataset receipt')
    if intent['bundle_id'] != authorization['adapter_path'].split('/')[0]:
        raise ValueError('Execution artifacts refer to a different bundle')
    return contract


def validate_inputs(intent, authorization, payload):
    validate_remote_metadata(intent, intent['input_descriptor'], authorization)
    raw = payload_bytes(payload); desc = intent['input_descriptor']
    if len(raw) != desc['bytes'] or hashlib.sha256(raw).hexdigest() != desc['sha256']:
        raise ValueError('Staged payload content differs from immutable intent')
    contract, shard, prefix = _payload(authorization, payload, intent['checkpoint'], intent['shard_id'])
    if (prefix['prefix_sha256'] != desc['prefix_sha256'] or prefix['retained_count'] != desc['retained_count']
            or prefix['last_call_id'] != desc['parent_call_id']):
        raise ValueError('Staged prefix differs from pre-spawn recovery declaration')
    return {'contract': contract, 'binding': payload['binding'], 'rows': payload['rows'],
        'prior_attempts': payload['prior_attempts'], 'prefix_rows': prefix['rows'], 'shard': shard}


def remote_directory(intent):
    volume_path(intent['bundle_id']); volume_path(intent['run_id'])
    return intent['bundle_id']+'/attempts/'+intent['run_id']


def dispatch_claim(intent, claim_id):
    _check(intent, 'intent_sha256')
    if not isinstance(claim_id, str) or not re.fullmatch('[a-f0-9]{32}', claim_id):
        raise ValueError('Dispatch needs a unique explicit32-hex claim')
    value = {key: intent[key] for key in ('role', 'run_id', 'bundle_id', 'freeze_sha256', 'seal_sha256', 'intent_sha256')}
    return _record(dict(value, claim_id=claim_id), 'claim_sha256')


def launch_receipt(intent, actual_call_id):
    _check(intent, 'intent_sha256')
    if not isinstance(actual_call_id, str) or not receipts.CALL.fullmatch(actual_call_id):
        raise ValueError('Actual provider call ID is required')
    value = {key: intent[key] for key in receipts.IDENTITY_FIELDS}
    value.update(call_id=actual_call_id, run_id=intent['run_id'], bundle_id=intent['bundle_id'],
        intent_sha256=intent['intent_sha256'], parent_call_id=intent['input_descriptor']['parent_call_id'],
        prefix_sha256=intent['input_descriptor']['prefix_sha256'])
    return _record(value, 'launch_sha256')


def batch_receipt(intent, launch, start, rows, *, raw_batch_sha256):
    if launch != launch_receipt(intent, launch.get('call_id')):
        raise ValueError('Launch differs from pre-spawn intent and actual call ID')
    contract_api.require_hash(raw_batch_sha256)
    if type(start) is not int or not intent['start'] <= start < intent['stop'] or (start-intent['start']) % 8:
        raise ValueError('Invalid logical batch position')
    stop = min(start+8, intent['stop'])
    if not isinstance(rows, list) or len(rows) != stop-start:
        raise ValueError('Batch must retain its real logical size without padding')
    value = {key: intent[key] for key in receipts.IDENTITY_FIELDS}
    value.update(call_id=launch['call_id'], launch_sha256=launch['launch_sha256'], start=start, stop=stop,
        count=stop-start, rows=deepcopy(rows), rows_sha256=digest(rows),
        question_ids_sha256=digest([row['id'] for row in rows]), raw_batch_sha256=raw_batch_sha256)
    return _record(value, 'batch_sha256')


def terminal_receipt(intent, launch, batches, prefix_rows, stage, *, confirmed_terminal=False,
                     raw_pending=False, raw_pending_start=None, raw_pending_sha256=None):
    if launch != launch_receipt(intent, launch.get('call_id')) or stage not in receipts.TERMINAL or type(confirmed_terminal) is not bool:
        raise ValueError('Invalid execution completion declaration')
    if (len(prefix_rows) != intent['input_descriptor']['retained_count']
            or digest(prefix_rows) != intent['input_descriptor']['prefix_sha256']):
        raise ValueError('Terminal prefix differs from immutable pre-spawn evidence')
    rows = list(prefix_rows)+[row for batch in batches for row in batch['rows']]
    next_position = intent['start']+len(prefix_rows)
    for batch in batches:
        if (batch.get('start') != next_position or batch.get('call_id') != launch['call_id']
                or batch.get('launch_sha256') != launch['launch_sha256']):
            raise ValueError('Terminal batch receipts are not a contiguous owned suffix')
        _check(batch, 'batch_sha256'); next_position = batch['stop']
    if len(rows) > intent['count'] or stage == 'completed' and len(rows) != intent['count']:
        raise ValueError('Completion must preserve the whole logical shard')
    if (type(raw_pending) is not bool or raw_pending and (type(raw_pending_start) is not int
            or not intent['start'] <= raw_pending_start < intent['stop'])
            or not raw_pending and (raw_pending_start is not None or raw_pending_sha256 is not None)
            or stage == 'completed' and raw_pending):
        raise ValueError('Pending raw outcomes cannot be declared complete')
    if raw_pending:
        contract_api.require_hash(raw_pending_sha256)
    value = {key: intent[key] for key in receipts.IDENTITY_FIELDS}
    value.update(call_id=launch['call_id'], launch_sha256=launch['launch_sha256'], stage=stage,
        confirmed_terminal=confirmed_terminal, committed_batches_sha256=digest([b['batch_sha256'] for b in batches]),
        output_prefix_sha256=digest(rows), retained_count=len(rows), raw_pending=raw_pending,
        raw_pending_start=raw_pending_start, raw_pending_sha256=raw_pending_sha256)
    return _record(value, 'terminal_sha256')


def derive_raw_batch(intent, launch, raw, binding, decode):
    """Deterministically derive a saved batch without model inference or I/O.

    decode must be the reviewed pinned tokenizer's deterministic decode callable.
    Keep original raw files and hashes; never replay generation to repair JSON.
    """
    if launch != launch_receipt(intent, launch.get('call_id')) or not callable(decode):
        raise ValueError('Raw derivation requires the exact owned launch and decoder')
    _check(binding, 'binding_sha256')
    fields = set(receipts.IDENTITY_FIELDS) | {'call_id', 'launch_sha256', 'start', 'stop', 'count',
        'question_ids', 'input_tokens', 'generated_ids', 'generation_elapsed_seconds', 'eos_token_ids', 'generation_failed'}
    if (not isinstance(raw, dict) or set(raw) != fields or any(raw.get(k) != intent[k] for k in receipts.IDENTITY_FIELDS)
            or raw['call_id'] != launch['call_id'] or raw['launch_sha256'] != launch['launch_sha256']):
        raise ValueError('Raw batch identity differs')
    start = raw['start']; stop = min(start+8, intent['stop']) if type(start) is int else -1
    if (type(start) is not int or not intent['start'] <= start < intent['stop'] or (start-intent['start']) % 8
            or raw['stop'] != stop or type(raw['count']) is not int or raw['count'] != stop-start):
        raise ValueError('Raw logical batch boundaries differ')
    expected = binding['questions'][start:stop]
    if (binding.get('binding_sha256') != intent['binding_sha256']
            or raw['question_ids'] != [q['id'] for q in expected]
            or not isinstance(raw['input_tokens'], list) or len(raw['input_tokens']) != stop-start
            or any(type(n) is not int or n < 1 for n in raw['input_tokens'])
            or type(raw['generation_failed']) is not bool):
        raise ValueError('Raw input identities or bounded token counts differ')
    elapsed = raw['generation_elapsed_seconds']; eos = raw['eos_token_ids']; outputs = raw['generated_ids']
    if (isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)) or not math.isfinite(elapsed) or elapsed < 0
            or not isinstance(eos, list) or 100257 not in eos or any(type(n) is not int or not 0 <= n < 100352 for n in eos)
            or not isinstance(outputs, list)):
        raise ValueError('Raw timing or generation metadata is malformed')
    eligible = sum(n <= 1536 for n in raw['input_tokens'])
    if (raw['generation_failed'] and (not eligible or outputs)
            or not raw['generation_failed'] and len(outputs) != eligible
            or not eligible and elapsed):
        raise ValueError('Raw generated subset differs from the attempted eligible inputs')
    for tokens in outputs:
        if not isinstance(tokens, list) or not 1 <= len(tokens) <= 512 or any(type(n) is not int or not 0 <= n < 100352 for n in tokens):
            raise ValueError('Raw token IDs exceed the pinned vocabulary/output bounds')
    rows, index = [], 0
    for position, question, count in zip(range(start, stop), expected, raw['input_tokens']):
        row = {k: question[k] for k in ('id', 'source_index', 'gold_answer', 'input_sha256')}
        row.update(global_position=position, response='', generated_tokens=0, truncated=False,
            elapsed_seconds=0, failure_type=None)
        if count > 1536:
            row.update(outcome='input_limit', failure_type='input_limit')
        elif raw['generation_failed']:
            row.update(outcome='failed', failure_type='generation_error', elapsed_seconds=elapsed/eligible)
        else:
            tail, truncated = trim_generation(outputs[index], eos, 512); index += 1
            text = decode(tail)
            if not isinstance(text, str):
                raise ValueError('Reviewed decoder must return original decoded text')
            row.update(outcome='generated', response=text, generated_tokens=len(tail),
                truncated=truncated, elapsed_seconds=elapsed/eligible)
        rows.append(row)
    return batch_receipt(intent, launch, start, rows,
        raw_batch_sha256=hashlib.sha256(payload_bytes(raw)).hexdigest())


def reconcile_full_prefix(intent, authorization, payload, launch, batches, terminal, *,
                          provider_terminal_proof, raw_batch_hashes):
    """Pure local completion attestation; never overwrites failure history.

    The caller must observe provider termination and inventory *all* raw files.
    Extra/unmatched raw hashes block reconciliation. Store this return value in
    a new immutable attestation, keeping the original failed terminal unchanged.
    """
    context = validate_inputs(intent, authorization, payload)
    proof = provider_terminal_proof
    if (not isinstance(proof, dict) or set(proof) != {'call_id', 'confirmed_terminal', 'kind', 'observed_at_utc'}
            or proof['confirmed_terminal'] is not True or proof['call_id'] != launch['call_id']
            or not isinstance(proof['kind'], str) or proof['kind'] not in receipts.TERMINAL):
        raise ValueError('Explicit matching provider terminal proof is required')
    contract_api._time(proof['observed_at_utc'])
    _check(terminal, 'terminal_sha256')
    if (terminal.get('confirmed_terminal') is not True or terminal.get('stage') not in {'failed', 'timed_out', 'cancelled'}
            or terminal.get('raw_pending') is not False):
        raise ValueError('Only a confirmed failed fully-derived prefix can be reconciled')
    if not isinstance(raw_batch_hashes, dict) or raw_batch_hashes != {str(b['start']): b.get('raw_batch_sha256') for b in batches}:
        raise ValueError('Every raw batch must have exactly one immutable derived receipt')
    current = {'launch': launch, 'terminal': terminal, 'batches': batches}
    lineage = context['prior_attempts']+[current]
    retained = receipts.recover_prefix(context['contract'], context['binding'], intent['checkpoint'], intent['shard_id'], lineage)
    if retained['retained_count'] != intent['count']:
        raise ValueError('Partial results cannot be promoted to whole-denominator completion')
    completed = terminal_receipt(intent, launch, batches, context['prefix_rows'], 'completed', confirmed_terminal=True)
    evidence = {'original_terminal_sha256': terminal['terminal_sha256'],
        'provider_terminal_proof_sha256': digest(proof), 'raw_batch_hashes_sha256': digest(raw_batch_hashes),
        'no_generation_replayed': True, 'original_failure_history_preserved': True}
    completed.pop('terminal_sha256')
    completed = _record(dict(completed, local_completion_reconciliation=evidence), 'terminal_sha256')
    return {'stage': 'full_prefix_reconciled_without_new_call', 'intent_sha256': intent['intent_sha256'],
        'evidence': evidence, 'completed_attempt': {'launch': deepcopy(launch), 'terminal': completed, 'batches': deepcopy(batches)},
        'previous_attempts': deepcopy(context['prior_attempts']), 'execution_authorized_by_this_helper': False}
