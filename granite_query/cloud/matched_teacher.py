"""Matched DeepSeek development evaluation; preserve every attempt, never filter answers.

Usage: python cloud/matched_teacher.py evaluate --input PATH --output PATH
No training or budget-ledger mutation occurs here. The caller must reserve funds.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cloud.run_api_pilot import credential
from cloud.comparison_metrics import score, summarize

MODEL = 'deepseek-v4-pro'
MAX_OUTPUT_TOKENS = 4096
PROMPT_VERSION = 'matched-granite-compare-v1'
PREFIX = ('Solve the math problem. Explain only the necessary calculation steps concisely. '
          'Finish with #### followed by the numeric final answer.\n\n')
API_URL = 'https://api.deepseek.com/chat/completions'


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def _digest(value):
    return hashlib.sha256(_canonical(value).encode('utf-8')).hexdigest()


def _write(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def read_inputs(path):
    rows = []
    seen = set()
    # Only LF delimits records; Unicode line separators can occur within prompts.
    for line in Path(path).read_text(encoding='utf-8-sig').split('\n'):
        if not line.strip():
            continue
        row = json.loads(line)
        if not all(isinstance(row.get(k), str) and row[k].strip()
                   for k in ('id', 'prompt', 'gold_answer')):
            raise ValueError('Every evaluation row requires string id, prompt and gold_answer')
        if row['id'] in seen:
            raise ValueError('Duplicate evaluation ID')
        if row.get('source_split', 'train') != 'train':
            raise ValueError('This development collector accepts training-split rows only')
        seen.add(row['id'])
        rows.append(row)
    if not 1 <= len(rows) <= 128:
        raise ValueError('Require between 1 and 128 development examples')
    return rows


def build_payload(row):
    """The exact user text used by modal_compare; no reference/gold fields sent."""
    return {'model': MODEL, 'max_tokens': MAX_OUTPUT_TOKENS, 'stream': False,
            'thinking': {'type': 'enabled'},
            'messages': [{'role': 'user', 'content': PREFIX + row['prompt']}]}


def _attempt_paths(output, row_id):
    slug = hashlib.sha256(row_id.encode('utf-8')).hexdigest()
    return output / 'attempts' / (slug + '.json'), output / 'attempts' / (slug + '.result.json')


def _call(row, output, key):
    payload = build_payload(row)
    request_sha = _digest(payload)
    marker, saved = _attempt_paths(output, row['id'])
    # Exclusive marker is written before transmission. An ambiguous attempt is
    # never automatically replayed after a crash or interrupted response.
    with marker.open('x', encoding='utf-8') as handle:
        json.dump({'id': row['id'], 'request_sha256': request_sha,
                   'started_at_utc': datetime.now(timezone.utc).isoformat()}, handle)
    result = {'id': row['id'], 'gold_answer': row['gold_answer'],
              'request_sha256': request_sha, 'teacher_model': MODEL,
              'response': '', 'raw': None, 'truncated': False,
              'finish_reason': 'error', 'failed': False, 'generated_tokens': 0,
              'generation': {'prompt_version': PROMPT_VERSION,
                             'settings': {k: v for k, v in payload.items() if k != 'messages'}}}
    started = time.monotonic()
    try:
        req = urllib.request.Request(API_URL, data=_canonical(payload).encode('utf-8'),
            headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=120) as response:
            raw = json.load(response)
        result['raw'] = raw
        choice = raw['choices'][0]
        result.update(response=choice['message'].get('content') or '',
                      teacher_revision=raw.get('model', MODEL),
                      finish_reason=choice.get('finish_reason'),
                      truncated=choice.get('finish_reason') == 'length',
                      generated_tokens=raw.get('usage', {}).get('completion_tokens', 0))
    except Exception as exc:
        # Never serialize exception text, headers, auth data, or an error body.
        result['failed'] = True
        result['error_type'] = type(exc).__name__
        if isinstance(exc, urllib.error.HTTPError):
            result['http_status'] = exc.code
    result['elapsed_seconds'] = time.monotonic() - started
    result['scoring'] = score(result)
    _write(saved, result)
    return result


def evaluate(input_path, output_path, workers=4):
    if not 1 <= workers <= 4:
        raise ValueError('Worker count must be between 1 and 4')
    input_path, output = Path(input_path).resolve(), Path(output_path).resolve()
    rows = read_inputs(input_path)
    output.mkdir(parents=True, exist_ok=True)
    lock = output / 'collector.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, str(os.getpid()).encode())
        (output / 'attempts').mkdir(exist_ok=True)
        requests = [{'id': r['id'], 'payload': build_payload(r)} for r in rows]
        frozen = {'schema_version': 1, 'input_sha256': hashlib.sha256(input_path.read_bytes()).hexdigest(),
                  'ids': [r['id'] for r in rows], 'request_manifest_sha256': _digest(requests),
                  'model': MODEL, 'max_output_tokens': MAX_OUTPUT_TOKENS,
                  'thinking_enabled': True, 'prompt_version': PROMPT_VERSION,
                  'max_attempts': len(rows), 'automatic_retries': 0,
                  'scoring': 'All attempted outcomes retained; no answer-based eligibility filter',
                  'latency_scope': 'HTTP request round trip, including network and provider service time',
                  'comparison_note': 'Same user prompt/questions as Granite; provider thinking and token limits differ'}
        manifest_path = output / 'manifest.json'
        if manifest_path.exists():
            if json.loads(manifest_path.read_text(encoding='utf-8')) != frozen:
                raise RuntimeError('Immutable evaluation manifest does not match this request')
        else:
            _write(manifest_path, frozen)
            (output / 'requests.jsonl').write_text(''.join(_canonical(r)+'\n' for r in requests), encoding='utf-8')
        results_path = output / 'results.jsonl'
        results = ([json.loads(line) for line in results_path.read_text(encoding='utf-8').split('\n') if line.strip()]
                   if results_path.exists() else [])
        by_id = {r['id']: r for r in results}
        if len(by_id) != len(results) or not set(by_id) <= set(frozen['ids']):
            raise RuntimeError('Existing result IDs are duplicated or outside the manifest')
        pending = []
        def append(result):
            with results_path.open('a', encoding='utf-8') as handle:
                handle.write(_canonical(result)+'\n')
                handle.flush()
                os.fsync(handle.fileno())
            by_id[result['id']] = result
        for row in rows:
            expected = _digest(build_payload(row))
            if row['id'] in by_id:
                if by_id[row['id']].get('request_sha256') != expected:
                    raise RuntimeError('Saved result request hash mismatch')
                continue
            marker, saved = _attempt_paths(output, row['id'])
            if saved.exists():
                result = json.loads(saved.read_text(encoding='utf-8'))
                if result.get('id') != row['id'] or result.get('request_sha256') != expected:
                    raise RuntimeError('Recoverable result does not match immutable request')
                append(result)
            elif marker.exists():
                raise RuntimeError('Ambiguous earlier attempt requires reconciliation; automatic duplicate call refused')
            else:
                pending.append(row)
        if pending:
            key = credential('DEEPSEEK_API_KEY')
            if not key:
                raise RuntimeError('DeepSeek credential is not configured')
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(_call, row, output, key) for row in pending]
                for future in as_completed(futures):
                    result = future.result()
                    append(result)
                    print(json.dumps({'completed': len(by_id), 'requested': len(rows),
                                      'failed': result['failed'],
                                      'truncated': result['truncated']}), flush=True)
        ordered = [by_id[r['id']] for r in rows]
        summary = summarize(ordered)
        usage = {'prompt_tokens': sum(r.get('raw', {}).get('usage', {}).get('prompt_tokens', 0)
                                     for r in ordered if r.get('raw')),
                 'completion_tokens': sum(r.get('raw', {}).get('usage', {}).get('completion_tokens', 0)
                                         for r in ordered if r.get('raw'))}
        summary.update(requested_count=len(rows), completed_count=len(ordered),
                       failed_count=sum(r['failed'] for r in ordered),
                       usage=usage, model=MODEL, prompt_version=PROMPT_VERSION,
                       estimated_upper_cost_usd=(usage['prompt_tokens']*1.32 + usage['completion_tokens']*3.96)/1e6,
                       cost_note='Recorded usage at published peak prices; unreported failed-request charges are unknown',
                       latency_scope=frozen['latency_scope'],
                       comparison_note=frozen['comparison_note'])
        _write(output / 'summary.json', summary)
        return summary
    finally:
        os.close(fd)
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    run = sub.add_parser('evaluate')
    run.add_argument('--input', required=True, type=Path)
    run.add_argument('--output', required=True, type=Path)
    run.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.input, args.output, args.workers)), flush=True)


if __name__ == '__main__':
    main()
