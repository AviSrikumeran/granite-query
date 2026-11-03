"""Immutable source-balanced chunks and bounded concise DeepSeek collection.

Preparation audits the finished source cohort against its pinned raw blocks.
Collection requires fresh funding reconciliation and an existing reservation.
Original receipts, incorrect answers, incomplete outputs and source-reference
origins are retained. There are no automatic retries, GPU calls or test inputs.
"""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from collections import Counter, defaultdict
from datetime import datetime, timezone
import argparse
import json
import math
import os
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from cloud import student_pool as transport
from cloud.math_cohort import SOURCES, adapt, canonical, digest
from cloud.matched_teacher import _attempt_paths, _canonical, _digest, _write
from cloud.deepseek_reconcile import require_fresh_deepseek_budget
from cloud.student_valuation import load_tokenizer
from cloud.progress import record

COHORT = ROOT / 'runs/math_source_cohort1800_v1'
RUN = ROOT / 'runs/math_source_teacher1800_v1'
PUBLIC = ROOT.parents[1] / 'progress/MATH_TEACHER.json'
SEED = 20261108
MAX_CALLS = 1800
CHUNK_SIZE = 512
UNIT_COST_BOUND = (2000 * 1.32 + 1024 * 3.96) / 1e6


def now():
    return datetime.now(timezone.utc).isoformat()


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8-sig').split('\n') if line.strip()]


def row_bytes(rows):
    return ''.join(_canonical(row) + '\n' for row in rows).encode('utf-8')


def balanced_order(rows):
    groups = defaultdict(list)
    for row in sorted(rows, key=lambda row: row['id']):
        groups[row['source']].append(row)
    for source, group in groups.items():
        random.Random(SEED ^ int(digest(source.encode())[:8], 16)).shuffle(group)
    output = []
    for index in range(max(map(len, groups.values()))):
        for source in sorted(groups):
            if index < len(groups[source]):
                output.append(groups[source][index])
    return output


