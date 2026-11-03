"""Freeze and collect a bounded, disjoint, concise GSM8K teaching pool.

No automatic retries, no official-test inputs, no GPU work or budget mutations.
Each request has a durable exclusive attempt marker before transmission. Resume
recovers saved responses and refuses ambiguous earlier requests. The caller must
reserve the configured four-dollar allowance before collection.
"""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from cloud.matched_teacher import PREFIX, API_URL, _canonical, _digest, _write, _attempt_paths
from cloud.run_api_pilot import credential
from cloud.prepare_verified_math import load_exclusions, Deduplicator, EXCLUSION_PATHS
from cloud.student_valuation import load_tokenizer, encode_example
from ranking.verification import teacher_eligible, numeric_answer

RUN = ROOT / 'runs/student_valuation_pool512_v1'
SCORES = ROOT.parent / 'ranking/runs/gsm8k_preview_128_seed42/scores.jsonl'
PROBES = ROOT.parent / 'ranking/runs/gsm8k_preview_128_seed42/target_queries.jsonl'
SOURCE_REVISION = '3101c7d5072418e28b9008a6636bde82a006892c'
SOURCE_TRAIN_SHA256 = '17f347dc51477c50d4efb83959dbb7c56297aba886e5544ee2aaed3024813465'
SCORES_SHA256 = 'd63b38c957141b896861e34a268675d83804db56ca7e8c57a7a00d5867dd69f4'
MODEL = 'deepseek-v4-pro'
MAX_CALLS = 512
MAX_TOKENS = 1024
SEED = 20261105
JOB_ID = 'student_valuation_pool512_v1-teacher'
PROMPT_VERSION = 'matched-granite-concise-nonthinking-v1'
RESERVATION_USD = 4.0
# Content and role serialization together leave headroom below the reservation's
# conservative 2000-input-token/request ceiling; no model-specific tokenizer is
# claimed for DeepSeek. UTF-8 bytes upper-bound byte-based text tokens.
MAX_MESSAGES_UTF8_BYTES = 1900
WORST_CASE_USD = MAX_CALLS * (2000 * 1.32 + MAX_TOKENS * 3.96) / 1e6


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8-sig').split('\n') if line.strip()]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_jsonl(path, rows):
    temporary = Path(path).with_suffix('.tmp')
    temporary.write_text(''.join(_canonical(row) + '\n' for row in rows), encoding='utf-8')
    temporary.replace(path)


def build_payload(row):
    """Same user text as Granite/frozen64; no gold/reference solution is sent."""
    return {'model': MODEL, 'max_tokens': MAX_TOKENS, 'stream': False,
            'thinking': {'type': 'disabled'},
            'messages': [{'role': 'user', 'content': PREFIX + row['prompt']}]}


def input_bound(row):
    return len(_canonical(build_payload(row)['messages']).encode('utf-8'))


