"""Physical, pre-access sealing for the separate scaled final-evaluation design.

Only explicit create/begin/bind calls write immutable local metadata. This module
never reads official questions, calls providers, reads budgets or launches work.
No CLI creates a seal or permit; the default CLI only describes its boundaries.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import struct
import time

from cloud import final_scale_contract as contract_api
from cloud import final_scale_receipts as receipts_api
from cloud.valuation_contract import validate_arm

ROOT = Path(__file__).resolve().parent
PRIVATE_ROOT = ROOT/'runs'
PROJECT_ROOT = ROOT.parent
ACCESS = PRIVATE_ROOT/'supervisor/final_test_access.json'
VERSION = 'physical-final-scale-seal-v1'
CALL = re.compile(r'fc-[A-Za-z0-9][A-Za-z0-9-]{0,127}')
CLAIM = re.compile(r'[0-9a-f]{32}')
LORA_NAME = re.compile(r'(.+\.(q_proj|v_proj))\.lora_([AB])(?:\.[A-Za-z0-9_-]+)?\.weight')
INPUT_HASH_CONVENTION = 'qid-index-canonical-messages-v1'


def now():
    return datetime.now(timezone.utc).isoformat()


def _safe(path, *, private=False, exists=True):
    if not isinstance(path, (str, Path)):
        raise ValueError('Artifact path must be explicit')
    path = Path(path).absolute()
    boundary = (PRIVATE_ROOT if private else PROJECT_ROOT).absolute()
    if not path.is_relative_to(boundary):
        raise ValueError('Path must remain inside the intended local project boundary')
    cursor = path
    while True:
        if cursor.is_symlink() or (hasattr(cursor, 'is_junction') and cursor.is_junction()):
            raise ValueError('Symlinks and junctions cannot identify sealed artifacts')
        if cursor == boundary:
            break
        cursor = cursor.parent
    resolved = path.resolve(strict=exists)
    if not resolved.is_relative_to(boundary.resolve()):
        raise ValueError('Resolved artifact path escaped its boundary')
    return resolved


def _file(path):
    path = _safe(path)
    if not path.is_file():
        raise ValueError('Require an actual regular file')
    return path


def sha(path):
    path = _file(path)
    result = hashlib.sha256()
    with path.open('rb') as handle:
        while True:
            part = handle.read(1024*1024)
            if not part:
                break
            result.update(part)
    return result.hexdigest()


def read(path):
    path = _file(path)
    if path.stat().st_size > 128*1024*1024:
        raise ValueError('Metadata file exceeds the bounded local envelope')
    value = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=_object_pairs)
    if not isinstance(value, dict):
        raise ValueError('Sealed metadata must be an object')
    return value


def _write_once(path, value):
    path = _safe(path, private=True, exists=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(4):
        try:
            with path.open('x', encoding='utf-8', newline='\n') as handle:
                json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
                handle.write('\n')
                handle.flush()
                os.fsync(handle.fileno())
            return
        except PermissionError:
            if attempt == 3:
                raise
            time.sleep(.05*(2**attempt))


def _hash_record(value, field):
    return dict(value, **{field: contract_api.digest(value)})


def _check_record(value, field):
    contract_api.require_hash(value.get(field))
    if contract_api.digest({k: v for k, v in value.items() if k != field}) != value[field]:
        raise ValueError('Immutable metadata hash changed')


def _object_pairs(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError('Duplicate safetensors header key')
        result[name] = value
    return result


def inspect_safetensors(path):
    """Bounded stdlib validation; no tensor deserialization or code execution."""
    path = _file(path)
    size = path.stat().st_size
    if not 10 <= size <= 512*1024*1024:
        raise ValueError('Adapter weights exceed the bounded file envelope')
    with path.open('rb') as handle:
        prefix = handle.read(8)
        if len(prefix) != 8:
            raise ValueError('Truncated safetensors length prefix')
        length = struct.unpack('<Q', prefix)[0]
        if not 2 <= length <= 8*1024*1024 or length % 8 or length+8 > size:
            raise ValueError('Invalid or incomplete safetensors header length')
        raw = handle.read(length)
    if not raw.startswith(b'{'):
        raise ValueError('Safetensors header must start with a JSON object')
    header = json.loads(raw.decode('utf-8'), object_pairs_hook=_object_pairs)
    if not isinstance(header, dict):
        raise ValueError('Safetensors header must be an object')
    metadata = header.pop('__metadata__', {})
    if not isinstance(metadata, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in metadata.items()):
        raise ValueError('Invalid safetensors metadata')
    if not 4 <= len(header) <= 10000:
        raise ValueError('Require bounded q/v LoRA tensor pairs')
    intervals, pairs, modules = [], {}, set()
    widths = {'F16': 2, 'BF16': 2, 'F32': 4, 'F64': 8}
    payload = size-8-length
    for name, entry in header.items():
        match = LORA_NAME.fullmatch(name) if isinstance(name, str) and len(name) <= 512 else None
        if not match or not isinstance(entry, dict) or set(entry) != {'dtype', 'shape', 'data_offsets'}:
            raise ValueError('Unexpected adapter tensor identity or header fields')
        shape, offsets = entry['shape'], entry['data_offsets']
        if (not isinstance(entry['dtype'], str) or entry['dtype'] not in widths or not isinstance(shape, list) or len(shape) != 2
                or any(type(x) is not int or not 1 <= x <= 131072 for x in shape)
                or not isinstance(offsets, list) or len(offsets) != 2
                or any(type(x) is not int for x in offsets)
                or not 0 <= offsets[0] < offsets[1] <= payload
                or offsets[1]-offsets[0] != math.prod(shape)*widths[entry['dtype']]):
            raise ValueError('Safetensors shape, dtype, offsets or file completeness differs')
        group, module, side = match.groups()
        if (side == 'A' and shape[0] != 8) or (side == 'B' and shape[1] != 8):
            raise ValueError('Adapter tensor rank differs from LoRA r8')
        if side in pairs.setdefault(group, set()):
            raise ValueError('Duplicate logical LoRA tensor')
        pairs[group].add(side)
        modules.add(module)
        intervals.append(tuple(offsets))
    cursor = 0
    for start, end in sorted(intervals):
        if start != cursor:
            raise ValueError('Safetensors data overlaps or contains unaccounted gaps')
        cursor = end
    if cursor != payload or modules != {'q_proj', 'v_proj'} or any(value != {'A', 'B'} for value in pairs.values()):
        raise ValueError('Safetensors data is incomplete or lacks paired q/v modules')
    return {'tensor_count': len(header), 'payload_bytes': payload,
        'header_sha256': hashlib.sha256(raw).hexdigest(), 'file_sha256': sha(path),
        'validation_scope': 'Structural file/header/offset completeness and paired r8 q/v tensors only.',
        'pinned_model_tensor_layout_and_coverage_verified': False}


def _finite(value, *, positive=False):
    return (not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
            and (value > 0 if positive else value >= 0))


def _batch_timing(rows, worker_seconds):
    for offset in range(0, len(rows), 8):
        batch = rows[offset:offset+8]
        if any(not math.isclose(row['batch_elapsed_seconds'], batch[0]['batch_elapsed_seconds'], rel_tol=1e-9)
               for row in batch):
            raise ValueError('Saved rows do not share the actual batch8 generation time')
    if sum(row['elapsed_seconds'] for row in rows) > worker_seconds+.001:
        raise ValueError('Saved generation time exceeds its enclosing worker duration')


def _manifest_claim(folder, plan, count):
    study = folder.parent.parent
    name = 'study_manifest.json' if count == 200 else 'manifest.json'
    path = study/name
    manifest = read(path)
    if count == 200:
        if (manifest.get('version') != 'human-reference64k-dev200-v2'
                or manifest.get('official_test_accessed') is not False or manifest.get('expected_dev') != 200):
            raise ValueError('Chosen human checkpoint lacks its exact saved study contract')
        claim_path = folder/'human_claim.json'
        claim = read(claim_path)
        if (not isinstance(claim.get('claim_id'), str) or not CLAIM.fullmatch(claim['claim_id'])
                or claim.get('run_id') != plan['run_id'] or claim.get('protocol_hash') != plan['protocol_hash']
                or claim.get('study_manifest_sha256') != sha(path)):
            raise ValueError('Human checkpoint unique dispatch claim differs')
        identity = 'human_unique_dispatch_claim'
        pinned = ('student_valuation.py', 'valuation_contract.py', 'modal_valuation.py', 'modal_train.py',
            'study_runner.py', 'comparison_control.py', 'budget_reconcile.py', 'comparison_metrics.py',
            '../ranking/verification.py')
        if (manifest.get('controller_sha256') != sha(ROOT/'human_study_control.py')
                or set(manifest.get('code_sha256', {})) != set(pinned)
                or any(manifest['code_sha256'][name] != sha(ROOT/name) for name in pinned)
                or plan.get('experiment_version') != manifest['version']):
            raise ValueError('Human saved controller/worker source contract changed')
    else:
        if (manifest.get('version') != 'common-pool-data-efficiency-v1'
                or manifest.get('official_test_used') is not False):
            raise ValueError('Chosen64 checkpoint lacks its current-grid saved contract')
        claim_path = None
        identity = 'frozen_manifest_job_claim_no_retrospective_dispatch_claim'
        files = {'training_worker_sha256': 'modal_valuation.py',
            'selection_code_sha256': 'data_efficiency_control.py', 'skill_code_sha256': 'student_valuation.py',
            'gradient_score_code_sha256': 'gradient_valuation.py'}
        expected_sources = {key: sha(ROOT/name) for key, name in files.items()}
        if (manifest.get('source_code') != expected_sources or plan.get('source_code') != expected_sources
                or plan.get('study_version') != manifest['version']):
            raise ValueError('Current-grid saved selection/worker source contract changed')
    jobs = manifest.get('jobs')
    if not isinstance(jobs, list) or any(not isinstance(job, dict) for job in jobs):
        raise ValueError('Saved study job claims are malformed')
    matches = [j for j in jobs if j.get('run_id') == plan['run_id']]
    if len(matches) != 1:
        raise ValueError('Frozen study must claim the chosen job exactly once')
    job = matches[0]
    relative_folder = job.get('folder')
    if (not isinstance(relative_folder, str) or Path(relative_folder).is_absolute()
            or '..' in Path(relative_folder).parts):
        raise ValueError('Frozen job claim must use a contained relative path')
    if (job.get('protocol_hash') != plan['protocol_hash'] or job.get('input_sha256') != plan['input_sha256']
            or job.get('selector') != plan['checkpoint_name']
            or _safe(study/relative_folder, private=True) != folder):
        raise ValueError('Frozen job claim differs from the completed run')
    artifacts = manifest.get('artifacts_sha256', {})
    for filename in ('plan.json', 'input.json'):
        relative = (folder/filename).relative_to(study).as_posix()
        if artifacts.get(relative) != sha(folder/filename):
            raise ValueError('Prepared plan/input hashes differ from the saved study')
    return path, claim_path, identity


def inspect_checkpoint(chosen_run):
    """Validate a real completed development adapter; never selects one itself."""
    folder = _safe(chosen_run, private=True)
    if not folder.is_dir() or not contract_api.NAME.fullmatch(folder.name):
        raise ValueError('Require a safely named physical chosen run')
    plan, result, data = (read(folder/name) for name in ('plan.json', 'result.json', 'input.json'))
    fixed = {'mode': 'train_evaluate', 'model': contract_api.MODEL, 'revision': contract_api.REVISION,
        'tokens_per_update': 1024, 'learning_rate': 2e-5, 'lora_r': 8, 'lora_alpha': 16,
        'context_limit': 2048, 'max_new_tokens': 512, 'enable_thinking': False, 'do_sample': False,
        'evaluation_batch_size': 8, 'evaluation_kind': 'development', 'fresh_base': True,
        'data_repetition': False, 'official_test_used': False}
    if any(type(plan.get(k)) is not type(v) or plan[k] != v for k, v in fixed.items()):
        raise ValueError('Chosen run differs from the exact approved training/inference recipe')
    protocol = {k: v for k, v in plan.items() if k not in ('run_id', 'protocol_hash', 'resume_from')}
    if (plan.get('run_id') != folder.name or plan.get('protocol_hash') != contract_api.digest(protocol)
            or plan.get('input_sha256') != sha(folder/'input.json')
            or type(plan.get('seed')) is not int or plan['seed'] not in (42, 43)
            or type(plan.get('token_budget')) is not int or plan['token_budget'] not in (32768, 65536, 131072)
            or plan.get('optimizer_updates') != plan['token_budget']//1024):
        raise ValueError('Chosen frozen protocol, input, seed or exposure changed')
    development = data.get('development')
    if not isinstance(development, list) or len(development) not in (64, 200):
        raise ValueError('Require completed64 or200 development questions')
    count = len(development)
    ids = [row['id'] for row in development]
    if (ids != plan.get('development_ids') or len(set(ids)) != count
            or any(not isinstance(identifier, str) or identifier.startswith('gsm8k:test:') for identifier in ids)):
        raise ValueError('Development identities are duplicated or include official final IDs')
    training = validate_arm(data['arm'])
    if (set(training) & set(ids) or data['arm']['token_budget'] != plan['token_budget']
            or data['arm']['arm'] != plan.get('arm') or any(len(row['input_ids']) > 2048 for row in training.values())):
        raise ValueError('Chosen training masks/exposure or development isolation differs')
    if (result.get('stage') != 'completed' or result.get('run_id') != plan['run_id']
            or result.get('plan') != plan or result.get('held_out_test_used') is not False
            or result.get('arm') != plan['arm'] or type(result.get('supervised_tokens')) is not int
            or result['supervised_tokens'] != plan['token_budget']
            or type(result.get('optimizer_updates')) is not int or result['optimizer_updates'] != plan['optimizer_updates']
            or set(result.get('evaluations', {})) != {plan.get('checkpoint_name')}
            or not _finite(result.get('elapsed_seconds'), positive=True)):
        raise ValueError('Chosen terminal result differs from frozen development execution')
    losses = result.get('weighted_losses')
    if not isinstance(losses, list) or len(losses) != plan['optimizer_updates'] or any(not _finite(x) for x in losses):
        raise ValueError('Chosen optimizer history is incomplete')
    rows = result['evaluations'][plan['checkpoint_name']]
    if not isinstance(rows, list) or [row['id'] for row in rows] != ids:
        raise ValueError('Chosen development outputs are incomplete or reordered')
    for row, expected in zip(rows, development):
        if (str(row.get('gold_answer')) != str(expected['gold_answer']) or not isinstance(row.get('response'), str)
                or type(row.get('truncated')) is not bool or type(row.get('generated_tokens')) is not int
                or not 0 <= row['generated_tokens'] <= 512 or type(row.get('batch_size')) is not int or row['batch_size'] != 8
                or not _finite(row.get('batch_elapsed_seconds')) or not _finite(row.get('elapsed_seconds'))
                or not math.isclose(row['elapsed_seconds'], row['batch_elapsed_seconds']/8, rel_tol=1e-9)):
            raise ValueError('Chosen development reference or generation/timing differs')
    _batch_timing(rows, result['elapsed_seconds'])
    launch, terminal = read(folder/'launch.json'), read(folder/'study_terminal.json')
    if (launch.get('run_id') != plan['run_id'] or not isinstance(launch.get('call_id'), str)
            or not CALL.fullmatch(launch['call_id']) or terminal.get('kind') != 'completed'
            or terminal.get('call_id') != launch['call_id'] or terminal.get('result_sha256') != sha(folder/'result.json')):
        raise ValueError('Chosen call/terminal/result ownership is ambiguous')
    manifest_path, claim_path, identity = _manifest_claim(folder, plan, count)
    adapter = _safe(folder/'adapter', private=True)
    config = read(adapter/'adapter_config.json')
    if (config.get('base_model_name_or_path') != contract_api.MODEL or type(config.get('r')) is not int
            or config['r'] != 8 or type(config.get('lora_alpha')) is not int or config['lora_alpha'] != 16
            or isinstance(config.get('lora_dropout'), bool) or config.get('lora_dropout') != 0
            or config.get('peft_type') != 'LORA' or config.get('bias') != 'none' or config.get('task_type') != 'CAUSAL_LM'
            or not isinstance(config.get('target_modules'), list)
            or sorted(config['target_modules']) != ['q_proj', 'v_proj']):
        raise ValueError('Physical adapter config differs from the trained LoRA recipe')
    for name in ('use_rslora', 'use_dora', 'fan_in_fan_out', 'use_qalora', 'lora_bias'):
        if config.get(name, False) is not False:
            raise ValueError('Alternate adapter scaling or structure differs from classic LoRA')
    for name in ('rank_pattern', 'alpha_pattern'):
        if config.get(name, {}) != {}:
            raise ValueError('Per-layer rank/alpha changes differ from the evaluated recipe')
    for name in ('modules_to_save', 'layer_replication', 'exclude_modules', 'target_parameters'):
        if config.get(name) not in (None, []):
            raise ValueError('Extra adapter modules/parameters differ from the evaluated recipe')
    if any(config.get(name) is not None for name in ('layers_to_transform', 'layers_pattern')):
        raise ValueError('Layer-selection overrides differ from plain q/v LoRA')
    weights = inspect_safetensors(adapter/'adapter_model.safetensors')
    inventory = {}
    for path in sorted(adapter.rglob('*')):
        _safe(path, private=True)
        if path.is_file():
            inventory[path.relative_to(adapter).as_posix()] = sha(path)
    evidence_paths = {name: folder/name for name in ('plan.json', 'input.json', 'result.json', 'launch.json', 'study_terminal.json')}
    evidence_paths['study_manifest'] = manifest_path
    if claim_path:
        evidence_paths['human_claim'] = claim_path
    evidence = {name: sha(path) for name, path in evidence_paths.items()}
    selected = {'model': contract_api.MODEL, 'revision': contract_api.REVISION,
        'checkpoint_id': folder.name, 'adapter_inventory_sha256': contract_api.digest(inventory),
        'development_evidence_sha256': contract_api.digest(evidence)}
    return {'selected': selected, 'run_path': str(folder), 'adapter_path': str(adapter),
        'adapter_files_sha256': inventory, 'development_evidence_sha256': evidence,
        'development_count': count, 'checkpoint_name': plan['checkpoint_name'],
        'identity_provenance': identity, 'weights_validation': weights,
        'weight_inventory_capture_timing': 'after_development_evaluation_before_final_seal',
        'development_worker_recorded_contemporaneous_adapter_hashes': False,
        'weight_provenance_limit': 'Call identity, run path and saved development/source contracts establish run provenance. Adapter bytes are hashed after development, so they do not prove a contemporaneous byte match to the evaluated model. Structural validation does not prove full pinned-model tensor layout/coverage. A later reviewed evaluator must check expected model/module shapes and enforce the sealed hashes before test loading.'}


def _source_inventory(contract, source_paths):
    expected = contract['protocol']['source_hashes']
    if not isinstance(source_paths, dict) or set(source_paths) != set(expected):
        raise ValueError('Every reviewed helper needs its actual physical source file')
    paths, hashes = {}, {}
    for name, value in source_paths.items():
        path = _file(value)
        if path.name != name:
            raise ValueError('Physical source basename differs from the reviewed role')
        paths[name] = str(path)
        hashes[name] = sha(path)
    owned = {'final_scale_contract.py': Path(contract_api.__file__).resolve(),
        'final_scale_receipts.py': Path(receipts_api.__file__).resolve(), 'final_scale_seal.py': Path(__file__).resolve(),
        'valuation_contract.py': ROOT/'valuation_contract.py'}
    if any(paths.get(name) != str(path) for name, path in owned.items()):
        raise ValueError('Exact contract/receipts/seal implementations must be physically bound')
    if 'final_scale_seal.py' not in contract['protocol']['source_roles']['contract']:
        raise ValueError('Physical seal implementation is missing from the reviewed contract role')
    if 'valuation_contract.py' not in contract['protocol']['source_roles']['checkpoint_validator']:
        raise ValueError('Actual training-mask validator must be part of the reviewed source bundle')
    contract_api.validate_sources(contract, hashes, complete=True)
    return paths, hashes


def _registry(path=None):
    requested = _safe(ACCESS if path is None else path, private=True, exists=False)
    if requested != _safe(ACCESS, private=True, exists=False):
        raise ValueError('Every final protocol must use the one shared access registry')
    return requested


def _calibration_inventory(paths, contract, record, checkpoint):
    if not isinstance(paths, dict) or set(paths) != {'base', 'chosen'}:
        raise ValueError('Both physical200-question calibration results are required')
    stored, questions = {}, None
    for role in ('base', 'chosen'):
        path = _safe(paths[role], private=True)
        if path.name != 'result.json' or sha(path) != record['evidence_hashes'][role]:
            raise ValueError('Physical calibration result differs from its reviewed evidence hash')
        folder = path.parent
        result, plan, data = read(path), read(folder/'plan.json'), read(folder/'input.json')
        protocol = {k: v for k, v in plan.items() if k not in ('run_id', 'protocol_hash', 'resume_from')}
        if (plan.get('protocol_hash') != contract_api.digest(protocol)
                or plan.get('run_id') != folder.name or plan.get('input_sha256') != sha(folder/'input.json')
                or result.get('stage') != 'completed' or result.get('plan') != plan
                or result.get('run_id') != folder.name or result.get('held_out_test_used') is not False
                or not _finite(result.get('elapsed_seconds'), positive=True)):
            raise ValueError('Physical calibration call/input/protocol differs')
        fixed = {'model': contract_api.MODEL, 'revision': contract_api.REVISION,
            'evaluation_kind': 'development', 'evaluation_batch_size': 8,
            'max_new_tokens': 512, 'enable_thinking': False, 'do_sample': False}
        if any(type(plan.get(k)) is not type(v) or plan[k] != v for k, v in fixed.items()):
            raise ValueError('Physical calibration inference recipe differs')
        development = data.get('development')
        if not isinstance(development, list) or len(development) != 200:
            raise ValueError('Calibration must use actual200 development questions')
        ids = [r['id'] for r in development]
        if (len(set(ids)) != 200 or ids != plan.get('development_ids')
                or any(not isinstance(x, str) or x.startswith('gsm8k:test:') for x in ids)
                or questions is not None and questions != development):
            raise ValueError('Base/chosen calibration must share the same200 development inputs')
        questions = development
        if role == 'base':
            if (plan.get('mode') != 'evaluate_saved' or plan.get('adapter_from') is not None
                    or result.get('supervised_tokens') != 0 or result.get('optimizer_updates') != 0
                    or 'arm' in data):
                raise ValueError('Baseline calibration must be untouched zero-training base')
        elif folder != Path(checkpoint['run_path']):
            if (plan.get('mode') != 'evaluate_saved'
                    or plan.get('adapter_from') != Path(checkpoint['run_path']).name+'/adapter'
                    or plan.get('evaluated_adapter_inventory_sha256') != checkpoint['selected']['adapter_inventory_sha256']):
                raise ValueError('Separate chosen calibration must bind the actual selected adapter')
        label = plan.get('checkpoint_name')
        if set(result.get('evaluations', {})) != {label}:
            raise ValueError('Calibration evaluated checkpoint label differs')
        rows = result['evaluations'][label]
        if not isinstance(rows, list) or [r['id'] for r in rows] != ids:
            raise ValueError('Calibration outputs must retain all200 ordered outcomes')
        for row, expected in zip(rows, development):
            if (str(row.get('gold_answer')) != str(expected['gold_answer'])
                    or not isinstance(row.get('response'), str) or type(row.get('truncated')) is not bool
                    or type(row.get('generated_tokens')) is not int or not 0 <= row['generated_tokens'] <= 512
                    or type(row.get('batch_size')) is not int or row['batch_size'] != 8
                    or not _finite(row.get('elapsed_seconds')) or not _finite(row.get('batch_elapsed_seconds'))
                    or not math.isclose(row['elapsed_seconds'], row['batch_elapsed_seconds']/8, rel_tol=1e-9)):
                raise ValueError('Calibration output reference/generation/timing differs')
        _batch_timing(rows, result['elapsed_seconds'])
        observed = sum(row['elapsed_seconds'] for row in rows)
        if (not math.isclose(observed, record[role+'_generation_seconds'], rel_tol=1e-9)
                or observed > result['elapsed_seconds']+.001):
            raise ValueError('Calibration scalar does not equal actual saved generation timing')
        if role == 'base' and record['load_allowance_seconds']+.001 < result['elapsed_seconds']-observed:
            raise ValueError('Load allowance is below actual baseline non-generation time')
        launch, terminal = read(folder/'launch.json'), read(folder/'study_terminal.json')
        if (launch.get('run_id') != folder.name or not isinstance(launch.get('call_id'), str)
                or not CALL.fullmatch(launch['call_id']) or terminal.get('kind') != 'completed'
                or terminal.get('call_id') != launch['call_id'] or terminal.get('result_sha256') != sha(path)):
            raise ValueError('Calibration call lacks matching complete terminal evidence')
        if (folder.parent.parent/'study_manifest.json').exists():
            _manifest_claim(folder, plan, 200)
        stored[role] = {'result_path': str(path), 'result_sha256': sha(path),
            'plan_sha256': sha(folder/'plan.json'), 'input_sha256': sha(folder/'input.json'),
            'launch_sha256': sha(folder/'launch.json'), 'terminal_sha256': sha(folder/'study_terminal.json')}
    return stored


def create(contract, chosen_run, output, *, source_paths, review, calibration_record,
           funding_snapshot, as_of_utc, actual_pricing_sha256, calibration_source_paths=None, access_registry=None):
    registry = _registry(access_registry)
    if registry.exists():
        raise ValueError('Final access already began; new checkpoint/protocol seals are forbidden')
    output = _safe(output, private=True, exists=False)
    if output.exists():
        raise FileExistsError('Physical seals are immutable; verify or choose a new unused directory')
    chosen_path = _safe(chosen_run, private=True)
    if (output.is_relative_to(chosen_path) or chosen_path.is_relative_to(output)
            or registry.is_relative_to(output)):
        raise ValueError('New seal metadata cannot modify chosen artifacts or contain the shared registry')
    contract_api.validate(contract)
    checkpoint = inspect_checkpoint(chosen_run)
    if contract['protocol']['selected'] != checkpoint['selected']:
        raise ValueError('Proposed selected identity differs from actual checkpoint evidence')
    paths, hashes = _source_inventory(contract, source_paths)
    contract_api.validate_review(contract, review, actual_source_hashes=hashes,
        calibration_record=calibration_record, funding_snapshot=funding_snapshot,
        as_of_utc=as_of_utc, actual_pricing_sha256=actual_pricing_sha256)
    calibration_files = _calibration_inventory(calibration_source_paths, contract, calibration_record, checkpoint)
    token = secrets.token_hex(32)
    contents = {'schema_version': 1, 'version': VERSION, 'stage': 'sealed_pre_access_not_dispatched',
        'created_at_utc': now(),
        'contract': contract, 'checkpoint': checkpoint, 'source_paths': paths,
        'review': review, 'calibration': calibration_record, 'calibration_files': calibration_files,
        'funding_snapshot': funding_snapshot,
        'reviewed_as_of_utc': as_of_utc, 'pricing_sha256': actual_pricing_sha256,
        'access_registry_path': str(registry), 'owner_sha256': contract_api.digest(token),
        'official_test_accessed_by_seal': False, 'paid_work_launched': False}
    sealed = _hash_record(contents, 'seal_sha256')
    if registry.exists():
        raise ValueError('Another final protocol acquired access during validation')
    output.mkdir(parents=True)
    _write_once(output/'access_owner.json', {'owner_token': token, 'seal_sha256': sealed['seal_sha256']})
    _write_once(output/'seal.json', sealed)
    return verify(output)


def verify(folder):
    folder = _safe(folder, private=True)
    sealed = read(folder/'seal.json')
    _check_record(sealed, 'seal_sha256')
    if (sealed.get('schema_version') != 1 or sealed.get('version') != VERSION
            or sealed.get('official_test_accessed_by_seal') is not False
            or sealed.get('paid_work_launched') is not False):
        raise ValueError('Unknown physical seal schema')
    contract = contract_api.validate(sealed['contract'])
    paths, hashes = _source_inventory(contract, sealed['source_paths'])
    if paths != sealed['source_paths'] or inspect_checkpoint(sealed['checkpoint']['run_path']) != sealed['checkpoint']:
        raise ValueError('Physical source/checkpoint provenance changed after sealing')
    if contract['protocol']['selected'] != sealed['checkpoint']['selected']:
        raise ValueError('Physical checkpoint no longer matches selected identity')
    contract_api.validate_review(contract, sealed['review'], actual_source_hashes=hashes,
        calibration_record=sealed['calibration'], funding_snapshot=sealed['funding_snapshot'],
        as_of_utc=sealed['reviewed_as_of_utc'], actual_pricing_sha256=sealed['pricing_sha256'])
    paths = {role: item['result_path'] for role, item in sealed['calibration_files'].items()}
    if _calibration_inventory(paths, contract, sealed['calibration'], sealed['checkpoint']) != sealed['calibration_files']:
        raise ValueError('Physical calibration provenance changed after sealing')
    registry = _registry(sealed['access_registry_path'])
    owner = read(folder/'access_owner.json')
    if (set(owner) != {'owner_token', 'seal_sha256'} or not isinstance(owner.get('owner_token'), str)
            or not re.fullmatch('[a-f0-9]{64}', owner['owner_token'])
            or owner.get('seal_sha256') != sealed['seal_sha256'] or contract_api.digest(owner['owner_token']) != sealed['owner_sha256']):
        raise ValueError('Physical access owner changed')
    if registry.exists():
        permit = read(registry)
        _validate_permit(permit)
        if any(permit.get(key) != value for key, value in _permit_identity(sealed, permit.get('destination')).items()):
            raise ValueError('Another protocol owns final access; this seal cannot be used')
    return sealed


def read_owner(folder):
    verify(folder)
    return read(Path(folder)/'access_owner.json')['owner_token']


def _destination(folder, sealed, destination):
    destination = _safe(destination, private=True, exists=False)
    if destination == PRIVATE_ROOT.resolve():
        raise ValueError('Loader destination must be a distinct private directory')
    runtime = _registry(sealed['access_registry_path']).parent
    if destination.is_relative_to(runtime) or runtime.is_relative_to(destination):
        raise ValueError('Official source destination cannot overlap shared supervisor state')
    for protected in (_safe(folder, private=True), _safe(sealed['checkpoint']['run_path'], private=True)):
        if destination.is_relative_to(protected) or protected.is_relative_to(destination):
            raise ValueError('Official source destination cannot overlap seal or development artifacts')
    return str(destination)


def _permit_identity(sealed, destination):
    return {'protocol_family': VERSION, 'role': 'final_eval_only',
        'freeze_sha256': sealed['contract']['freeze_sha256'], 'seal_sha256': sealed['seal_sha256'],
        'owner_sha256': sealed['owner_sha256'], 'destination': destination, 'test_access_count': 1}


def _validate_permit(permit):
    fields = {'protocol_family', 'role', 'freeze_sha256', 'seal_sha256', 'owner_sha256',
        'destination', 'test_access_count', 'stage', 'began_at_utc', 'permit_sha256'}
    if (set(permit) != fields or type(permit.get('test_access_count')) is not int
            or permit['test_access_count'] != 1 or permit.get('stage') != 'access_begun_before_source_read'
            or not isinstance(permit.get('destination'), str)):
        raise ValueError('Unknown global final-access permit')
    contract_api._time(permit['began_at_utc'])
    _check_record(permit, 'permit_sha256')


def check_access(folder, *, owner_token, destination):
    sealed = verify(folder)
    destination = _destination(folder, sealed, destination)
    if contract_api.digest(owner_token) != sealed['owner_sha256']:
        raise ValueError('Access belongs to a different durable owner')
    registry = _registry(sealed['access_registry_path'])
    if not registry.exists():
        raise ValueError('Durable global access permit must precede dataset use')
    permit = read(registry)
    _validate_permit(permit)
    if any(permit.get(k) != v for k, v in _permit_identity(sealed, destination).items()):
        raise ValueError('Official access owner/destination/protocol changed')
    return permit


def begin_access(folder, *, owner_token, destination, loader_authorized=False, as_of_utc=None):
    if loader_authorized is not True:
        raise ValueError('Only an explicitly authorized future loader can claim source access')
    sealed = verify(folder)
    destination = _destination(folder, sealed, destination)
    if contract_api.digest(owner_token) != sealed['owner_sha256']:
        raise ValueError('Access belongs to a different durable owner')
    registry = _registry(sealed['access_registry_path'])
    if registry.exists():
        return check_access(folder, owner_token=owner_token, destination=destination)
    contract_api.validate_review(sealed['contract'], sealed['review'],
        actual_source_hashes=sealed['contract']['protocol']['source_hashes'],
        calibration_record=sealed['calibration'], funding_snapshot=sealed['funding_snapshot'],
        as_of_utc=as_of_utc or now(), actual_pricing_sha256=sealed['pricing_sha256'])
    value = _hash_record(dict(_permit_identity(sealed, destination),
        stage='access_begun_before_source_read', began_at_utc=now()), 'permit_sha256')
    try:
        _write_once(registry, value)
    except FileExistsError:
        return check_access(folder, owner_token=owner_token, destination=destination)
    return value


def dataset_receipt_path(sealed_or_folder):
    sealed = sealed_or_folder if isinstance(sealed_or_folder, dict) else verify(sealed_or_folder)
    registry = _registry(sealed['access_registry_path'])
    return registry.with_name(registry.stem+'.dataset_receipt.json')


def _dataset_value(folder, *, owner_token, destination, receipt):
    permit = check_access(folder, owner_token=owner_token, destination=destination)
    sealed = verify(folder)
    fields = {'full_source_sha256', 'sample_sha256', 'binding_sha256', 'population_count',
        'sample_count', 'indices_sha256', 'input_hash_convention'}
    if not isinstance(receipt, dict) or set(receipt) != fields:
        raise ValueError('Dataset receipt must contain hash-bound metadata only')
    for key in ('full_source_sha256', 'sample_sha256', 'binding_sha256', 'indices_sha256'):
        contract_api.require_hash(receipt[key])
    data = sealed['contract']['protocol']['dataset']
    if (type(receipt['population_count']) is not int or receipt['population_count'] != 1319
            or type(receipt['sample_count']) is not int or receipt['sample_count'] != data['sample_count']
            or receipt['indices_sha256'] != data['indices_sha256']
            or receipt['input_hash_convention'] != INPUT_HASH_CONVENTION):
        raise ValueError('Persisted dataset differs from the one sealed target')
    value = _hash_record(dict(receipt, permit_sha256=permit['permit_sha256'],
        **_permit_identity(sealed, permit['destination'])), 'receipt_sha256')
    return sealed, value


def check_dataset_receipt(folder, *, owner_token, destination, receipt):
    sealed, value = _dataset_value(folder, owner_token=owner_token, destination=destination, receipt=receipt)
    if read(dataset_receipt_path(sealed)) != value:
        raise ValueError('Persisted global dataset receipt differs')
    return value


def bind_dataset_receipt(folder, *, owner_token, destination, receipt):
    sealed, value = _dataset_value(folder, owner_token=owner_token, destination=destination, receipt=receipt)
    path = dataset_receipt_path(sealed)
    try:
        _write_once(path, value)
    except FileExistsError:
        if read(path) != value:
            raise ValueError('Append-only dataset receipt already binds different source/sample bytes')
    return value


if __name__ == '__main__':
    print(json.dumps({'stage': 'implementation_only_no_seal_created',
        'official_test_accessed': False, 'paid_work_launched': False,
        'actual_checkpoint_choice_required': True, 'source_and_whole_bundle_review_required': True}))