def audit_cohort(cohort):
    cohort = Path(cohort).resolve()
    if not cohort.is_relative_to((ROOT / 'runs').resolve()):
        raise ValueError('Only local ignored source cohorts are permitted')
    if (cohort / 'cohort.lock').exists():
        raise RuntimeError('Source cohort is still active; do not freeze a growing request pool')
    manifest_raw, plan_raw, candidates_raw = [(cohort / name).read_bytes()
        for name in ('manifest.json', 'plan.json', 'candidates.jsonl')]
    manifest, source_plan = json.loads(manifest_raw), json.loads(plan_raw)
    if manifest['stage'] not in ('prepared', 'prepared_with_bounded_gaps'):
        raise RuntimeError('Source cohort has not reached a final durable state')
    if digest(candidates_raw) != manifest['candidates_sha256']:
        raise RuntimeError('Source candidate file changed after final preparation')
    rows = read_rows(cohort / 'candidates.jsonl')
    if len(rows) != manifest['actual_prompts'] or not 1 <= len(rows) <= MAX_CALLS:
        raise ValueError('Frozen cohort size differs or exceeds the1800-call ceiling')
    by_source = {source['repo']: source for source in SOURCES}
    by_id = {row['id']: row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError('Duplicate source-cohort identities')
    expected_by_source = defaultdict(dict)
    for row in rows:
        source = by_source.get(row.get('source'))
        if not source or row.get('source_split') != 'train' or any(
                row.get(key) != source[expected] for key, expected in
                [('source_revision', 'revision'), ('source_config', 'config'), ('hf_split', 'split')]):
            raise ValueError('Unapproved source, revision or training split')
        if row.get('reference_type') != source['reference_type'] or row.get('teacher_generated') is not False:
            raise ValueError('Source-reference origin is missing or changed')
        if transport.input_bound(row) > transport.MAX_MESSAGES_UTF8_BYTES:
            raise ValueError('Frozen teacher request exceeds the conservative byte bound')
        expected_by_source[row['source']][row['row_idx']] = row
    reviewed = set()
    forbidden = set(source_plan['conservative_forbidden_template_ids'])
    template_counts = Counter()
    for source in SOURCES:
        folder = cohort / 'sources' / source['repo'].replace('/', '__')
        for block in sorted(folder.glob('rows_*.json')):
            if block.name.endswith('.metadata.json'):
                continue
            raw = block.read_bytes()
            metadata = json.loads(block.with_suffix('.json.metadata.json').read_text(encoding='utf-8'))
            if metadata.get('revision') != source['revision'] or metadata['sha256'] != digest(raw):
                raise ValueError('Pinned source block hash/revision differs')
            payload = json.loads(raw)
            for wrapper in payload['rows']:
                expected = expected_by_source[source['repo']].get(wrapper['row_idx'])
                if expected is None:
                    continue
                actual, reason = adapt(source, wrapper, forbidden)
                if actual != expected or reason != 'adapter_eligible':
                    raise ValueError('Candidate no longer matches complete source-specific context/reference')
                reviewed.add(expected['id'])
                if expected.get('template_id') is not None:
                    template_counts[expected['template_id']] += 1
    if reviewed != set(by_id) or any(count > source_plan['template_cap'] for count in template_counts.values()):
        raise ValueError('Raw attribution review or template cap failed')
    # Recheck that exclusions did not change since cohort freezing. No test
    # source is ever opened: this is the cohort's explicit training-file list.
    for exclusion in source_plan['exclusions']:
        if digest(Path(exclusion['path']).read_bytes()) != exclusion['sha256']:
            raise ValueError('Previous training/development exclusion artifact changed')
    review = {'cohort_run': cohort.name, 'source_plan_sha256': digest(plan_raw),
        'source_manifest_sha256': digest(manifest_raw), 'source_candidates_sha256': digest(candidates_raw),
        'candidate_count': len(rows), 'complete_raw_attributions_verified': len(reviewed),
        'source_counts': dict(Counter(row['source'] for row in rows)),
        'reference_origin_counts': dict(Counter(row['reference_type'] for row in rows)),
        'unique_templates': len(template_counts), 'max_examples_per_template': max(template_counts.values(), default=0),
        'max_serialized_messages_utf8_bytes': max(transport.input_bound(row) for row in rows),
        'official_test_accessed': False,
        'review_limitations': 'Reviewed source identity, complete prompt context, scalar references, frozen exclusions and lineage caps. This does not independently prove procedural/majority-vote reference correctness.'}
    return rows, review


def prepare(cohort=COHORT, output=RUN, limit=MAX_CALLS):
    output = Path(output).resolve()
    if not output.is_relative_to((ROOT / 'runs').resolve()) or not 1 <= limit <= MAX_CALLS:
        raise ValueError('Use an ignored run and at most1800 calls')
    rows, review = audit_cohort(cohort)
    rows = balanced_order(rows)[:limit]
    requests = [{'id': row['id'], 'payload': transport.build_payload(row)} for row in rows]
    chunks = []
    for index, start in enumerate(range(0, len(rows), CHUNK_SIZE)):
        selected, requested = rows[start:start + CHUNK_SIZE], requests[start:start + CHUNK_SIZE]
        chunks.append({'index': index, 'ids': [row['id'] for row in selected],
            'request_count': len(selected), 'requests_sha256': _digest(requested),
            'source_counts': dict(Counter(row['source'] for row in selected)),
            'conservative_max_cost_usd': len(selected) * UNIT_COST_BOUND})
    reservation = float(math.ceil(len(rows) * UNIT_COST_BOUND))
    plan = {'schema_version': 1, 'run_id': output.name, 'budget_job_id': output.name + '-teacher',
        'seed': SEED, 'candidate_count': len(rows), 'max_attempts': len(rows),
        'chunks': chunks, 'chunk_size': CHUNK_SIZE, 'candidate_records_sha256': _digest(rows),
        'candidates_file_sha256': digest(row_bytes(rows)), 'requests_file_sha256': digest(row_bytes(requests)),
        'requests_sha256': _digest(requests), 'source_review': review,
        'model': transport.MODEL, 'max_output_tokens': 1024, 'thinking_enabled': False,
        'prompt_version': transport.PROMPT_VERSION, 'max_concurrent': 4, 'automatic_retries': 0,
        'max_serialized_messages_utf8_bytes': transport.MAX_MESSAGES_UTF8_BYTES,
        'conservative_input_token_bound': 2000, 'conservative_max_cost_usd': len(rows) * UNIT_COST_BOUND,
        'reserved_usd_required': reservation, 'context_limit': 2048, 'max_response_tokens': 768,
        'student_model': 'ibm-granite/granite-4.2-3b',
        'student_revision': '4e9c275e232f10211ec88644d106a1f6a1b60e06',
        'source_reference_policy': 'Eligibility means teacher final matches provided local reference; human/procedural/majority-vote origins remain attached and are not relabelled independent gold',
        'official_test_accessed': False, 'raw_responses_retained': True, 'trace_rewriting': False}
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'plan.json').exists():
        if json.loads((output / 'plan.json').read_text(encoding='utf-8')) != plan:
            raise RuntimeError('Immutable teacher plan differs')
        if (output / 'candidates.jsonl').read_bytes() != row_bytes(rows) or (output / 'requests.jsonl').read_bytes() != row_bytes(requests):
            raise RuntimeError('Immutable source-balanced requests changed')
    else:
        (output / 'candidates.jsonl').write_bytes(row_bytes(rows))
        (output / 'requests.jsonl').write_bytes(row_bytes(requests))
        (output / 'chunks').mkdir()
        for chunk in chunks:
            _write(output / 'chunks' / f'{chunk["index"]:03d}.json', chunk)
        _write(output / 'source_review.json', review)
        _write(output / 'plan.json', plan)
    return plan