def prepare(output=RUN, scores_path=SCORES, probes_path=PROBES):
    output = Path(output).resolve()
    if not output.is_relative_to((ROOT / 'runs').resolve()):
        raise ValueError('Artifacts must remain under ignored cloud/runs')
    if sha(scores_path) != SCORES_SHA256:
        raise RuntimeError('Pinned GSM8K score-pool artifact changed')
    exclusions, exclusion_sources = load_exclusions((*EXCLUSION_PATHS, probes_path))
    excluded_ids = {row['id'] for row in exclusions}
    dedup = Deduplicator(exclusions)
    rows = sorted(read_jsonl(scores_path), key=lambda row: row['id'])
    if len(rows) != 7344 or len({row['id'] for row in rows}) != len(rows):
        raise ValueError('Unexpected score-pool size/identities')
    if any(row.get('source_split') != 'train' or not row['id'].startswith('gsm8k:train:') for row in rows):
        raise ValueError('Only official-training-split GSM8K rows are permitted')
    random.Random(SEED).shuffle(rows)
    selected, decisions = [], []
    for row in rows:
        if len(selected) == MAX_CALLS:
            break
        if row['id'] in excluded_ids:
            decisions.append({'id': row['id'], 'reason': 'existing_or_probe_id'})
            continue
        if numeric_answer(row.get('gold_answer', '')) is None:
            decisions.append({'id': row['id'], 'reason': 'non_scalar_gold'})
            continue
        if input_bound(row) > MAX_MESSAGES_UTF8_BYTES:
            decisions.append({'id': row['id'], 'reason': 'input_byte_bound'})
            continue
        overlap = dedup.match(row)
        if overlap:
            decisions.append(dict(overlap, id=row['id']))
            continue
        chosen = {key: row[key] for key in ('id', 'prompt', 'gold_answer', 'source', 'source_split')}
        chosen['source_revision'] = SOURCE_REVISION
        chosen['prompt_sha256'] = hashlib.sha256(row['prompt'].encode('utf-8')).hexdigest()
        selected.append(chosen)
        dedup.add(chosen)
    if len(selected) != MAX_CALLS:
        raise RuntimeError('Not enough disjoint bounded candidates; do not weaken the pool')
    requests = [{'id': row['id'], 'payload': build_payload(row)} for row in selected]
    plan = {'schema_version': 1, 'run_id': output.name, 'budget_job_id': JOB_ID,
            'candidate_count': MAX_CALLS, 'sampling_seed': SEED,
            'candidate_ids': [row['id'] for row in selected],
            'candidates_sha256': _digest(selected), 'requests_sha256': _digest(requests),
            'source': 'openai/grade-school-math', 'source_split': 'train',
            'source_revision': SOURCE_REVISION, 'source_train_sha256': SOURCE_TRAIN_SHA256,
            'source_score_pool_sha256': sha(scores_path), 'exclusions': exclusion_sources,
            'excluded_unique_ids': len(excluded_ids), 'exclusion_decision_counts': dict(Counter(d['reason'] for d in decisions)),
            'model': MODEL, 'teacher_revision_policy': 'Mutable API alias; actual response model saved per example',
            'max_output_tokens': MAX_TOKENS, 'thinking_enabled': False,
            'prompt_version': PROMPT_VERSION, 'user_prompt_matches_frozen64_granite': True,
            'max_attempts': MAX_CALLS, 'automatic_retries': 0, 'max_concurrent': 4,
            'max_messages_utf8_bytes': MAX_MESSAGES_UTF8_BYTES,
            'input_budget_bound_tokens_per_call': 2000,
            'conservative_max_cost_usd': WORST_CASE_USD, 'reserved_usd_required': RESERVATION_USD,
            'cost_basis': 'Conservative peak-rate bound using <=2000 input tokens, <=1024 completion tokens/request; not invoice',
            'student_model': 'ibm-granite/granite-4.2-3b',
            'student_revision': '4e9c275e232f10211ec88644d106a1f6a1b60e06',
            'max_response_tokens': 768, 'context_limit': 2048,
            'official_test_accessed': False, 'raw_outputs_retained': True,
            'trace_rewriting': False, 'trace_truncation': False,
            'selection_note': 'Both selectors receive the same verified short-response pool; eligibility is frozen before valuation'}
    output.mkdir(parents=True, exist_ok=True)
    plan_path = output / 'plan.json'
    if plan_path.exists():
        if json.loads(plan_path.read_text(encoding='utf-8')) != plan:
            raise RuntimeError('Immutable plan differs; use a new separately reserved run')
        if read_jsonl(output / 'candidates.jsonl') != selected or read_jsonl(output / 'requests.jsonl') != requests:
            raise RuntimeError('Frozen request/input artifact changed')
    else:
        write_jsonl(output / 'candidates.jsonl', selected)
        write_jsonl(output / 'requests.jsonl', requests)
        write_jsonl(output / 'preparation_exclusions.jsonl', decisions)
        _write(plan_path, plan)
    return plan


def assert_reserved(plan):
    ledger = json.loads((ROOT / 'runs/supervisor/budget.json').read_text(encoding='utf-8'))
    matches = [job for job in ledger['jobs'] if job.get('run_id') == JOB_ID and job.get('service') == 'deepseek']
    if len(matches) != 1 or matches[0].get('status') not in {'reserved', 'in_progress'}:
        raise RuntimeError('Bounded teacher job has no active reservation')
    if matches[0].get('reserved_usd', 0) < RESERVATION_USD or WORST_CASE_USD > RESERVATION_USD:
        raise RuntimeError('Reservation does not cover frozen worst-case request allowance')
    if ledger['limits']['deepseek'] > 20 or ledger['estimated_spend']['deepseek'] + ledger['reserved']['deepseek'] > ledger['limits']['deepseek']:
        raise RuntimeError('DeepSeek service ceiling would be exceeded')
    if plan['budget_job_id'] != JOB_ID:
        raise RuntimeError('Reservation/run mismatch')


