"""Private paired256 TRAIN preparation and separately funded original calls.

No reservation, provider refresh, GPU launch, public generation or retry occurs
here. Explicit collection needs the exact existing reviewed seven-dollar job.
An intent precedes transmission; exact response bytes precede parsing. Unknown
transmissions fail closed and are never sent again by recovery or inspection.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
from decimal import Decimal
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from cloud import native_reasoning_contract as contract
from cloud import human_math_cohort as source
from cloud import final_scale_seal as paths_api
from cloud.deepseek_reconcile import require_fresh_deepseek_budget
from cloud.math_teacher import other_collector_locks
from cloud.run_api_pilot import credential
from cloud.student_valuation import load_tokenizer
from ranking.verification import numeric_answer

RUN = ROOT/'runs/native_reasoning256_v4'
VERSION = 'native-reasoning-paired256-originals-v4'
API_URL = 'https://api.deepseek.com/chat/completions'
QUESTIONS = 256
SEED = 20261112
MODES = ('concise', 'thinking')
CAPS = {'concise': 1024, 'thinking': 4096}
MAX_INPUT_TOKENS = 2000
MAX_MESSAGES_BYTES = 1006
MAX_RESPONSE_BYTES = 1024*1024
SOCKET_TIMEOUT = 120
HTTP_WALL_SECONDS = 120
MAX_DRAIN_SECONDS = 240
LAUNCH_WINDOW_SECONDS = 1800
RESERVATION = Decimal('7')
PRICING = {'currency': 'USD', 'unit': 'per_1000000_tokens',
    'cache_miss_input_peak': '1.32', 'output_peak': '3.96',
    'verified_on': '2026-11-03',
    'source': 'https://api-docs.deepseek.com/quick_start/pricing/',
    'thinking_source': 'https://api-docs.deepseek.com/guides/thinking_mode/',
    'api_source': 'https://api-docs.deepseek.com/api/create-chat-completion/'}
COST_BOUND = Decimal(QUESTIONS)*(2*MAX_INPUT_TOKENS*Decimal('1.32')+
    sum(CAPS.values())*Decimal('3.96'))/Decimal(1000000)


class AmbiguousAttemptError(RuntimeError):
    pass


def now(): return datetime.now(timezone.utc).isoformat()
def sha(raw): return hashlib.sha256(raw).hexdigest()
def digest(value): return sha(encoded(value))
def encoded(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
def rows_bytes(rows): return b''.join(encoded(row)+b'\n' for row in rows)


def _pairs(values):
    result = {}
    for key, value in values:
        if key in result: raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def parse(raw):
    return json.loads(raw, object_pairs_hook=_pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def private(path):
    """Check ancestor aliases before resolution and restrict all writes to runs."""
    checked = paths_api._safe(path, private=True, exists=False)
    if not checked.is_relative_to((ROOT/'runs').resolve()): raise ValueError('Use ignored cloud/runs only')
    return checked


def read(path):
    path = private(path)
    if path.stat().st_size > 32*1024*1024: raise ValueError('Local metadata exceeds bound')
    return parse(path.read_bytes())


def read_rows(path):
    path = private(path)
    # LF only: Unicode line separators inside preserved channels are not rows.
    if path.stat().st_size > 64*1024*1024: raise ValueError('Private rows exceed bound')
    return [parse(line) for line in path.read_bytes().decode('utf-8-sig').split('\n') if line.strip()]


def write_bytes(path, raw, *, immutable=True):
    path = private(path); path.parent.mkdir(parents=True, exist_ok=True)
    if immutable:
        try:
            with path.open('xb') as handle: handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        except FileExistsError:
            if path.read_bytes() != raw: raise ValueError('Immutable private artifact differs')
        return
    pending = private(path.with_name(path.name+'.pending'))
    with pending.open('xb') as handle: handle.write(raw); handle.flush(); os.fsync(handle.fileno())
    for attempt in range(4):
        try: os.replace(pending, path); break
        except PermissionError:
            if attempt == 3: raise
            time.sleep(.05*2**attempt)


def write(path, value, *, immutable=True): write_bytes(path, encoded(value)+b'\n', immutable=immutable)


def payload(row, mode):
    if mode not in MODES or row.get('source_split') != 'train' or not row['id'].startswith('gsm8k:train:'):
        raise ValueError('Only canonical TRAIN paired modes are permitted')
    result = {'model': contract.TEACHER_MODEL, 'max_tokens': CAPS[mode], 'stream': False,
        'thinking': {'type': 'disabled' if mode == 'concise' else 'enabled'},
        'messages': [{'role': 'user', 'content': contract.PREFIX+row['prompt']}]}
    if mode == 'thinking': result['reasoning_effort'] = 'high'
    return result


def input_bytes(row): return len(encoded(payload(row, 'concise')['messages']))


def requests_for(rows):
    rng = random.Random(SEED ^ 0x5A17); result = []
    for row in rows:
        modes = list(MODES); rng.shuffle(modes)
        for order, mode in enumerate(modes):
            body = payload(row, mode)
            result.append({'id': row['id']+'::'+mode, 'question_id': row['id'], 'mode': mode,
                'within_pair_position': order, 'payload': body, 'request_sha256': digest(body)})
    return result


def dependencies():
    return [Path(__file__), Path(contract.__file__), Path(source.__file__), ROOT/'final_scale_seal.py',
        ROOT/'math_teacher.py', ROOT/'matched_teacher.py', ROOT/'deepseek_reconcile.py', ROOT/'run_api_pilot.py',
        ROOT/'student_valuation.py', ROOT.parent/'ranking/prepare_gsm8k.py', ROOT.parent/'ranking/verification.py']


def protocol_identity(tokenizer):
    return {'version': VERSION, 'student': contract.protocol(), 'tokenizer': contract.tokenizer_identity(tokenizer),
        'teacher_model': contract.TEACHER_MODEL, 'caps': CAPS, 'thinking_effort': 'high',
        'question_count': QUESTIONS, 'original_requests': 2*QUESTIONS, 'seed': SEED,
        'max_concurrent': 4, 'automatic_retries': 0, 'max_input_tokens': MAX_INPUT_TOKENS,
        'max_messages_utf8_bytes': MAX_MESSAGES_BYTES, 'max_response_bytes': MAX_RESPONSE_BYTES,
        'socket_timeout_seconds': SOCKET_TIMEOUT, 'request_wall_deadline_seconds': HTTP_WALL_SECONDS,
        'max_launch_window_seconds': LAUNCH_WINDOW_SECONDS, 'conservative_max_drain_seconds': MAX_DRAIN_SECONDS,
        'pricing': PRICING, 'original_call_cost_bound_usd': str(COST_BOUND),
        'reserved_usd_required': str(RESERVATION), 'official_test_accessed': False,
        'future_reference': {'thinking_output_cap': 8192, 'authorized_by_this_plan': False,
            'note': 'An8192 strong-reference option needs a distinct reviewed/funded plan; this paired phase remains1024/4096.'},
        'source_code_hashes': {path.relative_to(ROOT.parent).as_posix(): sha(path.read_bytes()) for path in dependencies()}}


def select_candidates(canonical_rows, records):
    excluded, ancestry = source.ancestry_exclusions(canonical_rows, records)
    ordered = sorted(canonical_rows, key=lambda row: row['id']); random.Random(SEED).shuffle(ordered)
    result, signatures, counts = [], [], Counter()
    for row in ordered:
        if row.get('source_split') != 'train' or not row['id'].startswith('gsm8k:train:'):
            raise ValueError('Only canonical TRAIN selection input is permitted')
        if row['id'] in excluded: counts['prior_question_or_detectable_ancestry'] += 1; continue
        if input_bytes(row) > MAX_MESSAGES_BYTES: counts['input_byte_bound'] += 1; continue
        proof, reason, _ = source.annotation_check(row['reference_solution'], row['gold_answer'])
        if proof is None or numeric_answer(str(row['gold_answer'])) is None: counts[reason] += 1; continue
        signature = source.masked_shingles(row['prompt'])
        if any(len(signature & previous)/max(1, len(signature | previous)) >= .85 for previous in signatures):
            counts['within_cohort_near_duplicate'] += 1; continue
        result.append(dict(row, source_revision=source.REVISION, annotation_verification=proof,
            reference_solution_sha256=sha(row['reference_solution'].encode('utf-8')),
            prompt_sha256=sha(row['prompt'].encode('utf-8')), reference_semantics_verified=False))
        signatures.append(signature)
        if len(result) == QUESTIONS: break
    if len(result) != QUESTIONS: raise ValueError('Insufficient unused bounded canonical training capacity')
    return result, {'ancestry': ancestry, 'selection_decision_counts': dict(counts)}


def load_exclusions(output):
    """Read past TRAIN/development artifacts, rejecting final owners first.

    The legacy path discovery reads metadata only. This extra boundary excludes
    every final-family directory and sealed-role metadata before question bytes
    are opened, including future scaled bundles unknown to that older helper.
    """
    records, artifacts = [], []
    for path in source.exclusion_artifacts(output):
        path = paths_api._safe(path)
        if path != source.PROBES.resolve():
            if not path.is_relative_to((ROOT/'runs').resolve()): raise ValueError('Question exclusion path escaped TRAIN workspace')
            top = path.relative_to(ROOT/'runs').parts[0]
            if 'final' in top.casefold() or 'test' in top.casefold(): continue
            owner = ROOT/'runs'/top; blocked = False
            for name in ('plan.json', 'bundle.json', 'manifest.json'):
                metadata_path = paths_api._safe(owner/name, exists=False)
                if not metadata_path.exists(): continue
                if metadata_path.stat().st_size > 4*1024*1024: raise ValueError('Exclusion owner metadata exceeds bound')
                metadata = parse(metadata_path.read_bytes())
                def sealed(value):
                    if not isinstance(value, dict): return False
                    if (value.get('role') in ('final_eval_only', 'final_test') or value.get('evaluation_kind') == 'final_test'
                            or value.get('source_split') == 'test' or value.get('split') == 'test'
                            or any(value.get(key) is True for key in ('official_test_accessed','official_test_used','held_out_test_used'))): return True
                    return any(sealed(item) for item in value.values() if isinstance(item, dict))
                if sealed(metadata): blocked = True; break
            if blocked: continue
        raw = path.read_bytes(); usable = []
        for line in raw.decode('utf-8-sig').split('\n'):
            if line.strip():
                row = source.extract_question(parse(line))
                if row is not None: usable.append(row)
        records.extend(usable)
        artifacts.append({'run': path.relative_to(ROOT.parent).as_posix(), 'sha256': sha(raw), 'question_records': len(usable)})
    return records, artifacts


def prepare(output=RUN, *, tokenizer=None):
    output = private(output)
    if (output/'plan.json').exists(): return validate_run(output, tokenizer=tokenizer)[0]
    if output.exists() and any(output.iterdir()): raise ValueError('Partial preparation exists; do not overwrite')
    if sha(source.SOURCE.read_bytes()) != source.SOURCE_SHA: raise ValueError('Canonical TRAIN bytes changed')
    canonical_rows, _ = source.load_source(source.SOURCE, 'train')
    if len(canonical_rows) != 7473: raise ValueError('Canonical TRAIN population differs')
    records, artifacts = load_exclusions(output)
    required = [source.PROBES, ROOT/'runs/human_math_cohort2048_dev200_v1/candidates.jsonl',
        ROOT/'runs/human_math_cohort2048_dev200_v1/development.jsonl', ROOT/'runs/teacher_depth32_v1/candidates.jsonl']
    frozen_paths = {item['run'] for item in artifacts}
    if any(path.relative_to(ROOT.parent).as_posix() not in frozen_paths for path in required):
        raise ValueError('Required probe/human-development/teaching/depth32 exclusions missing')
    rows, exclusion_review = select_candidates(canonical_rows, records)
    requests = requests_for(rows); tokenizer = tokenizer or load_tokenizer(local_files_only=True)
    protocol = protocol_identity(tokenizer)
    body = {'schema_version': 1, 'version': VERSION, 'run_id': output.name, 'created_at_utc': now(),
        'role': 'training_pair_collection_only', 'source_split': 'train', 'official_test_accessed': False,
        'source_train_sha256': source.SOURCE_SHA, 'source_revision': source.REVISION,
        'candidate_count': QUESTIONS, 'max_original_requests': 2*QUESTIONS,
        'candidate_ids': [row['id'] for row in rows], 'candidates_sha256': sha(rows_bytes(rows)),
        'requests_sha256': sha(rows_bytes(requests)), 'protocol': protocol, 'protocol_sha256': digest(protocol),
        'exclusion_artifacts': artifacts, 'exclusion_review': exclusion_review,
        'reserved_usd_required': str(RESERVATION), 'conservative_max_cost_usd': str(COST_BOUND),
        'raw_reasoning_private': True, 'automatic_retries': 0, 'new_student_training': False,
        'limitations': 'Final-number/annotation matches do not prove reasoning; project ancestry is incomplete. Common full-fit pairs are a selected intersection, and caps/modes both change.'}
    plan = dict(body, plan_sha256=digest(body))
    output.mkdir(parents=True, exist_ok=True)
    write_bytes(output/'candidates.jsonl', rows_bytes(rows)); write_bytes(output/'requests.jsonl', rows_bytes(requests))
    write(output/'plan.json', plan)
    return plan


def validate_run(output, *, tokenizer=None):
    output = private(output); plan = read(output/'plan.json')
    body = {key: value for key, value in plan.items() if key != 'plan_sha256'}
    if (plan.get('plan_sha256') != digest(body) or plan.get('version') != VERSION or plan.get('run_id') != output.name
            or plan.get('role') != 'training_pair_collection_only' or plan.get('source_split') != 'train'
            or plan.get('official_test_accessed') is not False or plan.get('candidate_count') != QUESTIONS
            or plan.get('max_original_requests') != 2*QUESTIONS or plan.get('reserved_usd_required') != str(RESERVATION)
            or plan.get('conservative_max_cost_usd') != str(COST_BOUND)):
        raise ValueError('Immutable paired TRAIN plan, count or funding identity differs')
    rows, requests = read_rows(output/'candidates.jsonl'), read_rows(output/'requests.jsonl')
    if (sha((output/'candidates.jsonl').read_bytes()) != plan['candidates_sha256']
            or sha((output/'requests.jsonl').read_bytes()) != plan['requests_sha256']
            or len(rows) != QUESTIONS or len({row['id'] for row in rows}) != QUESTIONS
            or [row['id'] for row in rows] != plan['candidate_ids'] or requests != requests_for(rows)):
        raise ValueError('Frozen candidate/request bytes or deterministic pair order differ')
    actual = protocol_identity(tokenizer or load_tokenizer(local_files_only=True))
    if actual != plan['protocol'] or digest(actual) != plan['protocol_sha256']:
        raise ValueError('Frozen source, tokenizer, caps or protocol changed')
    if plan.get('source_revision') != source.REVISION or plan.get('source_train_sha256') != source.SOURCE_SHA or sha(source.SOURCE.read_bytes()) != source.SOURCE_SHA:
        raise ValueError('Canonical TRAIN cache changed')
    canonical_rows, _ = source.load_source(source.SOURCE, 'train'); canonical = {row['id']: row for row in canonical_rows}
    for row in rows:
        original = canonical.get(row['id'])
        if not original or any(row.get(key) != value for key, value in original.items()) or row.get('source_revision') != source.REVISION:
            raise ValueError('Canonical training prompt/reference differs')
        proof, _, _ = source.annotation_check(row['reference_solution'], row['gold_answer'])
        if (proof != row.get('annotation_verification') or proof is None or input_bytes(row) > MAX_MESSAGES_BYTES
                or sha(row['prompt'].encode()) != row.get('prompt_sha256')
                or sha(row['reference_solution'].encode()) != row.get('reference_solution_sha256')):
            raise ValueError('Exact reference/input bound changed')
    for item in plan['exclusion_artifacts']:
        path = paths_api._safe(ROOT.parent/item['run'])
        if path != source.PROBES.resolve() and not path.is_relative_to((ROOT/'runs').resolve()):
            raise ValueError('Exclusion artifact is outside declared training paths')
        if sha(path.read_bytes()) != item['sha256']: raise ValueError('Frozen exclusion artifact changed')
    # Include later prepared cohorts when deciding whether any paid call may
    # start; never silently share this supposedly unused teaching cohort.
    records, _ = load_exclusions(output)
    excluded, _ = source.ancestry_exclusions(canonical_rows, records)
    if any(row['id'] in excluded for row in rows): raise ValueError('Later project cohort overlaps this frozen selection')
    return plan, rows, requests


def review_template(plan, reservation_id):
    return {'reviewed': False, 'version': VERSION, 'plan_sha256': plan['plan_sha256'],
        'collector_sha256': sha(Path(__file__).read_bytes()), 'requests_sha256': plan['requests_sha256'],
        'reservation_id': reservation_id, 'reserved_usd': str(RESERVATION),
        'original_requests': 2*QUESTIONS, 'cost_bound_usd': str(COST_BOUND),
        'zero_retry_and_unknown_usage_hold_acknowledged': True,
        'private_channels_and_full_fit_intersection_acknowledged': True}


def validate_review(plan, reservation_id, review):
    expected = dict(review_template(plan, reservation_id), reviewed=True)
    if review != expected: raise ValueError('Exact current source/plan/request/funding collection review required')
    return digest(review)


def require_budget(plan, reservation_id, review, *, ledger_path=None, clock=now):
    review_sha = validate_review(plan, reservation_id, review)
    ledger = read(ledger_path or ROOT/'runs/supervisor/budget.json')
    if 'deepseek_budget_accounting' not in ledger: raise ValueError('Supported DeepSeek funding evidence is required')
    require_fresh_deepseek_budget(ledger, now=clock(), new_reservation=True)
    account = ledger['deepseek_budget_accounting']
    if (account.get('status') != 'conditional_wallet_inference' or account.get('funding_history_ambiguous') is not False
            or Decimal(str(ledger['limits']['deepseek'])) > Decimal('20')):
        raise ValueError('Original supported20USD DeepSeek ceiling required')
    jobs = [job for job in ledger.get('jobs', []) if job.get('run_id') == reservation_id and job.get('service') == 'deepseek']
    if len(jobs) != 1: raise ValueError('One existing exact DeepSeek reservation required')
    job = jobs[0]
    if (job.get('status') not in ('reserved', 'collecting') or Decimal(str(job.get('reserved_usd', 0))) != RESERVATION
            or job.get('native_reasoning_plan_sha256') != plan['plan_sha256']
            or job.get('native_reasoning_requests_sha256') != plan['requests_sha256']
            or job.get('native_reasoning_review_sha256') != review_sha):
        raise ValueError('Reservation does not bind this exact reviewed collection')
    return job


def attempt_paths(output, identifier):
    name = sha(identifier.encode())
    return tuple(private(Path(output)/'attempts'/(name+suffix)) for suffix in
        ('.intent.json', '.wire', '.wire.json', '.result.json', '.error.json'))


def _bounded_read(response, deadline):
    chunks = []; size = 0
    while size <= MAX_RESPONSE_BYTES:
        if time.monotonic() >= deadline: raise TimeoutError('HTTP wall deadline exceeded')
        chunk = response.read1(min(65536, MAX_RESPONSE_BYTES+1-size))
        if not chunk: break
        chunks.append(chunk); size += len(chunk)
    return b''.join(chunks)


def http(body, key):
    """Exactly one urllib transmission; no redirect or automatic retry."""
    deadline = time.monotonic()+HTTP_WALL_SECONDS
    request = urllib.request.Request(API_URL, data=encoded(body),
        headers={'Authorization': 'Bearer '+key, 'Content-Type': 'application/json'})
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs): return None
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=SOCKET_TIMEOUT) as response:
            return response.status, _bounded_read(response, deadline)
    except urllib.error.HTTPError as error:
        return error.code, _bounded_read(error, deadline)


def result_from_wire(plan, request, row, wire, marker, metadata):
    result = {'id': request['id'], 'question_id': row['id'], 'mode': request['mode'],
        'plan_sha256': plan['plan_sha256'], 'request_sha256': request['request_sha256'],
        'started_at_utc': marker['started_at_utc'], 'completed_at_utc': metadata['completed_at_utc'],
        'elapsed_seconds': metadata['elapsed_seconds'], 'http_status': metadata['http_status'],
        'wire_sha256': sha(wire), 'wire_bytes': len(wire), 'raw': None,
        'response': '', 'reasoning_content': '', 'finish_reason': 'error', 'failed': False}
    try:
        if len(wire) > MAX_RESPONSE_BYTES: raise ValueError('Response exceeds bound')
        raw = parse(wire)
        # Validate the entire parsed tree before retaining any of it. Escaped
        # lone surrogates, numeric overflow and excessive recursion can hide
        # outside the answer channels and otherwise poison durable receipts.
        encoded(raw)
        result['raw'] = raw
        if not isinstance(raw, dict) or not 200 <= metadata['http_status'] < 300: raise ValueError('HTTP/provider response failed')
        if not isinstance(raw.get('choices'), list) or len(raw['choices']) != 1: raise ValueError('Unexpected choices')
        choice = raw['choices'][0]
        if not isinstance(choice, dict) or not isinstance(choice.get('message'), dict):
            raise ValueError('Invalid choice/message shape')
        message = choice['message']
        if choice.get('finish_reason') not in ('stop','length','content_filter','tool_calls','insufficient_system_resource','aborted'):
            raise ValueError('Invalid completion finish reason')
        if not isinstance(message.get('content'), (str, type(None))) or not isinstance(message.get('reasoning_content'), (str, type(None))):
            raise ValueError('Invalid response channels')
        result.update(response=message.get('content') or '', reasoning_content=message.get('reasoning_content') or '',
            finish_reason=choice.get('finish_reason'), teacher_revision=raw.get('model'), system_fingerprint=raw.get('system_fingerprint'))
    except (ValueError, KeyError, IndexError, TypeError, UnicodeError, RecursionError):
        result.update(failed=True, raw=None, error_type='InvalidOrFailedProviderResponse')
    usage = result['raw'].get('usage') if isinstance(result['raw'], dict) else None
    result['unknown_provider_usage'] = not usage_valid(usage)
    return result


def usage_valid(usage):
    if not isinstance(usage, dict) or not all(type(usage.get(key)) is int and usage[key] >= 0 for key in ('prompt_tokens', 'completion_tokens')): return False
    details = usage.get('completion_tokens_details')
    return not isinstance(details, dict) or 'reasoning_tokens' not in details or (type(details['reasoning_tokens']) is int and 0 <= details['reasoning_tokens'] <= usage['completion_tokens'])


def recover_attempt(plan, request, row, output):
    intent_path, wire_path, metadata_path, result_path, error_path = attempt_paths(output, request['id'])
    if not intent_path.exists():
        if any(path.exists() for path in (wire_path, metadata_path, result_path, error_path)): raise ValueError('Receipt without original intent')
        return None
    marker = read(intent_path)
    if (marker.get('id') != request['id'] or marker.get('request_sha256') != request['request_sha256']
            or marker.get('plan_sha256') != plan['plan_sha256']): raise ValueError('Original intent identity changed')
    if error_path.exists():
        result = read(error_path)
        fields = {'id','question_id','mode','plan_sha256','request_sha256','started_at_utc',
            'completed_at_utc','failed','unknown_provider_usage','error_type','response',
            'reasoning_content','finish_reason','raw'}
        if (not isinstance(result, dict) or set(result) != fields or result.get('id') != request['id']
                or result.get('question_id') != row['id'] or result.get('mode') != request['mode']
                or result.get('plan_sha256') != plan['plan_sha256']
                or result.get('request_sha256') != request['request_sha256']
                or result.get('started_at_utc') != marker['started_at_utc']
                or result.get('unknown_provider_usage') is not True or result.get('failed') is not True
                or result.get('raw') is not None or result.get('response') != ''
                or result.get('reasoning_content') != '' or result.get('finish_reason') != 'error'
                or not isinstance(result.get('completed_at_utc'), str)
                or not isinstance(result.get('error_type'), str)
                or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}', result['error_type'])):
            raise ValueError('Failed original receipt changed')
        completed = datetime.fromisoformat(result['completed_at_utc'])
        if completed.tzinfo is None: raise ValueError('Failed original receipt lacks a zoned timestamp')
    elif wire_path.exists() and metadata_path.exists():
        metadata = read(metadata_path); wire = wire_path.read_bytes()
        if (metadata.get('plan_sha256') != plan['plan_sha256'] or metadata.get('request_sha256') != request['request_sha256']
                or metadata.get('wire_sha256') != sha(wire) or metadata.get('wire_bytes') != len(wire)
                or type(metadata.get('http_status')) is not int or type(metadata.get('elapsed_seconds')) not in (int, float)
                or not math.isfinite(metadata['elapsed_seconds']) or metadata['elapsed_seconds'] < 0):
            raise ValueError('Original wire metadata/hash changed')
        result = result_from_wire(plan, request, row, wire, marker, metadata)
    else:
        raise AmbiguousAttemptError('Original transmission has no complete durable outcome; never resend')
    if result_path.exists():
        if read(result_path) != result: raise ValueError('Derived result differs from original wire/error receipt')
    else: write(result_path, result)
    return result


def call_request(plan, request, row, output, key, *, reservation_id, review_sha256, transport=http):
    paths = attempt_paths(output, request['id']); intent_path, wire_path, metadata_path, result_path, error_path = paths
    if any(path.exists() for path in paths): raise AmbiguousAttemptError('Original request already claimed; inspect/recover, never resend')
    if request['payload'] != payload(row, request['mode']) or request['request_sha256'] != digest(request['payload']): raise ValueError('Frozen request differs')
    marker = {'id': request['id'], 'plan_sha256': plan['plan_sha256'], 'request_sha256': request['request_sha256'],
        'reservation_id': reservation_id, 'review_sha256': review_sha256, 'started_at_utc': now()}
    # An exclusive intent is the only claim permitted to transmit this request.
    intent_path.parent.mkdir(parents=True, exist_ok=True)
    with intent_path.open('xb') as handle: handle.write(encoded(marker)+b'\n'); handle.flush(); os.fsync(handle.fileno())
    started = time.monotonic()
    try:
        status, wire = transport(request['payload'], key)
        if type(status) is not int or not isinstance(wire, bytes): raise ValueError('Invalid transport outcome')
        write_bytes(wire_path, wire)
        write(metadata_path, {'plan_sha256': plan['plan_sha256'], 'request_sha256': request['request_sha256'],
            'wire_sha256': sha(wire), 'wire_bytes': len(wire), 'http_status': status,
            'elapsed_seconds': time.monotonic()-started, 'completed_at_utc': now()})
    except Exception as error:
        # No exception body/account data is persisted or printed. A transport or
        # local receipt interruption retains an unknown-cost original attempt.
        write(error_path, {'id': request['id'], 'question_id': row['id'], 'mode': request['mode'],
            'plan_sha256': plan['plan_sha256'], 'request_sha256': request['request_sha256'],
            'started_at_utc': marker['started_at_utc'], 'completed_at_utc': now(),
            'failed': True, 'unknown_provider_usage': True, 'error_type': type(error).__name__,
            'response': '', 'reasoning_content': '', 'finish_reason': 'error', 'raw': None})
        raise
    return recover_attempt(plan, request, row, output)


def verify_result(result, row, tokenizer):
    value = dict(result); mode = value['mode']; content = value.get('response'); reasoning = value.get('reasoning_content')
    usage = value.get('raw', {}).get('usage') if isinstance(value.get('raw'), dict) else None
    known = usage_valid(usage) and value.get('unknown_provider_usage') is False
    bounded = known and usage['prompt_tokens'] <= MAX_INPUT_TOKENS and usage['completion_tokens'] <= CAPS[mode]
    match = (isinstance(content, str) and content.count('####') == 1 and
        numeric_answer(content.rsplit('####', 1)[1].strip()) is not None and
        numeric_answer(content.rsplit('####', 1)[1].strip()) == numeric_answer(str(row['gold_answer'])))
    reasons = []
    if value.get('failed') or value.get('finish_reason') != 'stop': reasons.append('failed_or_nonstop_completion')
    if not isinstance(content, str) or not content.strip(): reasons.append('missing_visible_answer')
    if not match: reasons.append('unparsed_or_reference_mismatch')
    if not isinstance(value.get('teacher_revision'), str) or not value['teacher_revision'].casefold().startswith(contract.TEACHER_MODEL): reasons.append('unexpected_teacher_identity')
    if not known: reasons.append('unknown_provider_usage')
    elif not bounded: reasons.append('provider_token_bound_exceeded')
    if mode == 'thinking' and (not isinstance(reasoning, str) or not reasoning.strip()): reasons.append('missing_reasoning_channel')
    if mode == 'concise' and reasoning: reasons.append('unexpected_concise_reasoning_channel')
    try:
        encoding = contract.encode_target(row, mode, reasoning, content, tokenizer)
        value['encoding'] = encoding
        if not encoding['context_fit']: reasons.append('student_context_over4096')
    except (ValueError, TypeError, UnicodeError): reasons.append('unsafe_or_invalid_channel_serialization')
    value.update(eligible=not reasons, rejection_reasons=reasons, numeric_final_match=bool(match),
        provider_usage_known=known, provider_token_bounds_met=bool(bounded), trace_rewritten=False,
        intermediate_reasoning_verified=False, trace_truncated=value.get('finish_reason') == 'length')
    return value


def summary(plan, rows, results, *, stage, halt=None):
    by_id = {result['id']: result for result in results}
    if len(by_id) != len(results): raise ValueError('Duplicate original outcome')
    pairs = []
    for row in rows:
        values = {mode: by_id.get(row['id']+'::'+mode) for mode in MODES}
        if all(values[mode] and values[mode]['eligible'] for mode in MODES):
            if len({values[mode]['teacher_revision'].casefold() for mode in MODES}) != 1: continue
            if len({values[mode]['encoding']['prefix_ids_sha256'] for mode in MODES}) != 1: raise ValueError('Pair student prefix differs')
            pairs.append({'id': row['id'], **{mode: dict(values[mode]['encoding'], finish_reason='stop',
                truncated=False, verified_final_answer=True, teacher_revision=values[mode]['teacher_revision'],
                original_receipt_sha256=digest(values[mode])) for mode in MODES}})
    usage = {'prompt_tokens': 0, 'completion_tokens': 0}
    for result in results:
        if result['provider_usage_known']:
            raw = result['raw']['usage']
            for key in usage: usage[key] += raw[key]
    cost = (Decimal(usage['prompt_tokens'])*Decimal('1.32')+Decimal(usage['completion_tokens'])*Decimal('3.96'))/Decimal(1000000)
    totals = {mode: {'retained_original_outcomes': sum(r['mode'] == mode for r in results),
        'individually_eligible': sum(r['mode'] == mode and r['eligible'] for r in results),
        'paired_eligible_supervised_tokens': sum(p[mode]['supervised_tokens'] for p in pairs),
        'rejection_counts': dict(Counter(reason for r in results if r['mode'] == mode for reason in r['rejection_reasons']))} for mode in MODES}
    return {'schema_version': 1, 'version': VERSION, 'run_id': plan['run_id'], 'stage': stage, 'halt_reason': halt,
        'plan_sha256': plan['plan_sha256'], 'requested_questions': QUESTIONS, 'requested_original_calls': 2*QUESTIONS,
        'retained_original_outcomes': len(results), 'eligible_question_pairs': len(pairs), 'conditions': totals,
        'unknown_usage_attempts': sum(not r['provider_usage_known'] for r in results),
        'recorded_peak_token_estimate_usd': str(cost), 'original_call_cost_bound_usd': str(COST_BOUND),
        'provider_invoice_or_final_usage': False, 'new_student_training': False, 'official_test_accessed': False,
        'raw_channels_private': True}, pairs


def _history(output, plan, rows, requests, tokenizer, *, append=False):
    row_by_id = {row['id']: row for row in rows}; history_path = output/'teacher_results.jsonl'
    history = read_rows(history_path) if history_path.exists() else []
    saved = {result['id']: result for result in history}
    if len(saved) != len(history) or not set(saved) <= {request['id'] for request in requests}: raise ValueError('Append-only result IDs differ')
    results = []
    for request in requests:
        result = recover_attempt(plan, request, row_by_id[request['question_id']], output)
        if result is None:
            if request['id'] in saved: raise ValueError('Appended outcome lost its original receipt')
            continue
        verified = verify_result(result, row_by_id[request['question_id']], tokenizer)
        if request['id'] in saved:
            if saved[request['id']] != verified: raise ValueError('Append-only verified result differs')
        elif append:
            with private(history_path).open('ab') as handle: handle.write(encoded(verified)+b'\n'); handle.flush(); os.fsync(handle.fileno())
        results.append(verified)
    return results


def _receipt_inventory(output, plan, requests):
    allowed = {path.name for request in requests for path in attempt_paths(output, request['id'])}
    folder = private(output/'attempts'); files = []
    if not folder.exists(): return {'sha256': digest([]), 'files': [], 'original_intents': 0}
    entries = list(folder.iterdir())
    if len(entries) > 5*len(requests): raise ValueError('Original receipt inventory exceeds frozen attempts')
    for path in entries:
        checked = private(path)
        if not checked.is_file() or checked.name not in allowed: raise ValueError('Unknown/private receipt inventory artifact')
        limit = 3*MAX_RESPONSE_BYTES+65536 if checked.name.endswith('.result.json') else MAX_RESPONSE_BYTES+16384
        if checked.stat().st_size > limit: raise ValueError('Original receipt exceeds byte bound')
        files.append({'path': 'attempts/'+checked.name, 'sha256': sha(checked.read_bytes()), 'bytes': checked.stat().st_size})
    markers = [request for request in requests if attempt_paths(output, request['id'])[0].exists()]
    if entries:
        approved = read(output/'reviewed_for_collection.json'); session = read(output/'collection_session.json')
        review_sha = validate_review(plan, session.get('reservation_id'), approved)
        if (session.get('plan_sha256') != plan['plan_sha256'] or session.get('review_sha256') != review_sha):
            raise ValueError('Receipt owner/session review changed')
        for request in markers:
            marker = read(attempt_paths(output, request['id'])[0])
            if (set(marker) != {'id','plan_sha256','request_sha256','reservation_id','review_sha256','started_at_utc'}
                    or marker.get('id') != request['id'] or marker.get('plan_sha256') != plan['plan_sha256']
                    or marker.get('request_sha256') != request['request_sha256']
                    or marker.get('review_sha256') != review_sha or marker.get('reservation_id') != session['reservation_id']):
                raise ValueError('Original intent does not bind the reviewed session')
            stamp = datetime.fromisoformat(marker['started_at_utc'])
            if stamp.tzinfo is None: raise ValueError('Original intent timestamp requires timezone')
    files.sort(key=lambda item: item['path'])
    return {'sha256': digest(files), 'files': files, 'original_intents': len(markers)}


def receipt_inventory(output=RUN, *, tokenizer=None):
    output = private(output); plan, _, requests = validate_run(output, tokenizer=tokenizer)
    return _receipt_inventory(output, plan, requests)


def finalized_pairs(output=RUN, tokenizer=None):
    """Return only jointly eligible, whole native targets from all originals.

    This is a TRAIN intersection, never evaluation filtering. Source, exact
    approved session, every original wire/receipt and append-only history are
    revalidated; an incomplete or active collection is not finalized.
    """
    output = private(output); tokenizer = tokenizer or load_tokenizer(local_files_only=True)
    plan, rows, requests = validate_run(output, tokenizer=tokenizer)
    if (output/'collector.lock').exists(): raise ValueError('Active collector cannot finalize targets')
    _receipt_inventory(output, plan, requests)
    results = _history(output, plan, rows, requests, tokenizer)
    if len(results) != 2*QUESTIONS: raise ValueError('All original paired outcomes must be retained before finalization')
    _, pairs = summary(plan, rows, results, stage='completed')
    if (output/'eligible_pairs.jsonl').exists() and read_rows(output/'eligible_pairs.jsonl') != pairs:
        raise ValueError('Saved common eligible pair projection changed')
    return pairs


def inspect_run(output=RUN, *, tokenizer=None):
    output = private(output); tokenizer = tokenizer or load_tokenizer(local_files_only=True)
    plan, rows, requests = validate_run(output, tokenizer=tokenizer)
    if (output/'collector.lock').exists(): raise ValueError('Collector owns private receipts; inspect its metadata without rewriting')
    _receipt_inventory(output, plan, requests)
    results = _history(output, plan, rows, requests, tokenizer)
    return summary(plan, rows, results, stage='completed' if len(results) == 2*QUESTIONS else 'prepared_or_partial')[0]


def collect(output=RUN, *, reservation_id, review_path, authorized=False, workers=4,
            tokenizer=None, transport=http, ledger_path=None, key=None, clock=now):
    if authorized is not True: raise ValueError('Explicit reviewed paid-collection execution flag required')
    if type(workers) is not int or not 1 <= workers <= 4: raise ValueError('Use at most four pair workers')
    output = private(output); tokenizer = tokenizer or load_tokenizer(local_files_only=True)
    plan, rows, requests = validate_run(output, tokenizer=tokenizer)
    review = read(review_path); review_sha = validate_review(plan, reservation_id, review)
    require_budget(plan, reservation_id, review, ledger_path=ledger_path, clock=clock)
    if other_collector_locks(output): raise ValueError('Another collector owner must reconcile first')
    lock = private(output/'collector.lock'); token = encoded({'pid': os.getpid(), 'plan_sha256': plan['plan_sha256'], 'started_at_utc': clock()})
    with lock.open('xb') as handle: handle.write(token); handle.flush(); os.fsync(handle.fileno())
    stop = threading.Event(); halt = None; guard_lock = threading.Lock(); results = []
    try:
        if other_collector_locks(output): raise ValueError('Concurrent collector detected; no transmissions')
        write(output/'reviewed_for_collection.json', review)
        session_path = output/'collection_session.json'
        if not session_path.exists(): write(session_path, {'plan_sha256': plan['plan_sha256'],
            'review_sha256': review_sha, 'reservation_id': reservation_id, 'started_at_utc': clock()})
        session = read(session_path)
        if session.get('plan_sha256') != plan['plan_sha256'] or session.get('review_sha256') != review_sha or session.get('reservation_id') != reservation_id:
            raise ValueError('Original collection session changed')
        # Stabilize the common physical parent before worker paths resolve it.
        # Concurrent first-mkdir and Windows/OneDrive resolution can otherwise
        # transiently disagree about an absent ancestor's canonical spelling.
        private(output/'attempts').mkdir(exist_ok=True)
        _receipt_inventory(output, plan, requests)
        start = datetime.fromisoformat(session['started_at_utc']); launch_deadline = start.timestamp()+LAUNCH_WINDOW_SECONDS
        results = _history(output, plan, rows, requests, tokenizer, append=True)
        if any(r['failed'] or not r['provider_token_bounds_met'] for r in results):
            raise ValueError('Prior failed/unknown/over-bound original requires reconciliation; never continue blindly')
        if len(results) == 2*QUESTIONS: return summary(plan, rows, results, stage='completed')[0]
        key = key if key is not None else credential('DEEPSEEK_API_KEY')
        if not key: raise ValueError('DeepSeek credential unavailable')
        seen = {r['id'] for r in results}; by_row = {row['id']: row for row in rows}; pending = {}
        for request in requests:
            if request['id'] not in seen: pending.setdefault(request['question_id'], []).append(request)
        def run_pair(identifier, entries):
            receipts = []; reason = None
            for request in entries:
                with guard_lock:
                    if stop.is_set(): break
                    if datetime.fromisoformat(clock()).timestamp() >= launch_deadline:
                        stop.set(); return receipts, 'launch_window_exhausted_no_new_calls'
                    try: require_budget(plan, reservation_id, review, ledger_path=ledger_path, clock=clock)
                    except Exception:
                        stop.set(); return receipts, 'funding_guard_failed_no_new_calls'
                try:
                    result = call_request(plan, request, by_row[identifier], output, key,
                        reservation_id=reservation_id, review_sha256=review_sha, transport=transport)
                    result = verify_result(result, by_row[identifier], tokenizer); receipts.append(result)
                    if result['failed'] or not result['provider_token_bounds_met']:
                        reason = 'failed_or_unknown_or_out_of_bound_original_no_retry'; stop.set(); break
                except Exception:
                    stop.set(); return receipts, 'original_attempt_requires_reconciliation_no_retry'
            return receipts, reason
        queue = iter(pending.items())
        with ThreadPoolExecutor(max_workers=workers) as executor:
            active = {}
            for _ in range(min(workers, len(pending))):
                identifier, entries = next(queue); active[executor.submit(run_pair, identifier, entries)] = identifier
            while active:
                done, _ = wait(active, return_when=FIRST_COMPLETED)
                for future in done:
                    active.pop(future); received, reason = future.result()
                    for result in received:
                        with private(output/'teacher_results.jsonl').open('ab') as handle:
                            handle.write(encoded(result)+b'\n'); handle.flush(); os.fsync(handle.fileno())
                        results.append(result)
                    if reason: halt = reason
                if not stop.is_set():
                    while len(active) < workers:
                        entry = next(queue, None)
                        if entry is None: break
                        identifier, entries = entry; active[executor.submit(run_pair, identifier, entries)] = identifier
        # Recover every original durable receipt, including failures after a
        # local write interruption; no recovered outcome triggers HTTP.
        results = _history(output, plan, rows, requests, tokenizer, append=True)
        status, pairs = summary(plan, rows, results, stage='completed' if len(results) == 2*QUESTIONS else 'halted', halt=halt)
        write_bytes(output/'eligible_pairs.jsonl', rows_bytes(pairs), immutable=False)
        write(output/'teacher_summary.json', status, immutable=False)
        return status
    finally:
        if lock.exists() and lock.read_bytes() == token: lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', nargs='?', choices=('prepare', 'inspect', 'collect'), default='inspect')
    parser.add_argument('--output', type=Path, default=RUN); parser.add_argument('--reservation-id')
    parser.add_argument('--review-path', type=Path); parser.add_argument('--authorized', action='store_true')
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    if args.action == 'prepare': result = prepare(args.output)
    elif args.action == 'inspect': result = inspect_run(args.output)
    else:
        if not args.reservation_id or args.review_path is None: parser.error('Collection needs exact existing reservation and review')
        result = collect(args.output, reservation_id=args.reservation_id, review_path=args.review_path,
            authorized=args.authorized, workers=args.workers)
    print(json.dumps({key: result[key] for key in ('run_id', 'stage', 'candidate_count', 'retained_original_outcomes', 'eligible_question_pairs') if key in result}))


if __name__ == '__main__': main()