def assert_reserved(plan):
    ledger = json.loads((ROOT / 'runs/supervisor/budget.json').read_text(encoding='utf-8'))
    require_fresh_deepseek_budget(ledger)
    jobs = [job for job in ledger['jobs'] if job.get('run_id') == plan['budget_job_id'] and job.get('service') == 'deepseek']
    if len(jobs) != 1 or jobs[0].get('status') not in ('reserved', 'in_progress', 'collecting'):
        raise RuntimeError('This immutable teacher run needs an active DeepSeek reservation')
    if jobs[0].get('reserved_usd', 0) < plan['reserved_usd_required'] or plan['conservative_max_cost_usd'] > jobs[0]['reserved_usd']:
        raise RuntimeError('Reservation cannot cover this bounded request plan')
    if ledger['limits']['deepseek'] > 20:
        raise RuntimeError('DeepSeek project ceiling exceeds authorization')


def other_collector_locks(output):
    return [path for path in (ROOT / 'runs').rglob('collector.lock') if path.parent != output]


def collect(output=RUN, workers=4):
    output = Path(output).resolve()
    if not output.is_relative_to((ROOT / 'runs').resolve()) or not 1 <= workers <= 4:
        raise ValueError('Require an ignored run and one to four workers')
    plan = json.loads((output / 'plan.json').read_text(encoding='utf-8'))
    rows, requests = read_rows(output / 'candidates.jsonl'), read_rows(output / 'requests.jsonl')
    if not 1 <= len(rows) <= MAX_CALLS or len(rows) != plan['candidate_count']:
        raise ValueError('Request count exceeds frozen allowance')
    if digest((output / 'candidates.jsonl').read_bytes()) != plan['candidates_file_sha256'] or digest((output / 'requests.jsonl').read_bytes()) != plan['requests_file_sha256']:
        raise ValueError('Frozen files changed')
    if requests != [{'id': row['id'], 'payload': transport.build_payload(row)} for row in rows]:
        raise ValueError('Current generation settings differ from immutable requests')
    expected_ids = [row['id'] for row in rows]
    if ([key for chunk in plan['chunks'] for key in chunk['ids']] != expected_ids
            or any(not 1 <= len(chunk['ids']) <= CHUNK_SIZE for chunk in plan['chunks'])
            or len(set(expected_ids)) != len(expected_ids)):
        raise ValueError('Chunk manifest differs from bounded unique request sequence')
    others = other_collector_locks(output)
    if others:
        raise RuntimeError('Another teacher collector lock exists; inspect its PID before concurrent paid collection')
    assert_reserved(plan)
    tokenizer = load_tokenizer(local_files_only=True)
    lock = output / 'collector.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    by_id, halt = {}, None
    try:
        os.write(fd, str(os.getpid()).encode('ascii'))
        os.fsync(fd)
        (output / 'attempts').mkdir(exist_ok=True)
        results_path = output / 'teacher_results.jsonl'
        results = read_rows(results_path) if results_path.exists() else []
        by_id = {row['id']: row for row in results}
        row_by_id = {row['id']: row for row in rows}
        if len(by_id) != len(results) or not set(by_id) <= set(row_by_id):
            raise RuntimeError('Existing result IDs are duplicated or outside this plan')

        def append(raw):
            result = transport.verify(raw, tokenizer)
            result['reference_match_is_independent_gold'] = result['reference_type'] == 'human_dataset_answer'
            with results_path.open('a', encoding='utf-8') as handle:
                handle.write(_canonical(result) + '\n'); handle.flush(); os.fsync(handle.fileno())
            by_id[result['id']] = result
            return result

        def snapshot(stage):
            ordered = [by_id[row['id']] for row in rows if row['id'] in by_id]
            eligible = [row for row in ordered if row['eligible']]
            usage = {key: sum((row.get('raw') or {}).get('usage', {}).get(key, 0) for row in ordered)
                     for key in ('prompt_tokens', 'completion_tokens')}
            chunks = [{'index': chunk['index'], 'requested': chunk['request_count'],
                       'completed': sum(key in by_id for key in chunk['ids'])} for chunk in plan['chunks']]
            summary = {'run_id': output.name, 'stage': stage, 'requested': len(rows), 'completed': len(ordered),
                'eligible': len(eligible), 'failed': sum(row.get('failed', False) for row in ordered),
                'truncated': sum(row.get('truncated', False) for row in ordered),
                'supervised_tokens_available': sum(row.get('supervised_tokens', 0) for row in eligible),
                'eligibility_counts': dict(Counter(row['verification'] for row in ordered)),
                'eligible_by_source': dict(Counter(row['source'] for row in eligible)),
                'eligible_by_reference_origin': dict(Counter(row['reference_type'] for row in eligible)),
                'chunks': chunks, 'usage': usage,
                'estimated_peak_cost_usd': (usage['prompt_tokens'] * 1.32 + usage['completion_tokens'] * 3.96) / 1e6,
                'cost_note': 'Recorded peak-rate token estimate, not wallet consumption or invoice; missing failed-request usage remains unknown',
                'halt_reason': halt, 'automatic_retries': 0, 'thinking_enabled': False,
                'official_test_accessed': False, 'updated_at_utc': now(),
                'interpretation': 'Eligibility means complete short teacher response matches the provided reference; source origins retain different levels of independence. No trained Granite improvement is claimed.'}
            transport.write_jsonl(output / 'eligible.jsonl', eligible)
            _write(output / 'teacher_summary.json', summary)
            _write(PUBLIC, {key: value for key, value in summary.items() if key not in ('usage',)})
            return summary

        for row in rows:
            expected = _digest(transport.build_payload(row))
            if row['id'] in by_id:
                if by_id[row['id']].get('request_sha256') != expected:
                    raise RuntimeError('Saved request hash differs')
                continue
            marker, saved = _attempt_paths(output, row['id'])
            if saved.exists():
                recovered = json.loads(saved.read_text(encoding='utf-8'))
                if recovered.get('id') != row['id'] or recovered.get('request_sha256') != expected:
                    raise RuntimeError('Recoverable receipt differs')
                append(recovered)
            elif marker.exists():
                raise RuntimeError('Ambiguous prior attempt requires reconciliation; never automatically repeat it')
        snapshot('collecting')
        key = transport.credential('DEEPSEEK_API_KEY') if len(by_id) < len(rows) else None
        if len(by_id) < len(rows) and not key:
            raise RuntimeError('DeepSeek credential missing')
        record('in_progress', 'Source-balanced concise math teacher collection started',
            f"Frozen {len(rows)} requests in {len(plan['chunks'])} sequential chunks from the completed source cohort. Four workers maximum, nonthinking V4,1024 output-token limit, no retries. Human, procedural and synthetic majority-vote references remain labelled. Funds reserved before generation.", output.name + '-started')
        failures = 0
        for chunk in plan['chunks']:
            pending = [row_by_id[key] for key in chunk['ids'] if key not in by_id]
            if not pending:
                continue
            assert_reserved(plan)
            queue = iter(pending)
            with ThreadPoolExecutor(max_workers=workers) as executor:
                active = {executor.submit(transport._call, next(queue), output, key) for _ in range(min(workers, len(pending)))}
                while active:
                    finished, active = wait(active, return_when=FIRST_COMPLETED)
                    for future in finished:
                        result = append(future.result())
                        failures = failures + 1 if result.get('failed') else 0
                        if result.get('http_status') in (401, 402, 403, 429):
                            halt = 'provider_http_' + str(result['http_status'])
                        elif failures >= 3:
                            halt = 'three_consecutive_request_failures'
                        summary = snapshot('halted' if halt else 'collecting')
                        print(json.dumps({field: summary[field] for field in ('stage', 'completed', 'requested', 'eligible', 'failed')}), flush=True)
                    if not halt:
                        while len(active) < workers:
                            row = next(queue, None)
                            if row is None: break
                            active.add(executor.submit(transport._call, row, output, key))
            if halt:
                break
        summary = snapshot('completed' if len(by_id) == len(rows) else 'halted')
        record('completed' if summary['stage'] == 'completed' else 'failed',
            'Concise source-cohort teacher collection ' + summary['stage'],
            f"Saved {summary['completed']}/{len(rows)} original attempts; {summary['eligible']} passed strict reference-match/completion/token checks, supplying {summary['supervised_tokens_available']} supervised tokens. Source-origin breakdowns and failed attempts are preserved. No Granite training or official test evaluation was launched.", output.name + '-' + summary['stage'])
        return summary
    except Exception as error:
        _write(output / 'collector_failure.json', {'error_type': type(error).__name__, 'completed': len(by_id),
            'at_utc': now(), 'note': 'Inspect original receipts, existing lock and funding before any resume; no retries'})
        record('failed', 'Source-cohort teacher collector stopped',
            'A preflight or durable-state condition stopped collection. Original receipts remain preserved; reconcile funding/attempt state before resuming.', output.name + '-guard-stopped')
        raise
    finally:
        os.close(fd)
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'collect'))
    parser.add_argument('--cohort', type=Path, default=COHORT)
    parser.add_argument('--output', type=Path, default=RUN)
    parser.add_argument('--limit', type=int, default=MAX_CALLS)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    result = prepare(args.cohort, args.output, args.limit) if args.action == 'prepare' else collect(args.output, args.workers)
    print(json.dumps({key: result[key] for key in ('run_id', 'candidate_count', 'reserved_usd_required') if key in result}
                     if args.action == 'prepare' else result), flush=True)


if __name__ == '__main__':
    main()
