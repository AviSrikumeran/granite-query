"""Reviewed continuation of335 NEVER-ATTEMPTED V4 original TRAIN requests.

The original failed request stays failed/unknown and is never transmitted here.
No original source, plan, session, review, budget, wire or error is rewritten.
This driver neither reserves nor refreshes funds and never retries a request.
"""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
import argparse
import os
from pathlib import Path
import threading
import time

from cloud import native_reasoning_collection as col

VERSION = 'native-reasoning-v4-unsent335-continuation-v1'
ORIGINALS = 512
PRIOR = 177
PENDING = 335
UNKNOWN_ID = 'gsm8k:train:00583::concise'
EXITED_PIDS = (10112, 16248)
FOLDER = 'continuations/unsent335_v1'


def _date(value):
    if not isinstance(value, str): raise ValueError('Zoned UTC timestamp required')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None: raise ValueError('Zoned UTC timestamp required')
    return result.astimezone(timezone.utc)


def _attestation(value):
    if (not isinstance(value, dict) or set(value) != {'verified_exited','pids','verified_at_utc','method'}
            or value.get('verified_exited') is not True or value.get('pids') != list(EXITED_PIDS)
            or any(type(pid) is not int or pid <= 0 for pid in value['pids'])
            or value.get('method') != 'external_host_identity_and_exit_verification'):
        raise ValueError('Exact externally verified original host exit attestation required')
    _date(value['verified_at_utc'])
    return value


def _pending_records(requests, output):
    return [request for request in requests if not any(path.exists() for path in col.attempt_paths(output, request['id']))]


def _snapshot(output, tokenizer):
    output = col.private(output)
    plan, rows, requests = col.validate_run(output, tokenizer=tokenizer)
    if len(requests) != ORIGINALS or plan['max_original_requests'] != ORIGINALS:
        raise ValueError('This driver only continues the frozen whole512 original requests')
    if (output/'collector.lock').exists(): raise ValueError('An original or continuation collector still owns the lease')
    inventory = col._receipt_inventory(output, plan, requests)
    results = col._history(output, plan, rows, requests, tokenizer)
    pending = _pending_records(requests, output)
    # Ambiguous/orphaned originals cannot become pending by dropping receipts.
    if len(results) != PRIOR or inventory['original_intents'] != PRIOR or len(pending) != PENDING:
        raise ValueError('Exact177 retained originals and335 entirely unclaimed requests required')
    unknown = [result for result in results if not result['provider_usage_known']]
    if (len(unknown) != 1 or unknown[0]['id'] != UNKNOWN_ID or unknown[0].get('failed') is not True
            or unknown[0].get('error_type') != 'TimeoutError'):
        raise ValueError('The one original TimeoutError must remain failed and usage-unknown')
    request = next(request for request in requests if request['id'] == UNKNOWN_ID)
    error_path = col.attempt_paths(output, request['id'])[4]
    original_review = col.read(output/'reviewed_for_collection.json'); session_path = output/'collection_session.json'
    session = col.read(session_path)
    original_review_sha = col.validate_review(plan, session['reservation_id'], original_review)
    start = _date(session['started_at_utc'])
    deadline = datetime.fromtimestamp(start.timestamp()+col.LAUNCH_WINDOW_SECONDS, timezone.utc).isoformat()
    pending_bindings = [{'id': request['id'], 'question_id': request['question_id'], 'mode': request['mode'],
        'request_sha256': request['request_sha256'], 'payload_sha256': col.digest(request['payload'])} for request in pending]
    return plan, rows, requests, results, pending, {
        'version': VERSION, 'collection_version': plan['version'], 'run_id': plan['run_id'],
        'original_plan_sha256': plan['plan_sha256'], 'original_plan_file_sha256': col.sha((output/'plan.json').read_bytes()),
        'original_requests_sha256': plan['requests_sha256'], 'original_protocol_sha256': plan['protocol_sha256'],
        'original_source_code_hashes': plan['protocol']['source_code_hashes'],
        'original_review_sha256': original_review_sha,
        'original_review_file_sha256': col.sha((output/'reviewed_for_collection.json').read_bytes()),
        'original_session_sha256': col.digest(session), 'original_session_file_sha256': col.sha(session_path.read_bytes()),
        'reservation_id': session['reservation_id'], 'reservation_required_usd': '7',
        'original_session_started_at_utc': session['started_at_utc'], 'original_absolute_launch_deadline_utc': deadline,
        'whole_original_request_count': ORIGINALS, 'retained_original_outcomes': PRIOR,
        'original_unknown_error': {'id': request['id'], 'request_sha256': request['request_sha256'],
            'error_sha256': col.sha(error_path.read_bytes()), 'failed': True, 'usage_unknown': True},
        'baseline_receipt_inventory': inventory, 'never_attempted_requests': pending_bindings,
        'never_attempted_requests_sha256': col.digest(pending_bindings), 'approved_new_original_count': PENDING,
        'driver_source_sha256': col.sha(Path(__file__).read_bytes()), 'max_concurrent': 4,
        'automatic_retries': 0, 'original_error_must_never_be_resent': True,
        'retain_full_original_reservation_for_unknown_usage': True, 'official_test_accessed': False}


