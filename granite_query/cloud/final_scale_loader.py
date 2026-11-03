"""Future permit-first1000/full1319 loader. No default dataset access.

Imports and metadata inspection never fetch or open test content. Preparation
and prepared-content reads each require an explicit authorization argument.
Only a future reviewed seal may claim the shared global source permit. A durable
fetch marker precedes one GET; unknown transmissions are never retried here.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from cloud import final_scale_contract as contract_api
from cloud import final_scale_receipts as receipt_api
from cloud import final_scale_seal as seal

ROLE = 'final_eval_only'
INPUT_HASH_CONVENTION = 'qid-index-canonical-messages-v1'
MAX_SOURCE_BYTES = 8*1024*1024
NUMBER = re.compile(r'[+-]?(?:(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d*)?|\.\d+)')
FILES = {'loader.lock', 'fetch_started.json', 'source.download', 'download_receipt.json',
    'source.jsonl', 'sample.jsonl', 'sample_binding.json', 'sample_manifest.json', 'loader_state.json'}


def sha_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)+'\n').encode('utf-8')


def rows_bytes(rows):
    return b''.join(encoded(row) for row in rows)


def read(path):
    return json.loads(_raw(path, 4*1024*1024).decode('utf-8-sig'))


def private(path):
    # Inspect the supplied path and every ancestor before resolution; resolving
    # first would erase a junction/symlink alias even if it targets private data.
    return seal._safe(path, private=True, exists=False)


def _raw(path, limit=MAX_SOURCE_BYTES):
    path = seal._safe(path, private=True)
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError('Prepared artifact is missing, linked or exceeds its byte cap')
    return path.read_bytes()


def _replace(source, target):
    for attempt in range(4):
        try:
            Path(source).replace(target)
            return
        except PermissionError:
            if attempt == 3:
                raise
            time.sleep(.05*(2**attempt))


def _promote(source, target, expected_sha256):
    """Local-only recovery; matching existing targets are never overwritten."""
    source, target = Path(source), Path(target)
    if target.exists():
        if sha_bytes(_raw(target, MAX_SOURCE_BYTES+1)) != expected_sha256:
            raise ValueError('Existing immutable artifact differs')
        if source.exists() and sha_bytes(_raw(source, MAX_SOURCE_BYTES+1)) != expected_sha256:
            raise ValueError('Pending and persisted artifact conflict')
        return
    if sha_bytes(_raw(source, MAX_SOURCE_BYTES+1)) != expected_sha256:
        raise ValueError('Pending durable artifact hash differs')
    _replace(source, target)


def ensure_bytes(path, raw):
    """Fsync one immutable artifact; only filesystem renames are retried."""
    path = seal._safe(path, private=True, exists=False)
    temporary = seal._safe(path.with_name(path.name+'.pending'), private=True, exists=False)
    if path.exists():
        if _raw(path, MAX_SOURCE_BYTES+1) != raw:
            raise ValueError('Existing immutable artifact bytes differ')
        if temporary.exists() and _raw(temporary, MAX_SOURCE_BYTES+1) != raw:
            raise ValueError('Conflicting immutable pending bytes')
        return
    if temporary.exists():
        if _raw(temporary, MAX_SOURCE_BYTES+1) != raw:
            raise ValueError('Ambiguous pending artifact needs local reconciliation')
    else:
        with temporary.open('xb') as handle:
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
    _promote(temporary, path, sha_bytes(raw))


def ensure_json(path, value):
    ensure_bytes(path, encoded(value))


def _state(output, stage, **metadata):
    value = dict(stage=stage, updated_at_utc=datetime.now(timezone.utc).isoformat(), **metadata)
    # A pre-existing status temporary must never be followed as a symlink or
    # junction. This check also protects direct/recovery uses of this writer.
    target = seal._safe(Path(output)/'loader_state.json', private=True, exists=False)
    temporary = seal._safe(Path(output)/'loader_state.json.pending', private=True, exists=False)
    with temporary.open('wb') as handle:
        handle.write(encoded(value)); handle.flush(); os.fsync(handle.fileno())
    _replace(temporary, target)


def source_url(contract):
    contract_api.validate(contract)
    data = contract['protocol']['dataset']
    expected = {'repository': 'openai/grade-school-math',
        'revision': '3101c7d5072418e28b9008a6636bde82a006892c',
        'relative_path': 'grade_school_math/data/test.jsonl'}
    if any(data.get(key) != value for key, value in expected.items()):
        raise ValueError('Only the predeclared canonical pinned source is accepted')
    return 'https://raw.githubusercontent.com/'+data['repository']+'/'+data['revision']+'/'+data['relative_path']


def fetch(url, *, authorized=False):
    """One bounded future GET; no retries or import-time activity."""
    if authorized is not True:
        raise ValueError('Explicit source-fetch authorization is required')
    request = urllib.request.Request(url, headers={'User-Agent': 'GraniteQuery-SealedFinalScale/1.0'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read(MAX_SOURCE_BYTES+1)


def question_input_hash(row, contract):
    """Canonical shared user input; IDs/indices included, gold excluded."""
    return contract_api.digest({'id': row['id'], 'source_index': row['source_index'],
        'messages': [{'role': 'user', 'content': contract['protocol']['inference']['user_prefix']+row['prompt']}]})


def _reference(answer):
    if not isinstance(answer, str) or answer.count('####') != 1:
        raise ValueError('Canonical reference must have one final numeric marker')
    final = answer.rsplit('####', 1)[1].strip()
    if len(final) > 128 or not NUMBER.fullmatch(final):
        raise ValueError('Canonical final reference is not a bounded decimal')
    try:
        number = Decimal(final.replace(',', ''))
    except InvalidOperation:
        raise ValueError('Invalid canonical final reference') from None
    if not number.is_finite():
        raise ValueError('Canonical reference must be finite')
    return final


def select(raw, contract):
    """Pure supplied-byte parser. Never filters, resamples or trains on rows."""
    contract_api.validate(contract)
    if not isinstance(raw, bytes) or len(raw) > MAX_SOURCE_BYTES:
        raise ValueError('Canonical source exceeds bounded complete-byte contract')
    lines = raw.decode('utf-8-sig').split('\n')
    while lines and not lines[-1].strip():
        lines.pop()
    if any(not line.strip() for line in lines) or len(lines) != 1319:
        raise ValueError('Canonical source must retain all1319 ordered rows')
    population = []
    for line in lines:
        row = json.loads(line)
        if (not isinstance(row, dict) or set(row) != {'question', 'answer'}
                or not isinstance(row['question'], str) or not row['question'].strip()):
            raise ValueError('Canonical row schema differs')
        population.append((row['question'], row['answer'], _reference(row['answer'])))
    selected = []
    for index in contract['protocol']['dataset']['indices']:
        prompt, reference, gold = population[index]
        selected.append({'id': f'gsm8k:test:{index:05d}', 'source_index': index,
            'prompt': prompt, 'gold_answer': gold, 'reference_solution': reference,
            'source_split': 'test', 'role': ROLE, 'training_eligible': False})
    if [row['id'] for row in selected] != contract_api.expected_ids(contract):
        raise ValueError('Canonical selected identities differ')
    return selected


def make_binding(contract, raw, selected):
    """Pure metadata; actual source/sample bytes are hashed without mutation."""
    value = {'schema_version': 1, 'role': ROLE, 'freeze_sha256': contract['freeze_sha256'],
        'source_bundle_sha256': contract_api.digest(contract['protocol']['source_hashes']),
        'full_source_sha256': sha_bytes(raw), 'sample_sha256': sha_bytes(rows_bytes(selected)),
        'questions': [{'id': row['id'], 'source_index': row['source_index'], 'gold_answer': row['gold_answer'],
            'input_sha256': question_input_hash(row, contract)} for row in selected]}
    binding = dict(value, binding_sha256=contract_api.digest(value))
    receipt_api.validate_binding(contract, binding)
    return binding


def _loader_role(sealed):
    contract = sealed['contract']; contract_api.validate(contract)
    name = Path(__file__).name
    if (name not in contract['protocol']['source_roles']['loader']
            or contract['protocol']['source_hashes'].get(name) != sha_bytes(Path(__file__).read_bytes())):
        raise ValueError('This loader differs from the sealed reviewed source role')


def _owner(folder, sealed):
    value = read(Path(folder)/'access_owner.json')
    token = value.get('owner_token')
    if (not isinstance(token, str) or not token or value.get('seal_sha256') != sealed['seal_sha256']
            or contract_api.digest(token) != sealed['owner_sha256']):
        raise ValueError('Final source owner does not match the reviewed seal')
    return token


def _identity(sealed, output):
    return {'schema_version': 1, 'role': ROLE, 'seal_sha256': sealed['seal_sha256'],
        'freeze_sha256': sealed['contract']['freeze_sha256'], 'owner_sha256': sealed['owner_sha256'],
        'destination_sha256': contract_api.digest(str(output)),
        'source_url_sha256': sha_bytes(source_url(sealed['contract']).encode()), 'max_fetch_attempts': 1}


def _download(output, expected):
    marker = read(output/'fetch_started.json')
    if marker != expected:
        raise ValueError('Fetch marker belongs to another protocol, owner or destination')
    receipt = read(output/'download_receipt.json')
    _validate_download_receipt(receipt, expected)
    source, pending = output/'source.jsonl', output/'source.download'
    path = source if source.exists() else pending
    raw = _raw(path)
    if len(raw) != receipt['full_source_bytes'] or sha_bytes(raw) != receipt.get('full_source_sha256'):
        raise ValueError('Persisted source bytes differ from original durable download')
    if pending.exists() and sha_bytes(_raw(pending)) != receipt['full_source_sha256']:
        raise ValueError('Conflicting persisted download bytes')
    _promote(path, source, receipt['full_source_sha256'])
    return raw


def _validate_download_receipt(receipt, expected):
    if (not isinstance(receipt, dict) or set(receipt) != set(expected) | {
                'full_source_sha256', 'full_source_bytes', 'download_receipt_sha256'}
            or any(receipt.get(key) != value for key, value in expected.items())
            or receipt.get('download_receipt_sha256') != contract_api.digest({k: v for k, v in receipt.items() if k != 'download_receipt_sha256'})
            or type(receipt.get('full_source_bytes')) is not int or not 0 < receipt['full_source_bytes'] <= MAX_SOURCE_BYTES):
        raise ValueError('Durable download receipt differs or is not complete bounded bytes')
    contract_api.require_hash(receipt['full_source_sha256'])


def _dataset_receipt(contract, binding):
    return {key: binding[key] for key in ('full_source_sha256', 'sample_sha256', 'binding_sha256')} | {
        'population_count': 1319, 'sample_count': contract['protocol']['dataset']['sample_count'],
        'indices_sha256': contract['protocol']['dataset']['indices_sha256'],
        'input_hash_convention': INPUT_HASH_CONVENTION}


def _manifest(sealed, output, binding):
    contract = sealed['contract']
    return {'schema_version': 1, 'role': ROLE, 'training_eligible': False, 'official_test_used': True,
        'seal_sha256': sealed['seal_sha256'], 'freeze_sha256': contract['freeze_sha256'],
        'source_bundle_sha256': binding['source_bundle_sha256'], **_dataset_receipt(contract, binding),
        'full_test_evaluation': contract['protocol']['dataset']['full_test_evaluation'],
        'question_ids_sha256': contract['protocol']['dataset']['question_ids_sha256'],
        'destination_sha256': contract_api.digest(str(output))}


def prepare(seal_folder, output, *, authorized=False, fetcher=None):
    """Explicit future access only. A marker with unknown bytes stops recovery."""
    if authorized is not True:
        raise ValueError('Explicit final-test access authorization is required')
    seal_folder, output = private(seal_folder), private(output)
    sealed = seal.verify(seal_folder); _loader_role(sealed)
    # This is a read-only path-policy check. It must precede mkdir, lock and
    # error-state writes, including when a forbidden child does not exist yet.
    output = Path(seal._destination(seal_folder, sealed, output))
    if output.exists():
        for path in output.iterdir():
            if path.name not in FILES and path.name.removesuffix('.pending') not in FILES:
                raise ValueError('Unrelated artifacts already occupy this loader destination')
            child = seal._safe(path, private=True)
            if not child.is_file():
                raise ValueError('Loader destination children must be regular unlinked files')
    output.mkdir(parents=True, exist_ok=True)
    lock = output/'loader.lock'; fd = os.open(lock, os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    permit_bound = False
    try:
        os.write(fd, str(os.getpid()).encode('ascii')); os.fsync(fd)
        owner = _owner(seal_folder, sealed)
        permit_reused = Path(sealed['access_registry_path']).exists()
        permit = seal.begin_access(seal_folder, owner_token=owner, destination=output, loader_authorized=True)
        permit_bound = True
        expected = _identity(sealed, output)
        marker = output/'fetch_started.json'
        if marker.exists():
            # No GET can occur again, even if local output is invalid or missing.
            if not (output/'download_receipt.json').exists():
                pending_receipt = output/'download_receipt.json.pending'
                if pending_receipt.exists():
                    saved = read(pending_receipt)
                    _validate_download_receipt(saved, expected)
                    ensure_json(output/'download_receipt.json', saved)
                else:
                    raise ValueError('Ambiguous prior source fetch; no automatic retry')
            raw = _download(output, expected)
        else:
            if any((output/name).exists() for name in ('source.jsonl', 'source.download', 'download_receipt.json', 'sample.jsonl')):
                raise ValueError('Orphaned data without original fetch intent')
            ensure_json(marker, expected)
            _state(output, 'fetch_started', seal_sha256=sealed['seal_sha256'])
            raw = (fetch(source_url(sealed['contract']), authorized=True) if fetcher is None
                else fetcher(source_url(sealed['contract'])))
            if not isinstance(raw, bytes) or len(raw) > MAX_SOURCE_BYTES+1:
                raise ValueError('Fetcher did not return bounded source bytes')
            ensure_bytes(output/'source.download', raw)
            download = dict(expected, full_source_sha256=sha_bytes(raw), full_source_bytes=len(raw))
            ensure_json(output/'download_receipt.json', dict(download, download_receipt_sha256=contract_api.digest(download)))
            raw = _download(output, expected)
        selected = select(raw, sealed['contract'])
        binding = make_binding(sealed['contract'], raw, selected)
        sample_raw = rows_bytes(selected); manifest = _manifest(sealed, output, binding)
        ensure_bytes(output/'sample.jsonl', sample_raw)
        ensure_json(output/'sample_binding.json', binding)
        ensure_json(output/'sample_manifest.json', manifest)
        receipt_reused = seal.dataset_receipt_path(sealed).exists()
        receipt = seal.bind_dataset_receipt(seal_folder, owner_token=owner, destination=output,
            receipt=_dataset_receipt(sealed['contract'], binding))
        _state(output, 'prepared_final_eval_only', **manifest)
        return {'stage': 'prepared_final_eval_only', 'count': len(selected), 'role': ROLE,
            'training_eligible': False, 'official_test_used': True, 'paid_work_launched': False,
            'source_sha256': binding['full_source_sha256'], 'sample_sha256': binding['sample_sha256'],
            'binding_sha256': binding['binding_sha256'], 'permit_reused': permit_reused,
            'receipt_reused': receipt_reused}
    except Exception as error:
        if permit_bound:
            try:
                _state(output, 'action_required', error_type=type(error).__name__,
                    seal_sha256=sealed['seal_sha256'],
                    note='Inspect immutable local receipts and source ownership. No source request is retried automatically.')
            except (OSError, ValueError):
                pass
        raise
    finally:
        os.close(fd)
        if lock.exists() and lock.read_text(encoding='ascii').strip() == str(os.getpid()):
            lock.unlink()


def load_prepared(seal_folder, output, *, authorized=False):
    """Explicit prepared-content read; no repair, permit creation or download."""
    if authorized is not True:
        raise ValueError('Explicit prepared final-content read authorization is required')
    seal_folder, output = private(seal_folder), private(output)
    sealed = seal.verify(seal_folder); _loader_role(sealed)
    if (output/'loader.lock').exists():
        raise ValueError('Loader owner is active; no partial-content reads')
    owner = _owner(seal_folder, sealed)
    seal.check_access(seal_folder, owner_token=owner, destination=output)
    expected = _identity(sealed, output)
    # Unlike preparation, reading never promotes an interrupted artifact.
    if read(output/'fetch_started.json') != expected:
        raise ValueError('Prepared sample lacks its original source intent')
    download = read(output/'download_receipt.json')
    _validate_download_receipt(download, expected)
    raw = _raw(output/'source.jsonl')
    if download.get('full_source_sha256') != sha_bytes(raw) or download.get('full_source_bytes') != len(raw):
        raise ValueError('Prepared source bytes differ')
    selected = select(raw, sealed['contract']); binding = make_binding(sealed['contract'], raw, selected)
    sample_raw = rows_bytes(selected); manifest = _manifest(sealed, output, binding)
    if (_raw(output/'sample.jsonl') != sample_raw or read(output/'sample_binding.json') != binding
            or read(output/'sample_manifest.json') != manifest):
        raise ValueError('Prepared sample or binding differs from persisted canonical source')
    seal.check_dataset_receipt(seal_folder, owner_token=owner, destination=output,
        receipt=_dataset_receipt(sealed['contract'], binding))
    return {'sealed': sealed, 'manifest': manifest, 'binding': binding, 'sample_raw': sample_raw, 'rows': selected}


def inspect_metadata(seal_folder, output):
    """Read local status metadata only; never source/sample bytes or references."""
    seal_folder, output = private(seal_folder), private(output)
    sealed = seal.verify(seal_folder)
    path = output/'loader_state.json'
    status = read(path) if path.exists() else {'stage': 'not_prepared'}
    stages = {'not_prepared', 'fetch_started', 'prepared_final_eval_only', 'action_required'}
    if (not isinstance(status, dict) or not isinstance(status.get('stage'), str) or status['stage'] not in stages
            or path.exists() and status.get('seal_sha256') != sealed['seal_sha256']):
        return {'stage': 'invalid_local_metadata', 'seal_sha256': sealed['seal_sha256'],
            'source_access_performed_by_inspection': False}
    allowed = ('stage', 'updated_at_utc', 'sample_count', 'population_count', 'full_source_sha256',
        'sample_sha256', 'binding_sha256', 'role', 'training_eligible', 'official_test_used', 'error_type')
    public = {key: status[key] for key in allowed if key in status}
    if 'updated_at_utc' in public:
        try:
            stamp = datetime.fromisoformat(public['updated_at_utc'])
            if stamp.tzinfo is None:
                raise ValueError('Timestamp must include a timezone')
        except (ValueError, TypeError):
            raise ValueError('Invalid local inspection timestamp') from None
    if 'error_type' in public and public['error_type'] not in {'ValueError', 'OSError', 'PermissionError',
            'FileNotFoundError', 'FileExistsError', 'RuntimeError', 'TimeoutError', 'URLError',
            'HTTPError', 'UnicodeDecodeError', 'JSONDecodeError'}:
        public['error_type'] = 'OtherError'
    for key in ('full_source_sha256', 'sample_sha256', 'binding_sha256'):
        if key in public:
            contract_api.require_hash(public[key])
    if ('sample_count' in public and public['sample_count'] != sealed['contract']['protocol']['dataset']['sample_count']
            or 'population_count' in public and public['population_count'] != 1319
            or 'role' in public and public['role'] != ROLE
            or 'training_eligible' in public and public['training_eligible'] is not False
            or 'official_test_used' in public and type(public['official_test_used']) is not bool):
        raise ValueError('Local inspection metadata differs from sealed scope')
    return {'seal_sha256': sealed['seal_sha256'], 'source_access_performed_by_inspection': False, **public}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('inspect', 'prepare'), nargs='?', default='inspect')
    parser.add_argument('--seal-folder', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--authorize-final-test-access', action='store_true')
    args = parser.parse_args()
    result = prepare(args.seal_folder, args.output, authorized=args.authorize_final_test_access) if args.action == 'prepare' else inspect_metadata(args.seal_folder, args.output)
    print(json.dumps(result))
