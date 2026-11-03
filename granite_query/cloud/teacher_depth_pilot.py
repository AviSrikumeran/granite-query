"""Unpaid preparation and separately funded collection of32 paired TRAIN items.

This is a feasibility pilot, not a student-training or improvement result.
Collection never reserves credit, refreshes providers, retries a request, launches
a GPU or expands beyond32 questions/64 original requests. Private wire responses
are fsynced before parsing. Missing receipts never cause an automatic resend.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import random
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from cloud import human_math_cohort as source
from cloud.matched_teacher import PREFIX, API_URL, _canonical
from cloud.math_teacher import assert_reserved, other_collector_locks
from cloud.deepseek_reconcile import require_fresh_deepseek_budget
from cloud.run_api_pilot import credential
from cloud.student_valuation import load_tokenizer, MODEL as STUDENT, REVISION
from ranking.verification import numeric_answer

RUN = ROOT / 'runs/teacher_depth32_v1'
PUBLIC = ROOT.parents[1] / 'progress/TEACHER_DEPTH_PILOT.json'
DESIGN = ROOT.parents[1] / 'progress/TEACHER_DEPTH_DESIGN.json'
SEED = 20261110
QUESTIONS = 32
MODEL = 'deepseek-v4-pro'
MODES = ('concise', 'thinking')
CAPS = {'concise': 1024, 'thinking': 4096}
MAX_INPUT_TOKENS = 2000
MAX_MESSAGES_BYTES = 1006
MAX_RESPONSE_BYTES = 1024 * 1024
CONTEXT = 4096
MAX_SECONDS = 1200
TEMPLATE_SHA = 'f0ba43f79b3cabca5e5a7584c77aec92f49feae45cdf7779c87d9fc54cd90258'
ENCODER_VERSION = 'native-thinking-explicit-boundary-v1'
PROTOCOL_VERSION = 'paired-teacher-depth32-feasibility-v1'
COST_BOUND = Decimal(QUESTIONS) * (2 * MAX_INPUT_TOKENS * Decimal('1.32')
             + sum(CAPS.values()) * Decimal('3.96')) / Decimal(1000000)


def now(): return datetime.now(timezone.utc).isoformat()
def sha(raw): return hashlib.sha256(raw).hexdigest()
def digest(value): return sha(_canonical(value).encode('utf-8'))
def rows_bytes(rows): return ''.join(_canonical(row) + '\n' for row in rows).encode('utf-8')
def read_rows(path): return [json.loads(line) for line in Path(path).read_text(encoding='utf-8-sig').split('\n') if line.strip()]


def provider_usage(result):
    raw = result.get('raw')
    usage = raw.get('usage') if isinstance(raw, dict) else None
    return usage if isinstance(usage, dict) else {}


def bounded_usage(result):
    usage = provider_usage(result)
    if not all(isinstance(usage.get(key), int) and not isinstance(usage.get(key), bool) and usage[key] >= 0
               for key in ('prompt_tokens','completion_tokens')):
        return False
    details = usage.get('completion_tokens_details')
    if isinstance(details, dict) and 'reasoning_tokens' in details:
        reasoning = details['reasoning_tokens']
        if not isinstance(reasoning, int) or isinstance(reasoning, bool) or not 0 <= reasoning <= usage['completion_tokens']:
            return False
    return usage['prompt_tokens'] <= MAX_INPUT_TOKENS and usage['completion_tokens'] <= CAPS[result['mode']]


def write_bytes(path, raw):
    """Fsync local durable state; retries never include a provider request."""
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('xb') as handle:
        handle.write(raw); handle.flush(); os.fsync(handle.fileno())
    for attempt in range(4):
        try:
            os.replace(temporary, path)
            break
        except PermissionError:
            if attempt == 3: raise
            time.sleep(.05 * (2**attempt))


def write_json(path, value):
    write_bytes(path, (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8'))


def payload(row, mode):
    if mode not in MODES or row.get('source_split') != 'train':
        raise ValueError('Only the frozen two modes and training questions are permitted')
    value = {'model': MODEL, 'max_tokens': CAPS[mode], 'stream': False,
             'thinking': {'type': 'disabled' if mode == 'concise' else 'enabled'},
             'messages': [{'role': 'user', 'content': PREFIX + row['prompt']}]}
    if mode == 'thinking': value['reasoning_effort'] = 'high'
    return value


def input_bytes(row):
    return len(_canonical(payload(row, 'concise')['messages']).encode('utf-8'))


def tokenizer_identity(tokenizer):
    template = tokenizer.chat_template
    if not isinstance(template, str) or sha(template.encode('utf-8')) != TEMPLATE_SHA:
        raise ValueError('Pinned Granite native template differs')
    if tokenizer.eos_token != '<|im_end|>' or tokenizer.eos_token_id != 100257:
        raise ValueError('Pinned Granite EOS differs')
    return {'model': STUDENT, 'revision': REVISION, 'chat_template_sha256': TEMPLATE_SHA,
            'backend_sha256': sha(tokenizer.backend_tokenizer.to_str().encode('utf-8')),
            'transformers_version': importlib.metadata.version('transformers'),
            'eos_token': tokenizer.eos_token, 'eos_token_id': tokenizer.eos_token_id}


def protocol_identity(tokenizer):
    dependencies = [Path(__file__), ROOT/'human_math_cohort.py', ROOT/'matched_teacher.py',
        ROOT/'math_teacher.py', ROOT/'deepseek_reconcile.py', ROOT/'student_valuation.py',
        ROOT/'run_api_pilot.py', ROOT.parent/'ranking/prepare_gsm8k.py',
        ROOT.parent/'ranking/verification.py']
    return {'version': PROTOCOL_VERSION, 'encoder_version': ENCODER_VERSION,
        'model': MODEL, 'modes': {'concise': {'thinking': 'disabled', 'max_tokens': 1024},
            'thinking': {'thinking': 'enabled', 'reasoning_effort': 'high', 'max_tokens': 4096}},
        'user_prefix_sha256': sha(PREFIX.encode('utf-8')), 'tokenizer': tokenizer_identity(tokenizer),
        'source_code_hashes': {path.relative_to(ROOT.parent).as_posix(): sha(path.read_bytes()) for path in dependencies},
        'context_limit': CONTEXT, 'max_messages_utf8_bytes': MAX_MESSAGES_BYTES,
        'max_received_response_bytes': MAX_RESPONSE_BYTES, 'max_collector_seconds_before_drain': MAX_SECONDS,
        'conservative_input_token_bound': MAX_INPUT_TOKENS, 'automatic_retries': 0,
        'max_questions': QUESTIONS, 'max_attempts': 2*QUESTIONS, 'max_concurrent': 4,
        'loss_contract': 'Prefix labels=-100; complete suffix IDs and exactly one EOS supervised; no padding in saved encoding. Future batches must mask padding explicitly.',
        'source_reference_policy': 'Human arithmetic annotations/final match checked exactly; semantic sufficiency and complete ancestry are not proven.'}


def encode_target(row, mode, reasoning, content, tokenizer):
    """Preserve channels, concatenate explicit token boundaries, never slice BPE.

    The common generation prefix includes the opening think tag. Even an empty
    span has an explicit closing tag in the supervised suffix. Separate encoding
    is intentional because full-string BPE can merge across the text boundary.
    """
    if mode not in MODES or not isinstance(reasoning, str) or not isinstance(content, str):
        raise ValueError('Invalid mode or response channels')
    if mode == 'concise' and reasoning:
        raise ValueError('Unexpected reasoning channel in nonthinking response')
    controls = ('<|im_start|>', '<|im_end|>', '<think>', '</think>')
    if any(control in text for text in (reasoning, content) for control in controls):
        raise ValueError('Original channel contains a reserved serialization delimiter')
    prefix = tokenizer.apply_chat_template([{'role': 'user', 'content': PREFIX+row['prompt']}],
        tokenize=False, add_generation_prompt=True, enable_thinking=True)
    if not prefix.endswith('<|im_start|>assistant\n<think>\n'):
        raise ValueError('Unexpected native thinking generation prefix')
    suffix = (reasoning+'\n' if mode == 'thinking' else '') + '</think>\n' + content
    prefix_ids = tokenizer.encode(prefix, add_special_tokens=False)
    suffix_ids = tokenizer.encode(suffix, add_special_tokens=False) + [tokenizer.eos_token_id]
    ids = prefix_ids + suffix_ids
    decoded = tokenizer.decode(ids, skip_special_tokens=False, clean_up_tokenization_spaces=False)
    if decoded != prefix + suffix + tokenizer.eos_token:
        raise ValueError('Explicit-boundary encoding does not decode to preserved channel text')
    if tokenizer.eos_token_id in suffix_ids[:-1]:
        raise ValueError('Duplicate EOS in supervised suffix')
    return {'encoder_version': ENCODER_VERSION, 'input_ids': ids,
        'attention_mask': [1]*len(ids), 'labels': [-100]*len(prefix_ids)+suffix_ids,
        'prefix_tokens': len(prefix_ids), 'supervised_tokens': len(suffix_ids),
        'context_tokens': len(ids), 'reasoning_tokens': len(tokenizer.encode(reasoning, add_special_tokens=False)),
        'visible_content_tokens': len(tokenizer.encode(content, add_special_tokens=False)),
        'context_fit': len(ids) <= CONTEXT, 'prefix_ids_sha256': digest(prefix_ids),
        'target_ids_sha256': digest(suffix_ids), 'target_text_sha256': sha(suffix.encode('utf-8')),
        'original_reasoning_sha256': sha(reasoning.encode('utf-8')),
        'original_content_sha256': sha(content.encode('utf-8')), 'trace_truncated': False}


def select_candidates(canonical_rows, records, count=QUESTIONS):
    if not 1 <= count <= QUESTIONS: raise ValueError('At most32 questions')
    excluded, ancestry = source.ancestry_exclusions(canonical_rows, records)
    ordered = sorted(canonical_rows, key=lambda row: row['id'])
    random.Random(SEED).shuffle(ordered)
    chosen, signatures, counts = [], [], Counter()
    for row in ordered:
        if row.get('source_split') != 'train' or not row['id'].startswith('gsm8k:train:'):
            raise ValueError('Only canonical GSM training rows are permitted')
        if row['id'] in excluded:
            counts['prior_question_or_detectable_ancestry'] += 1; continue
        if input_bytes(row) > MAX_MESSAGES_BYTES:
            counts['input_byte_bound'] += 1; continue
        if numeric_answer(str(row['gold_answer'])) is None:
            counts['nondecimal_scalar_reference'] += 1; continue
        proof, reason, _ = source.annotation_check(row['reference_solution'], row['gold_answer'])
        if proof is None:
            counts[reason] += 1; continue
        signature = source.masked_shingles(row['prompt'])
        if any(len(signature & old)/max(1, len(signature | old)) >= .85 for old in signatures):
            counts['within_pilot_near_duplicate'] += 1; continue
        signatures.append(signature)
        chosen.append(dict(row, source_revision=source.REVISION,
            reference_type='human_dataset_answer_with_exact_annotation_checks',
            annotation_verification=proof, reference_solution_sha256=sha(row['reference_solution'].encode('utf-8')),
            prompt_sha256=sha(row['prompt'].encode('utf-8')), reference_semantics_verified=False))
        if len(chosen) == count: break
    if len(chosen) != count: raise RuntimeError('Insufficient disjoint bounded human training prompts')
    return chosen, {'ancestry': ancestry, 'selection_decision_counts': dict(counts)}


def requests_for(rows):
    rng = random.Random(SEED ^ 0x5A17)
    requests = []
    for row in rows:
        order = list(MODES); rng.shuffle(order)
        for position, mode in enumerate(order):
            value = payload(row, mode)
            requests.append({'id': row['id']+'::'+mode, 'question_id': row['id'], 'mode': mode,
                'within_pair_position': position, 'payload': value, 'request_sha256': digest(value)})
    return requests


def prepare(output=RUN):
    output = Path(output).resolve()
    if not output.is_relative_to((ROOT/'runs').resolve()): raise ValueError('Use ignored cloud/runs only')
    if (output/'plan.json').exists():
        plan, _, _ = validate_run(output)
        return plan
    if output.exists() and any(output.iterdir()): raise RuntimeError('Partial preparation exists; inspect rather than overwrite')
    raw = source.SOURCE.read_bytes()
    if sha(raw) != source.SOURCE_SHA: raise ValueError('Pinned canonical TRAIN cache changed')
    canonical_rows, _ = source.load_source(source.SOURCE, 'train')
    if len(canonical_rows) != 7473: raise ValueError('Unexpected canonical training size')
    records, artifacts = source.load_exclusions(output)
    rows, review = select_candidates(canonical_rows, records)
    # Pin every scanned exclusion snapshot before any artifacts become visible.
    for item in artifacts:
        if sha((ROOT.parent/item['run']).read_bytes()) != item['sha256']:
            raise RuntimeError('Training exclusion artifact changed during preparation')
    tokenizer = load_tokenizer(local_files_only=True)
    protocol = protocol_identity(tokenizer)
    for row in rows:
        # Unpaid format/labels smoke check; this is not a generated answer.
        for mode in MODES:
            test = encode_target(row, mode, 'Arithmetic format fixture.' if mode == 'thinking' else '', '#### 0', tokenizer)
            if not test['context_fit']: raise ValueError('Prompt leaves no bounded context headroom')
    requests = requests_for(rows)
    plan = {'schema_version': 1, 'run_id': output.name, 'budget_job_id': output.name+'-teacher',
        'stage': 'prepared_unpaid', 'seed': SEED, 'candidate_count': QUESTIONS, 'max_attempts': 2*QUESTIONS,
        'source_split': 'train', 'source_revision': source.REVISION, 'source_train_sha256': source.SOURCE_SHA,
        'candidates_sha256': sha(rows_bytes(rows)), 'requests_sha256': sha(rows_bytes(requests)),
        'protocol': protocol, 'protocol_sha256': digest(protocol), 'design_sha256': sha(DESIGN.read_bytes()),
        'exclusion_artifacts': artifacts, 'exclusion_review': review,
        'max_actual_messages_utf8_bytes': max(input_bytes(row) for row in rows),
        'conservative_input_token_bound': MAX_INPUT_TOKENS, 'conservative_max_cost_usd': float(COST_BOUND),
        'reserved_usd_required': 1, 'max_concurrent': 4, 'automatic_retries': 0,
        'official_test_accessed': False, 'raw_reasoning_private': True, 'trace_truncation': False,
        'prior_exposure_limit': 'Project-disjoint teaching/development questions, not globally unseen text: the historical BM25 corpus included GSM training text. Synthetic ancestry checks are incomplete.',
        'pilot_scope': '32 questions/64 original attempts only. No larger collection, student training, provider refresh or reservation is performed by this module.'}
    output.mkdir(parents=True, exist_ok=True)
    write_bytes(output/'candidates.jsonl', rows_bytes(rows))
    write_bytes(output/'requests.jsonl', rows_bytes(requests))
    write_json(output/'plan.json', plan)
    summarize(output, plan, rows, [], 'prepared_unpaid')
    return plan


def validate_run(output, tokenizer=None):
    output = Path(output).resolve()
    if not output.is_relative_to((ROOT/'runs').resolve()): raise ValueError('Use ignored cloud/runs only')
    plan = json.loads((output/'plan.json').read_text(encoding='utf-8'))
    rows, requests = read_rows(output/'candidates.jsonl'), read_rows(output/'requests.jsonl')
    if (plan.get('candidate_count') != QUESTIONS or plan.get('max_attempts') != 2*QUESTIONS
            or len(rows) != QUESTIONS or len({row['id'] for row in rows}) != QUESTIONS
            or plan.get('official_test_accessed') is not False or plan.get('source_split') != 'train'
            or plan.get('run_id') != output.name or plan.get('budget_job_id') != output.name+'-teacher'
            or plan.get('reserved_usd_required') != 1 or Decimal(str(plan.get('conservative_max_cost_usd'))) != COST_BOUND):
        raise ValueError('Frozen pilot count, identity, isolation or cost contract differs')
    if (sha((output/'candidates.jsonl').read_bytes()) != plan['candidates_sha256']
            or sha((output/'requests.jsonl').read_bytes()) != plan['requests_sha256']
            or requests != requests_for(rows)):
        raise ValueError('Frozen candidates, pair order or requests differ')
    if sha(source.SOURCE.read_bytes()) != source.SOURCE_SHA or plan['source_train_sha256'] != source.SOURCE_SHA:
        raise ValueError('Pinned canonical training reference changed')
    canonical_rows, _ = source.load_source(source.SOURCE, 'train')
    canonical_by_id = {row['id']: row for row in canonical_rows}
    for row in rows:
        original = canonical_by_id.get(row['id'])
        if not original or row.get('source_split') != 'train' or row.get('source_revision') != source.REVISION:
            raise ValueError('Noncanonical training source')
        if any(row.get(key) != original.get(key) for key in original): raise ValueError('Original human source row changed')
        proof, _, _ = source.annotation_check(row['reference_solution'], row['gold_answer'])
        if (not proof or proof != row['annotation_verification'] or input_bytes(row) > MAX_MESSAGES_BYTES
                or numeric_answer(str(row['gold_answer'])) is None
                or sha(row['reference_solution'].encode('utf-8')) != row['reference_solution_sha256']
                or sha(row['prompt'].encode('utf-8')) != row['prompt_sha256']):
            raise ValueError('Reference proof, prompt or input bound changed')
    if sha(DESIGN.read_bytes()) != plan['design_sha256']: raise ValueError('Reviewed design changed after freeze')
    actual = protocol_identity(tokenizer or load_tokenizer(local_files_only=True))
    if actual != plan['protocol'] or digest(actual) != plan['protocol_sha256']:
        raise ValueError('Pinned protocol, tokenizer or source code changed')
    for item in plan['exclusion_artifacts']:
        if sha((ROOT.parent/item['run']).read_bytes()) != item['sha256']:
            raise ValueError('Frozen teaching/development exclusion snapshot changed')
    # Other prepared cohorts must also honor this pilot. Fail closed if a later
    # collection independently reused any of its questions before dispatch.
    current_records, _ = source.load_exclusions(output)
    current_excluded, _ = source.ancestry_exclusions(canonical_rows, current_records)
    if {row['id'] for row in rows} & current_excluded:
        raise ValueError('Pilot overlaps another current teaching/development cohort or detectable ancestry')
    return plan, rows, requests


def assert_funding(plan):
    """Read-only gate; caller owns provider refresh/reservation, never this code."""
    assert_no_study_owner()
    assert_reserved(plan)
    ledger = json.loads((ROOT/'runs/supervisor/budget.json').read_text(encoding='utf-8'))
    account = ledger.get('deepseek_budget_accounting', {})
    if account.get('status') != 'conditional_wallet_inference' or account.get('issues') or account.get('funding_history_ambiguous'):
        raise RuntimeError('Fresh unambiguous provider funding accounting is required')
    require_fresh_deepseek_budget(ledger)


def assert_no_study_owner(runs_root=None):
    """Honor the current study/accounting owner; never clear another lease."""
    root = Path(runs_root or ROOT/'runs')
    if any(root.rglob('study_watch.lock')) or any(root.rglob('study_tick.lock')):
        raise RuntimeError('Study watcher/tick lease requires owner release before new teacher dispatch')
    for path in root.rglob('study_watch_state.json'):
        try: state = json.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError):
            raise RuntimeError('Unverifiable study watch state requires owner review') from None
        if state.get('stage') != 'stopped':
            raise RuntimeError('Nonterminal study watch state blocks new teacher dispatch')


def attempt_paths(output, request_id):
    stem = Path(output)/'attempts'/sha(request_id.encode('utf-8'))
    return (stem.with_suffix('.attempt.json'), stem.with_suffix('.response.bin'), stem.with_suffix('.result.json'))


def result_from_wire(request, row, wire, marker):
    result = {'id': request['id'], 'question_id': row['id'], 'mode': request['mode'],
        'request_sha256': request['request_sha256'], 'started_at_utc': marker['started_at_utc'],
        'completed_at_utc': now(), 'failed': False, 'raw': None, 'response': '', 'reasoning_content': '',
        'wire_response_sha256': sha(wire), 'wire_response_bytes': len(wire), 'finish_reason': 'error'}
    try:
        raw = json.loads(wire)
        result['raw'] = raw
        if not isinstance(raw, dict): raise ValueError('Unexpected response object')
        choice = raw['choices'][0]; message = choice['message']
        if not isinstance(message.get('content'), (str, type(None))) or not isinstance(message.get('reasoning_content'), (str, type(None))):
            raise ValueError('Unexpected response channels')
        result.update(response=message.get('content') or '', reasoning_content=message.get('reasoning_content') or '',
            finish_reason=choice.get('finish_reason'), teacher_revision=raw.get('model'),
            system_fingerprint=raw.get('system_fingerprint'))
    except Exception as error:
        result.update(failed=True, error_type=type(error).__name__)
    return result


def call_request(request, row, output, key):
    """One original transmission only. Funding is checked by the dispatcher."""
    if request['payload'] != payload(row, request['mode']) or request['request_sha256'] != digest(request['payload']):
        raise ValueError('Request differs from frozen payload')
    if input_bytes(row) > MAX_MESSAGES_BYTES: raise ValueError('Input bound exceeded')
    marker_path, wire_path, result_path = attempt_paths(output, request['id'])
    marker = {'id': request['id'], 'request_sha256': request['request_sha256'], 'started_at_utc': now()}
    with marker_path.open('x', encoding='utf-8') as handle:
        handle.write(_canonical(marker)); handle.flush(); os.fsync(handle.fileno())
    started = time.monotonic()
    try:
        req = urllib.request.Request(API_URL, data=_canonical(request['payload']).encode('utf-8'),
            headers={'Authorization': 'Bearer '+key, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=120) as response:
            wire = response.read(MAX_RESPONSE_BYTES+1)
        # Exact received bytes precede JSON parsing and derived receipts.
        write_bytes(wire_path, wire)
        if len(wire) > MAX_RESPONSE_BYTES: raise ValueError('Response byte ceiling exceeded')
        result = result_from_wire(request, row, wire, marker)
    except Exception as error:
        result = {'id': request['id'], 'question_id': row['id'], 'mode': request['mode'],
            'request_sha256': request['request_sha256'], 'started_at_utc': marker['started_at_utc'],
            'completed_at_utc': now(), 'failed': True, 'raw': None, 'response': '', 'reasoning_content': '',
            'finish_reason': 'error', 'error_type': type(error).__name__, 'unknown_provider_usage': True}
        if isinstance(error, urllib.error.HTTPError): result['http_status'] = error.code
        if wire_path.exists():
            result.update(wire_response_sha256=sha(wire_path.read_bytes()), wire_response_bytes=wire_path.stat().st_size)
    result['elapsed_seconds'] = time.monotonic()-started
    write_json(result_path, result)
    return result


def recover_attempt(request, row, output):
    marker_path, wire_path, result_path = attempt_paths(output, request['id'])
    if not marker_path.exists():
        if wire_path.exists() or result_path.exists(): raise RuntimeError('Receipt without original attempt marker')
        return None
    marker = json.loads(marker_path.read_text(encoding='utf-8'))
    if marker.get('id') != request['id'] or marker.get('request_sha256') != request['request_sha256']:
        raise RuntimeError('Original attempt identity differs')
    if result_path.exists():
        result = json.loads(result_path.read_text(encoding='utf-8'))
    elif wire_path.exists():
        wire = wire_path.read_bytes()
        if len(wire) > MAX_RESPONSE_BYTES: raise RuntimeError('Oversize saved response needs manual reconciliation')
        result = result_from_wire(request, row, wire, marker)
        result['recovered_from_durable_wire'] = True
        write_json(result_path, result)
    else:
        raise RuntimeError('Ambiguous prior transmission: inspect process/provider; never resend automatically')
    if (result.get('id') != request['id'] or result.get('question_id') != row['id']
            or result.get('mode') != request['mode'] or result.get('request_sha256') != request['request_sha256']):
        raise RuntimeError('Saved receipt identity differs')
    if wire_path.exists() and sha(wire_path.read_bytes()) != result.get('wire_response_sha256'):
        raise RuntimeError('Saved wire response hash differs')
    if wire_path.exists() and wire_path.stat().st_size <= MAX_RESPONSE_BYTES:
        expected = result_from_wire(request, row, wire_path.read_bytes(), marker)
        stable_fields = ('id','question_id','mode','request_sha256','started_at_utc','failed','raw',
            'response','reasoning_content','wire_response_sha256','wire_response_bytes','finish_reason',
            'teacher_revision','system_fingerprint','error_type')
        if any(result.get(key) != expected.get(key) for key in stable_fields):
            raise RuntimeError('Derived saved receipt differs from original wire response')
    if result.get('raw') is not None:
        if not wire_path.exists() or json.loads(wire_path.read_bytes()) != result['raw']:
            raise RuntimeError('Parsed response differs from original wire receipt')
    return result


def verify_result(result, row, tokenizer):
    result = dict(result)
    content, reasoning = result.get('response'), result.get('reasoning_content')
    usage = provider_usage(result)
    usage_ok = all(isinstance(usage.get(key), int) and not isinstance(usage.get(key), bool) and usage[key] >= 0
                   for key in ('prompt_tokens', 'completion_tokens'))
    bounded = bounded_usage(result)
    flags = {'complete': not result.get('failed') and result.get('finish_reason') == 'stop',
        'content_present': isinstance(content, str) and bool(content.strip()),
        'reasoning_present': isinstance(reasoning, str) and bool(reasoning.strip()),
        'usage_present': usage_ok, 'provider_token_bounds_met': bounded, 'numeric_final_match': False,
        'teacher_identity_present': isinstance(result.get('teacher_revision'), str) and result['teacher_revision'].casefold().startswith('deepseek-v4-pro'),
        'context_fit': False, 'channels_preserved': True, 'trace_truncated': result.get('finish_reason') == 'length',
        'semantic_question_validity_verified': False, 'intermediate_reasoning_verified': False}
    if flags['content_present'] and content.count('####') == 1:
        predicted = numeric_answer(content.rsplit('####', 1)[1].strip())
        gold = numeric_answer(str(row['gold_answer']))
        flags['numeric_final_match'] = predicted is not None and predicted == gold
    reasons = []
    if not flags['complete']: reasons.append('failed_or_nonstop_completion')
    if not flags['content_present']: reasons.append('missing_visible_answer')
    if not flags['numeric_final_match']: reasons.append('unparsed_or_reference_mismatch')
    if not flags['teacher_identity_present']: reasons.append('unexpected_teacher_identity')
    if not usage_ok: reasons.append('missing_provider_usage')
    elif not bounded: reasons.append('provider_token_bound_exceeded')
    if result['mode'] == 'thinking' and not flags['reasoning_present']: reasons.append('missing_reasoning_channel')
    if result['mode'] == 'concise' and reasoning: reasons.append('unexpected_concise_reasoning_channel')
    try:
        encoded = encode_target(row, result['mode'], reasoning, content, tokenizer)
        flags['context_fit'] = encoded['context_fit']
        result['encoding'] = encoded
        if not encoded['context_fit']: reasons.append('student_context_over4096')
    except (ValueError, TypeError, UnicodeError):
        flags['channels_preserved'] = False; reasons.append('unsafe_or_invalid_channel_serialization')
    result.update(eligible=not reasons, verified_final_answer=flags['numeric_final_match'],
        verification=flags, rejection_reasons=reasons, trace_rewritten=False)
    return result


def summarize(output, plan, rows, results, stage, halt=None):
    by_key = {result['id']: result for result in results}
    if len(by_key) != len(results): raise ValueError('Duplicate original attempt records')
    pairs = []; model_mismatch_pairs = 0
    for row in rows:
        modes = {mode: by_key.get(row['id']+'::'+mode) for mode in MODES}
        if all(modes[mode] and modes[mode]['eligible'] for mode in MODES):
            if len({modes[mode]['teacher_revision'].casefold() for mode in MODES}) != 1:
                model_mismatch_pairs += 1; continue
            if len({modes[mode]['encoding']['prefix_ids_sha256'] for mode in MODES}) != 1:
                raise ValueError('Eligible pair does not share identical student prefix IDs')
            pairs.append({'question_id': row['id'], 'source_split': 'train', 'source_revision': source.REVISION,
                'prompt': row['prompt'], 'gold_answer': row['gold_answer'], 'reference_semantics_verified': False,
                'conditions': modes})
    stats = {}
    for mode in MODES:
        subset = [result for result in results if result['mode'] == mode]
        chosen = [pair['conditions'][mode] for pair in pairs]
        distributions = {}
        for key in ('supervised_tokens','reasoning_tokens','visible_content_tokens','context_tokens'):
            values = [result['encoding'][key] for result in chosen]
            distributions[key] = {'min': min(values), 'median': statistics.median(values), 'max': max(values)} if values else None
        stats[mode] = {'requested_output_cap': CAPS[mode],
            'thinking_parameter': 'disabled' if mode == 'concise' else 'enabled/high',
            'completed': len(subset), 'individually_eligible': sum(result['eligible'] for result in subset),
            'complete': sum(result['verification']['complete'] for result in subset),
            'numeric_final_match': sum(result['verification']['numeric_final_match'] for result in subset),
            'full_context_fit': sum(result['verification']['context_fit'] for result in subset),
            'paired_eligible_supervised_tokens': sum(result['encoding']['supervised_tokens'] for result in chosen),
            'paired_reasoning_tokens': sum(result['encoding']['reasoning_tokens'] for result in chosen),
            'paired_token_distributions': distributions,
            'rejection_counts': dict(Counter(reason for result in subset for reason in result['rejection_reasons']))}
    usage = {key: sum(provider_usage(result).get(key, 0) for result in results
                     if isinstance(provider_usage(result).get(key), int) and not isinstance(provider_usage(result).get(key), bool)
                     and provider_usage(result)[key] >= 0)
             for key in ('prompt_tokens', 'completion_tokens')}
    public = {'schema_version': 1, 'run_id': plan['run_id'], 'stage': stage, 'requested_questions': QUESTIONS,
        'requested_original_calls': 2*QUESTIONS, 'completed_original_calls': len(results),
        'eligible_question_pairs': len(pairs), 'conditions': stats, 'halt_reason': halt,
        'otherwise_eligible_pairs_with_returned_model_mismatch': model_mismatch_pairs,
        'failed_attempts': sum(bool(result.get('failed')) for result in results),
        'unknown_usage_attempts': sum(not result['verification']['usage_present'] for result in results),
        'recorded_peak_token_estimate_usd': (usage['prompt_tokens']*1.32+usage['completion_tokens']*3.96)/1e6,
        'cost_note': 'Recorded usage estimate excludes unknown failed-attempt charges; not a provider invoice. Frozen original-call bound remains0.8177664USD and requires its own1USD reservation before collection.',
        'conservative_max_cost_usd': plan['conservative_max_cost_usd'],
        'funds_reserved_by_preparation': False, 'new_student_training': False, 'official_test_accessed': False,
        'source_split': 'train', 'student_context_limit': CONTEXT, 'encoder_version': ENCODER_VERSION,
        'native_serialization_note': 'Both conditions deliberately share the native OPEN thinking generation prefix. The concise derived suffix immediately closes an empty span; it is not byte-identical to full-chat native empty-span rendering. Any future student comparison must freeze identical inference settings for base and both adapters; this pilot trains none.',
        'teacher_model_alias': MODEL, 'student_model': STUDENT, 'student_revision': REVISION,
        'canonical_training_source_revision': source.REVISION,
        'exclusion_artifact_count': len(plan.get('exclusion_artifacts', [])),
        'prior_canonical_questions_or_detectable_ancestry_excluded': plan.get('exclusion_review', {}).get('ancestry', {}).get('combined_unique_gsm_exclusions'),
        'artifact_fingerprints': {key: plan[key] for key in ('candidates_sha256','requests_sha256','protocol_sha256','design_sha256')},
        'prior_exposure_limit': plan['prior_exposure_limit'], 'updated_at_utc': now(),
        'interpretation': 'Feasibility only: paired modes also change output caps. Correct final numbers do not prove correct explanations, and the verified/full-fit intersection can select easier shorter questions. No Granite improvement has been measured by this pilot.'}
    write_bytes(Path(output)/'eligible_pairs.jsonl', rows_bytes(pairs))
    write_json(Path(output)/'teacher_summary.json', dict(public, usage=usage))
    write_json(PUBLIC, public)
    return public


def collect(output=RUN, workers=1):
    output = Path(output).resolve()
    if not 1 <= workers <= 4: raise ValueError('Use one to four pair workers')
    tokenizer = load_tokenizer(local_files_only=True)
    plan, rows, requests = validate_run(output, tokenizer)
    if other_collector_locks(output): raise RuntimeError('Another collector lock exists; inspect its owner before proceeding')
    fd = os.open(output/'collector.lock', os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    results = []; stop = threading.Event(); halt = None
    try:
        os.write(fd, str(os.getpid()).encode('ascii')); os.fsync(fd)
        if other_collector_locks(output): raise RuntimeError('Concurrent collector launch detected; stop and reconcile')
        (output/'attempts').mkdir(exist_ok=True)
        row_by_id = {row['id']: row for row in rows}
        result_path = output/'teacher_results.jsonl'
        prior = read_rows(result_path) if result_path.exists() else []
        prior_by_id = {result['id']: result for result in prior}
        if len(prior_by_id) != len(prior) or not set(prior_by_id) <= {request['id'] for request in requests}:
            raise RuntimeError('Append-only attempt identities differ')
        def append(receipt):
            verified = verify_result(receipt, row_by_id[receipt['question_id']], tokenizer)
            old = prior_by_id.get(verified['id'])
            if old is not None:
                if old != verified: raise RuntimeError('Append-only result differs from durable original receipt')
            else:
                with result_path.open('a', encoding='utf-8') as handle:
                    handle.write(_canonical(verified)+'\n'); handle.flush(); os.fsync(handle.fileno())
            results.append(verified)
            return verified
        pending_by_question = {}
        for request in requests:
            row = row_by_id[request['question_id']]
            receipt = recover_attempt(request, row, output)
            if receipt is not None:
                if pending_by_question.get(row['id']):
                    raise RuntimeError('Saved receipt exists after its missing frozen within-pair predecessor')
                append(receipt)
            elif request['id'] in prior_by_id: raise RuntimeError('Appended result lost its durable attempt receipt')
            else: pending_by_question.setdefault(row['id'], []).append(request)
        if not pending_by_question:
            return summarize(output, plan, rows, results, 'completed')
        if any(result.get('failed') or not bounded_usage(result) for result in results):
            return summarize(output, plan, rows, results, 'halted',
                'prior_failed_or_unbounded_attempt_requires_review')
        assert_no_study_owner()
        assert_funding(plan)
        key = credential('DEEPSEEK_API_KEY')
        if not key: raise RuntimeError('DeepSeek credential missing')
        summarize(output, plan, rows, results, 'collecting')
        deadline = time.monotonic()+MAX_SECONDS
        def run_pair(question_id, pending):
            receipts = []; reason = None
            for request in pending:
                if stop.is_set(): break
                if time.monotonic() >= deadline:
                    reason = 'bounded_collector_time_limit'; stop.set(); break
                try:
                    assert_no_study_owner()
                    assert_funding(plan)
                except (RuntimeError, ValueError, OSError):
                    reason = 'fresh_funding_guard_stopped'; stop.set(); break
                receipt = call_request(request, row_by_id[question_id], output, key)
                receipts.append(receipt)
                if receipt.get('http_status') in (401,402,403,429): reason = 'provider_account_or_rate_limit'
                elif receipt.get('failed'): reason = 'failed_response_no_retry'
                elif not bounded_usage(receipt):
                    reason = 'unknown_or_out_of_bound_provider_usage'
                if reason: stop.set(); break
            return receipts, reason
        queue = iter(pending_by_question.items())
        with ThreadPoolExecutor(max_workers=workers) as executor:
            active = {}
            for _ in range(min(workers, len(pending_by_question))):
                question_id, pending = next(queue)
                active[executor.submit(run_pair, question_id, pending)] = question_id
            while active:
                done, _ = wait(active, return_when=FIRST_COMPLETED)
                for future in done:
                    active.pop(future)
                    try:
                        receipts, reason = future.result()
                        for receipt in receipts: append(receipt)
                    except Exception:
                        stop.set(); raise
                    if reason: halt = reason
                    summarize(output, plan, rows, results, 'halted' if stop.is_set() else 'collecting', halt)
                if not stop.is_set():
                    while len(active) < workers:
                        entry = next(queue, None)
                        if entry is None: break
                        question_id, pending = entry
                        active[executor.submit(run_pair, question_id, pending)] = question_id
        stage = 'completed' if len(results) == 2*QUESTIONS else 'halted'
        return summarize(output, plan, rows, results, stage, halt)
    except Exception as error:
        stop.set()
        write_json(output/'collector_failure.json', {'error_type': type(error).__name__, 'at_utc': now(),
            'note': 'Inspect process/lock, immutable plan, wire receipts and funding. Never replay an ambiguous transmitted request.'})
        try: summarize(output, plan, rows, results, 'failed_requires_reconciliation', type(error).__name__)
        except (OSError, ValueError): pass
        raise
    finally:
        os.close(fd)
        try:
            if (output/'collector.lock').read_text(encoding='ascii').strip() == str(os.getpid()):
                (output/'collector.lock').unlink()
        except FileNotFoundError: pass


def inspect_run(output=RUN):
    """Unpaid verification from original receipts; never infer paid completion."""
    output = Path(output).resolve()
    if (output/'collector.lock').exists():
        raise RuntimeError('Collector owns this summary; inspect its durable state without rewriting')
    tokenizer = load_tokenizer(local_files_only=True)
    plan, rows, requests = validate_run(output, tokenizer)
    by_id = {row['id']: row for row in rows}
    history_path = output/'teacher_results.jsonl'
    history = read_rows(history_path) if history_path.exists() else []
    saved = {result['id']: result for result in history}
    if len(saved) != len(history) or not set(saved) <= {request['id'] for request in requests}:
        raise RuntimeError('Append-only attempt identities differ')
    results = []
    for request in requests:
        receipt = recover_attempt(request, by_id[request['question_id']], output)
        if receipt is None:
            if request['id'] in saved: raise RuntimeError('Appended result lost its durable original receipt')
            continue
        result = verify_result(receipt, by_id[request['question_id']], tokenizer)
        if request['id'] in saved and saved[request['id']] != result:
            raise RuntimeError('Append-only result differs from original receipt')
        results.append(result)
    stage = 'completed' if len(results) == 2*QUESTIONS else ('partial_unpaid_inspection' if results else 'prepared_unpaid')
    return summarize(output, plan, rows, results, stage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', nargs='?', default='prepare', choices=('prepare','inspect','collect'))
    parser.add_argument('--output', type=Path, default=RUN)
    parser.add_argument('--workers', type=int, default=1)
    args = parser.parse_args()
    if args.action == 'prepare': result = prepare(args.output)
    elif args.action == 'collect': result = collect(args.output, args.workers)
    else: result = inspect_run(args.output)
    print(json.dumps({key: result[key] for key in ('run_id','stage','candidate_count','completed_original_calls','eligible_question_pairs') if key in result}), flush=True)


if __name__ == '__main__': main()