def review_template(output=col.RUN, *, host_exit_attestation, tokenizer=None):
    tokenizer = tokenizer or col.load_tokenizer(local_files_only=True)
    *_, snapshot = _snapshot(output, tokenizer)
    return dict(snapshot, reviewed=False, host_exit_attestation=_attestation(host_exit_attestation))


def validate_approval(output, approval, tokenizer):
    if not isinstance(approval, dict): raise ValueError('Typed continuation approval required')
    actual = _snapshot(output, tokenizer)
    expected = dict(actual[-1], reviewed=True, host_exit_attestation=_attestation(approval.get('host_exit_attestation')))
    if approval != expected: raise ValueError('Continuation approval does not match exact originals, pending scope, source or host exit')
    if _date(approval['host_exit_attestation']['verified_at_utc']) < _date(actual[-1]['original_session_started_at_utc']):
        raise ValueError('Host exit attestation predates the actual collection session')
    return actual


def inspect(output=col.RUN, *, tokenizer=None):
    tokenizer = tokenizer or col.load_tokenizer(local_files_only=True)
    *_, snapshot = _snapshot(output, tokenizer)
    return {key: snapshot[key] for key in ('version','run_id','retained_original_outcomes',
        'approved_new_original_count','original_absolute_launch_deadline_utc','driver_source_sha256')}