def _call(row, output, key):
    payload = build_payload(row)
    if input_bound(row) > MAX_MESSAGES_UTF8_BYTES:
        raise RuntimeError('Request input-byte bound exceeded')
    marker, saved = _attempt_paths(output, row['id'])
    with marker.open('x', encoding='utf-8') as handle:
        json.dump({'id': row['id'], 'request_sha256': _digest(payload),
                   'started_at_utc': datetime.now(timezone.utc).isoformat()}, handle)
        handle.flush()
        os.fsync(handle.fileno())
    result = dict(row, request_sha256=_digest(payload), teacher_model=MODEL,
                  teacher_revision='unknown; no successful API response', response='', raw=None,
                  truncated=False, finish_reason='error', failed=False, generated_tokens=0,
                  generation={'prompt_version': PROMPT_VERSION,
                              'settings': {key: value for key, value in payload.items() if key != 'messages'}})
    started = time.monotonic()
    try:
        request = urllib.request.Request(API_URL, data=_canonical(payload).encode('utf-8'),
            headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = json.load(response)
        result['raw'] = raw
        choice = raw['choices'][0]
        result.update(response=choice['message'].get('content') or '',
                      teacher_revision=raw.get('model', MODEL), finish_reason=choice.get('finish_reason'),
                      truncated=choice.get('finish_reason') == 'length',
                      generated_tokens=raw.get('usage', {}).get('completion_tokens', 0))
    except Exception as error:
        # Never serialize an error body, credentials, headers or exception text.
        result.update(failed=True, error_type=type(error).__name__)
        if isinstance(error, urllib.error.HTTPError):
            result['http_status'] = error.code
    result['elapsed_seconds'] = time.monotonic() - started
    _write(saved, result)  # Raw receipt precedes append-only aggregate output.
    return result


def verify(result, tokenizer):
    result = dict(result, generation=dict(result['generation']))
    okay, reason = teacher_eligible(result)
    if result.get('failed') or result.get('finish_reason') != 'stop':
        okay, reason = False, 'failed_or_nonstop_completion'
    if okay:
        encoded = encode_example(result, tokenizer)
        result.update(prefix_tokens=encoded['prompt_tokens'], supervised_tokens=encoded['response_tokens'],
                      total_tokens=encoded['input_tokens'])
        if encoded['response_tokens'] > 768:
            okay, reason = False, 'response_too_long'
        elif encoded['input_tokens'] > 2048:
            okay, reason = False, 'context_too_long'
    result.update(eligible=okay, verified_final_answer=okay, verification=reason,
                  trace_truncated=result.get('truncated', False), trace_rewritten=False)
    result['generation']['verification'] = {'verified_final_answer': okay,
        'method': 'local_numeric_reference_match_and_exact_pinned_student_token_lengths',
        'complete': result.get('finish_reason') == 'stop',
        'trace_truncated': result.get('truncated', False)}
    return result


def collect(output=RUN, workers=4):
    if not 1 <= workers <= 4:
        raise ValueError('Require one to four workers')
    output = Path(output).resolve()
    plan = json.loads((output / 'plan.json').read_text(encoding='utf-8'))
    rows = read_jsonl(output / 'candidates.jsonl')
    requests = read_jsonl(output / 'requests.jsonl')
    if not 1 <= len(rows) <= MAX_CALLS or len(rows) != plan['candidate_count']:
        raise RuntimeError('Candidate count differs from frozen allowance')
    if _digest(rows) != plan['candidates_sha256'] or _digest(requests) != plan['requests_sha256']:
        raise RuntimeError('Immutable candidate/request hashes changed')
    if requests != [{'id': row['id'], 'payload': build_payload(row)} for row in rows]:
        raise RuntimeError('Frozen requests differ from current collector')
    if any(row.get('source_split') != 'train' or not row['id'].startswith('gsm8k:train:') for row in rows):
        raise RuntimeError('Only training-split GSM8K candidates permitted')
    assert_reserved(plan)
    tokenizer = load_tokenizer(local_files_only=True)
    lock = output / 'collector.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    by_id = {}
    halt_reason = None
    try:
        os.write(fd, str(os.getpid()).encode('ascii'))
        os.fsync(fd)
        (output / 'attempts').mkdir(exist_ok=True)
        results_path = output / 'teacher_results.jsonl'
        results = read_jsonl(results_path) if results_path.exists() else []
        by_id = {row['id']: row for row in results}
        if len(by_id) != len(results) or not set(by_id) <= {row['id'] for row in rows}:
            raise RuntimeError('Saved result identities are duplicated/outside plan')

        def snapshot(stage):
            ordered = [by_id[row['id']] for row in rows if row['id'] in by_id]
            eligible = [row for row in ordered if row.get('eligible')]
            usage = {key: sum((row.get('raw') or {}).get('usage', {}).get(key, 0) for row in ordered)
                     for key in ('prompt_tokens', 'completion_tokens')}
            summary = {'run_id': output.name, 'stage': stage, 'requested': len(rows), 'completed': len(ordered),
                       'eligible': len(eligible), 'failed': sum(row.get('failed', False) for row in ordered),
                       'truncated': sum(row.get('truncated', False) for row in ordered),
                       'eligibility_counts': dict(Counter(row['verification'] for row in ordered)),
                       'supervised_tokens_available': sum(row.get('supervised_tokens', 0) for row in eligible),
                       'usage': usage, 'estimated_upper_cost_usd': (usage['prompt_tokens'] * 1.32 + usage['completion_tokens'] * 3.96) / 1e6,
                       'cost_note': 'Recorded tokens at conservative peak rates; failed unreported charges unknown; not invoice',
                       'automatic_retries': 0, 'teacher_model': MODEL, 'thinking_enabled': False,
                       'official_test_accessed': False, 'halt_reason': halt_reason,
                       'updated_at_utc': datetime.now(timezone.utc).isoformat()}
            write_jsonl(output / 'eligible.jsonl', eligible)
            _write(output / 'teacher_summary.json', summary)
            return summary

        def append(raw_result):
            result = verify(raw_result, tokenizer)
            with results_path.open('a', encoding='utf-8') as handle:
                handle.write(_canonical(result) + '\n')
                handle.flush()
                os.fsync(handle.fileno())
            by_id[result['id']] = result
            return result

        pending = []
        for row in rows:
            expected = _digest(build_payload(row))
            if row['id'] in by_id:
                if by_id[row['id']].get('request_sha256') != expected:
                    raise RuntimeError('Saved result request hash differs')
                continue
            marker, saved = _attempt_paths(output, row['id'])
            if saved.exists():
                result = json.loads(saved.read_text(encoding='utf-8'))
                if result.get('id') != row['id'] or result.get('request_sha256') != expected:
                    raise RuntimeError('Recoverable response differs from immutable request')
                append(result)
            elif marker.exists():
                raise RuntimeError('Ambiguous earlier attempt; reconcile before any duplicate request')
            else:
                pending.append(row)
        snapshot('collecting')
        if pending:
            key = credential('DEEPSEEK_API_KEY')
            if not key:
                raise RuntimeError('DeepSeek credential missing')
            # Schedule a window of <=4 requests. Auth/account/rate failures halt
            # new work; already transmitted window members are always preserved.
            queue = iter(pending)
            consecutive_failures = 0
            with ThreadPoolExecutor(max_workers=workers) as executor:
                active = {executor.submit(_call, next(queue), output, key) for _ in range(min(workers, len(pending)))}
                while active:
                    completed, active = wait(active, return_when=FIRST_COMPLETED)
                    for future in completed:
                        result = append(future.result())
                        consecutive_failures = consecutive_failures + 1 if result.get('failed') else 0
                        if result.get('http_status') in (401, 402, 403, 429):
                            halt_reason = 'provider_http_' + str(result['http_status'])
                        elif consecutive_failures >= 3:
                            halt_reason = 'three_consecutive_request_failures'
                        summary = snapshot('halted' if halt_reason else 'collecting')
                        print(json.dumps({key: summary[key] for key in ('stage', 'completed', 'requested', 'eligible', 'failed')}), flush=True)
                    if not halt_reason:
                        while len(active) < workers:
                            row = next(queue, None)
                            if row is None:
                                break
                            active.add(executor.submit(_call, row, output, key))
        return snapshot('completed' if len(by_id) == len(rows) else 'halted')
    except Exception as error:
        _write(output / 'collector_failure.json', {'error_type': type(error).__name__,
            'completed': len(by_id), 'updated_at_utc': datetime.now(timezone.utc).isoformat(),
            'note': 'Inspect lock and durable attempt receipts before resuming; no automatic retries'})
        raise
    finally:
        os.close(fd)
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'collect'))
    parser.add_argument('--output', type=Path, default=RUN)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    if args.action == 'prepare':
        plan = prepare(args.output)
        print(json.dumps({key: plan[key] for key in ('run_id', 'candidate_count', 'candidates_sha256', 'conservative_max_cost_usd')}))
    else:
        print(json.dumps(collect(args.output, args.workers)), flush=True)


if __name__ == '__main__':
    main()