def collect(output=col.RUN, *, approval_path, authorized=False, workers=4, tokenizer=None,
            transport=col.http, ledger_path=None, key=None, clock=col.now):
    if authorized is not True: raise ValueError('Explicit execution of the separately reviewed continuation required')
    if type(workers) is not int or not 1 <= workers <= 4: raise ValueError('At most four pair workers')
    output = col.private(output); tokenizer = tokenizer or col.load_tokenizer(local_files_only=True)
    approval = col.read(approval_path)
    plan, rows, requests, retained, pending, snapshot = validate_approval(output, approval, tokenizer)
    original_review = col.read(output/'reviewed_for_collection.json')
    reservation_id = snapshot['reservation_id']; original_review_sha = snapshot['original_review_sha256']
    col.require_budget(plan, reservation_id, original_review, ledger_path=ledger_path, clock=clock)
    deadline = _date(snapshot['original_absolute_launch_deadline_utc']).timestamp()
    if _date(clock()).timestamp() >= deadline: raise ValueError('Original absolute launch window is over; do not reset it')
    if col.other_collector_locks(output): raise ValueError('Another collector owner must reconcile first')
    folder = col.private(output/FOLDER); intent_path = folder/'continuation_intent.json'
    if intent_path.exists(): raise ValueError('Existing continuation intent requires reconciliation; no automatic rerun')
    lock = col.private(output/'collector.lock')
    token = col.encoded({'pid': os.getpid(), 'driver_version': VERSION, 'approval_sha256': col.digest(approval), 'started_at_utc': clock()})
    with lock.open('xb') as handle: handle.write(token); handle.flush(); os.fsync(handle.fileno())
    stop = threading.Event(); gate = threading.Lock(); halt = None; new_ids = []
    try:
        if col.other_collector_locks(output): raise ValueError('Concurrent collector detected; no new transmissions')
        # Recheck the exact old inventory after taking the common owner lease.
        current = col._receipt_inventory(output, plan, requests)
        if current != snapshot['baseline_receipt_inventory'] or _pending_records(requests, output) != pending:
            raise ValueError('Original receipt/pending scope changed while obtaining lease')
        col.write(intent_path, {'version': VERSION, 'approval_sha256': col.digest(approval),
            'driver_source_sha256': snapshot['driver_source_sha256'], 'original_plan_sha256': plan['plan_sha256'],
            'baseline_receipt_inventory_sha256': current['sha256'],
            'pending_requests_sha256': snapshot['never_attempted_requests_sha256'],
            'maximum_new_originals': PENDING, 'original_deadline_utc': snapshot['original_absolute_launch_deadline_utc'],
            'started_at_utc': clock(), 'automatic_retries': 0})
        col.write(folder/'approved_reconciliation.json', approval)
        key = key if key is not None else col.credential('DEEPSEEK_API_KEY')
        if not key: raise ValueError('DeepSeek credential unavailable')
        by_id = {row['id']: row for row in rows}; by_question = {}
        for request in pending: by_question.setdefault(request['question_id'], []).append(request)
        def run_pair(identifier, entries):
            received = []; reason = None
            for request in entries:
                with gate:
                    if stop.is_set(): break
                    if _date(clock()).timestamp() >= deadline:
                        stop.set(); return received, 'original_absolute_deadline_no_new_calls'
                    if any(path.exists() for path in col.attempt_paths(output, request['id'])):
                        stop.set(); return received, 'pending_request_already_claimed_no_resend'
                    try: col.require_budget(plan, reservation_id, original_review, ledger_path=ledger_path, clock=clock)
                    except Exception:
                        stop.set(); return received, 'fresh_original_reservation_guard_failed'
                try:
                    raw = col.call_request(plan, request, by_id[identifier], output, key,
                        reservation_id=reservation_id, review_sha256=original_review_sha, transport=transport)
                    value = col.verify_result(raw, by_id[identifier], tokenizer); received.append(value)
                    if value['failed'] or not value['provider_token_bounds_met']:
                        stop.set(); reason = 'new_failed_unknown_or_overbound_original_no_retry'; break
                except Exception:
                    stop.set(); return received, 'new_original_requires_reconciliation_no_retry'
            return received, reason
        queue = iter(by_question.items())
        with ThreadPoolExecutor(max_workers=workers) as executor:
            active = {}
            for _ in range(min(workers, len(by_question))):
                identifier, entries = next(queue); active[executor.submit(run_pair, identifier, entries)] = identifier
            while active:
                done, _ = wait(active, return_when=FIRST_COMPLETED)
                for future in done:
                    active.pop(future); received, reason = future.result()
                    for value in received:
                        with col.private(output/'teacher_results.jsonl').open('ab') as handle:
                            handle.write(col.encoded(value)+b'\n'); handle.flush(); os.fsync(handle.fileno())
                        new_ids.append(value['id'])
                    if reason: halt = reason
                if not stop.is_set():
                    while len(active) < workers:
                        entry = next(queue, None)
                        if entry is None: break
                        identifier, entries = entry; active[executor.submit(run_pair, identifier, entries)] = identifier
        results = col._history(output, plan, rows, requests, tokenizer, append=True)
        result, pairs = col.summary(plan, rows, results,
            stage='completed' if len(results) == ORIGINALS else 'halted', halt=halt)
        result.update(continuation_version=VERSION, continuation_approval_sha256=col.digest(approval),
            continuation_new_retained_outcomes=len(results)-PRIOR, original_failed_outcome_retained=True,
            full_original_reservation_must_remain_held=True)
        col.write_bytes(output/'eligible_pairs.jsonl', col.rows_bytes(pairs), immutable=False)
        col.write(output/'teacher_summary.json', result, immutable=False)
        pending_ids = {request['id'] for request in pending}
        col.write(folder/'continuation_terminal.json', {'stage': result['stage'], 'new_retained_outcomes': len(results)-PRIOR,
            'whole_original_outcomes': len(results), 'halt_reason': halt, 'finished_at_utc': clock(),
            'new_request_ids': [value['id'] for value in results if value['id'] in pending_ids], 'reservation_released': False})
        return result
    except Exception as error:
        # No error body, credential or raw reasoning enters this status record.
        col.write(folder/'continuation_failure.json', {'error_type': type(error).__name__,
            'at_utc': clock(), 'original_reservation_must_remain_held': True,
            'automatic_retry_permitted': False})
        raise
    finally:
        if lock.exists() and lock.read_bytes() == token: lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('inspect','collect'), nargs='?', default='inspect')
    parser.add_argument('--output', type=Path, default=col.RUN); parser.add_argument('--approval-path', type=Path)
    parser.add_argument('--authorized', action='store_true'); parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    if args.action == 'collect':
        if args.approval_path is None: parser.error('Exact separate reconciliation approval required')
        result = collect(args.output, approval_path=args.approval_path, authorized=args.authorized, workers=args.workers)
    else: result = inspect(args.output)
    print(col.encoded({key: result[key] for key in ('run_id','stage','retained_original_outcomes',
        'approved_new_original_count','original_absolute_launch_deadline_utc') if key in result}).decode())


if __name__ == '__main__': main()
