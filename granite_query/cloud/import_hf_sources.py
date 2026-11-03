"""Bounded, resumable public Hugging Face training-split sample imports.

Imports are real cached rows, not a claim that every source is training-ready.
Only explicitly named training splits are read; evaluation splits are never
downloaded. Raw data/cards stay under ignored cloud/runs. The public inventory
uses an explicit field allowlist and contains no examples or reasoning traces.
No model weights, paid model calls, training jobs or budget mutations occur.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import time
from urllib.parse import urlencode, quote
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
REGISTRY = ROOT / 'hf_source_registry.json'
RUN = ROOT / 'runs/hf_training_sources_40_v1'
PUBLIC = ROOT.parents[1] / 'progress/HF_SOURCE_INVENTORY.json'
SEED = 20261106
SCHEMA_VERSION = 1
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 48 * 1024 * 1024
PUBLIC_FIELDS = (
    'repo', 'family', 'domain', 'url', 'revision', 'license_listed', 'status',
    'config', 'split', 'sample_rows', 'untruncated_rows', 'raw_bytes', 'raw_sha256',
    'numeric_reference_prompts', 'duplicate_prompts', 'provenance_note',
    'metadata_reviewed', 'card_saved', 'error_type', 'http_status', 'limitation',
    'viewer_partial_coverage', 'sampling_note', 'license_metadata_status',
)


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(value).hexdigest()


def write(path, value):
    temporary = Path(path).with_suffix(Path(path).suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def append_event(folder, event):
    with (folder / 'events.jsonl').open('a', encoding='utf-8') as handle:
        handle.write(canonical(dict(at_utc=now(), **event)) + '\n')
        handle.flush()
        os.fsync(handle.fileno())


class DownloadLimit(RuntimeError):
    pass


class RevisionMismatch(RuntimeError):
    pass


class SourceHTTP:
    """At most two 429 retries with bounded backoff; no paid endpoints allowed."""
    def __init__(self, folder, max_bytes=MAX_TOTAL_BYTES, *, offline=False, deadline=None):
        self.folder, self.max_bytes, self.offline = folder, max_bytes, offline
        self.source_bytes = 0
        self.network_bytes = 0
        self.last_request = {}
        self.deadline = deadline
        self.accounted_paths = set()
        for metadata in (folder / 'sources').rglob('*.metadata.json'):
            saved = json.loads(metadata.read_text(encoding='utf-8'))
            cache = Path(str(metadata)[:-len('.metadata.json')]).resolve()
            if cache.exists():
                self.source_bytes += cache.stat().st_size
                self.accounted_paths.add(cache)

    def get(self, url, cache, *, revision=None, max_bytes=MAX_RESPONSE_BYTES):
        cache = Path(cache)
        sidecar = cache.with_suffix(cache.suffix + '.metadata.json')
        if not url.startswith(('https://huggingface.co/', 'https://datasets-server.huggingface.co/')):
            raise ValueError('Only public Hugging Face endpoints are allowed')
        if cache.exists() or sidecar.exists():
            if not cache.exists() or not sidecar.exists():
                raise RuntimeError('Incomplete cache requires inspection')
            data, meta = cache.read_bytes(), json.loads(sidecar.read_text(encoding='utf-8'))
            if meta['url'] != url or meta['sha256'] != digest(data) or (revision and meta.get('revision') != revision):
                raise RuntimeError('Cached download hash/revision mismatch')
        else:
            if self.offline:
                raise RuntimeError('Requested source artifact is not cached; offline mode made no request')
            host = url.split('/')[2]
            for attempt in range(3):
                if self.deadline is not None and time.monotonic() >= self.deadline:
                    raise DownloadLimit('Bounded importer wall-time allowance exhausted')
                delay = max(0, 3.0 - (time.monotonic() - self.last_request.get(host, 0)))
                if self.deadline is not None and time.monotonic() + delay >= self.deadline:
                    raise DownloadLimit('Bounded importer wall-time allowance exhausted')
                if delay:
                    time.sleep(delay)
                self.last_request[host] = time.monotonic()
                try:
                    request = urllib.request.Request(url, headers={'User-Agent': 'GraniteQuery-bounded-source-audit/1.0',
                                                                  'Accept-Encoding': 'identity'})
                    timeout = min(35, max(1, self.deadline - time.monotonic())) if self.deadline else 35
                    with urllib.request.urlopen(request, timeout=timeout) as response:
                        headers = {key.casefold(): value for key, value in response.headers.items()}
                        if revision and headers.get('x-revision') != revision:
                            raise RevisionMismatch('Dataset-server snapshot differs from pinned repository revision')
                        available = min(max_bytes, self.max_bytes - self.source_bytes)
                        if available <= 0 or (headers.get('content-length') and int(headers['content-length']) > available):
                            raise DownloadLimit('Response exceeds frozen per-response/global byte allowance')
                        data = response.read(available + 1)
                        self.network_bytes += len(data)
                        if len(data) > available:
                            raise DownloadLimit('Response exceeded byte allowance')
                    meta = {'url': url, 'sha256': digest(data), 'bytes': len(data),
                            'revision': headers.get('x-revision'), 'saved_at_utc': now()}
                    cache.write_bytes(data)
                    write(sidecar, meta)
                    break
                except urllib.error.HTTPError as error:
                    if error.code != 429 or attempt == 2:
                        raise
                    raw_delay = error.headers.get('Retry-After', '') if error.headers else ''
                    backoff = min(60, max(15 * 2**attempt, int(raw_delay) if raw_delay.isdigit() else 0))
                    if self.deadline is not None and time.monotonic() + backoff >= self.deadline:
                        raise DownloadLimit('Wall-time allowance cannot accommodate required backoff')
                    append_event(self.folder, {'event': 'rate_limit_backoff', 'url': url, 'seconds': backoff, 'attempt': attempt + 1})
                    time.sleep(backoff)
        unaccounted = 0 if cache.resolve() in self.accounted_paths else len(data)
        if len(data) > max_bytes or self.source_bytes + unaccounted > self.max_bytes:
            raise DownloadLimit('Cached data exceeds frozen byte allowance')
        self.source_bytes += unaccounted
        self.accounted_paths.add(cache.resolve())
        return data, meta


def choose_train_split(source, payload):
    permitted = source.get('preferred_splits', ['train'])
    if any(re.search(r'(^|[_-])(test|validation|eval|dev)([_-]|$)', name, re.I) for name in permitted):
        raise ValueError('Evaluation split requests are forbidden')
    splits = [split for split in payload.get('splits', []) if split['split'] in permitted]
    if source.get('config'):
        preferred = [split for split in splits if split['config'] == source['config']]
        if preferred:
            splits = preferred
    if not splits:
        return None
    return sorted(splits, key=lambda split: (permitted.index(split['split']),
                    0 if split['config'] == 'default' else 1, split['config']))[0]


def check_rows_coverage(payload, *, expected_total=None, expected_partial=None):
    # https://huggingface.co/docs/dataset-viewer/rows explains that partial
    # refers to limited dataset coverage. It does not truncate returned cells.
    if not isinstance(payload.get('partial'), bool) or not isinstance(payload.get('num_rows_total'), int):
        raise RuntimeError('Missing source coverage metadata')
    if expected_total is not None and payload['num_rows_total'] != expected_total:
        raise RuntimeError('Source row coverage changed between blocks')
    if expected_partial is not None and payload['partial'] != expected_partial:
        raise RuntimeError('Source partial-coverage status changed between blocks')
    return payload['partial']


def prompt_and_reference(row):
    """Conservative cross-source adapter; references are NOT teacher verification."""
    fields = {str(key).casefold(): value for key, value in row.items()}
    prompt = None
    if isinstance(fields.get('body'), str) and isinstance(fields.get('question'), str):
        prompt = fields['body'] + '\n\n' + fields['question']
    else:
        for key in ('problem', 'question', 'prompt', 'instruction'):
            if isinstance(fields.get(key), str) and fields[key].strip():
                prompt = fields[key]
                if key == 'instruction' and isinstance(fields.get('input'), str) and fields['input'].strip():
                    prompt += '\n\n' + fields['input']
                break
    if prompt is None:
        for key in ('messages', 'conversations'):
            if isinstance(fields.get(key), list):
                users = [item for item in fields[key] if isinstance(item, dict) and item.get('role', item.get('from')) in ('user', 'human')]
                if len(users) == 1:
                    prompt = users[0].get('content', users[0].get('value'))
                    break
    if not isinstance(prompt, str) or not prompt.strip():
        return None, None
    try:
        from .prepare_verified_math import scalar_reference
    except ImportError:
        from prepare_verified_math import scalar_reference
    for key in ('expected_answer', 'gold_answer', 'final_answer', 'answer', 'target'):
        value = fields.get(key)
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            value = str(value)
            if '####' in value:
                value = value.rsplit('####', 1)[-1].strip()
            number = scalar_reference(value)
            if number is not None:
                return prompt, str(number)
    return prompt, None


def public_snapshot(manifest):
    rows = [{key: value for key, value in source.items() if key in PUBLIC_FIELDS}
            for source in manifest['sources']]
    imported = [row for row in rows if row.get('status') == 'sample_imported']
    return {'schema_version': SCHEMA_VERSION, 'updated_at_utc': now(), 'run_id': manifest['run_id'],
            'stage': manifest['stage'], 'target_imported_datasets': manifest['target_imported_datasets'],
            'registered_sources': len(rows), 'metadata_reviewed_sources': sum(bool(row.get('metadata_reviewed')) for row in rows),
            'actually_imported_sources': len(imported), 'actually_imported_families': len({row['family'] for row in imported}),
            'sample_rows_imported': sum(row.get('sample_rows', 0) for row in imported),
            'numeric_reference_prompts': sum(row.get('numeric_reference_prompts', 0) for row in imported),
            'training_ready_examples': 0, 'new_teacher_calls': 0, 'gpu_jobs_launched': 0,
            'sources': rows,
            'interpretation': 'Imported means actual bounded training-split rows were cached. Numeric-reference prompts still require source/quality review and a controlled teacher pipeline before training. Mixed-domain sources need their own adapters/scorers.',
            'limitations': ['Repository count is not independent data-family count; related augmentations/annotations are labelled.',
                'Only small seeded samples were imported, not entire datasets.',
                'HF train labels and upstream claims do not establish complete benchmark decontamination.',
                'No official evaluation split was fetched. Public inventory contains no raw questions, answers or reasoning.',
                'Existing pilot/training pools and frozen experiments remain unchanged.']}


def import_one(source, folder, http, dedup, sample_rows):
    repo = source['repo']
    out = folder / 'sources' / repo.replace('/', '__')
    out.mkdir(parents=True, exist_ok=True)
    result = {'repo': repo, 'family': source['family'], 'domain': source['domain'],
              'url': f'https://huggingface.co/datasets/{repo}', 'status': 'inspecting',
              'provenance_note': source['provenance'], 'metadata_reviewed': False,
              'sample_rows': 0, 'untruncated_rows': 0, 'numeric_reference_prompts': 0,
              'duplicate_prompts': 0, 'raw_bytes': 0}
    try:
        body, meta = http.get(f'https://huggingface.co/api/datasets/{quote(repo, safe="/")}', out / 'repository.json')
        info = json.loads(body)
        revision = info.get('sha')
        if not isinstance(revision, str) or not re.fullmatch(r'[0-9a-f]{40}', revision):
            raise ValueError('Repository returned no immutable revision')
        result.update(metadata_reviewed=True, revision=revision,
                      license_listed=(info.get('cardData') or {}).get('license', 'not specified in metadata'))
        result['license_metadata_status'] = ('unspecified' if result['license_listed'] == 'not specified in metadata'
                                              else 'listed; terms not interpreted')
        write(out / 'source_identity.json', {'repo': repo, 'revision': revision, 'repository_sha256': meta['sha256']})
        try:
            http.get(f'https://huggingface.co/datasets/{repo}/resolve/{revision}/README.md', out / 'README.md', max_bytes=256 * 1024)
            result['card_saved'] = True
        except (urllib.error.HTTPError, DownloadLimit) as error:
            result['card_saved'] = False
            append_event(folder, {'event': 'card_unavailable', 'repo': repo, 'error_type': type(error).__name__, 'http_status': getattr(error, 'code', None)})
        splits_url = 'https://datasets-server.huggingface.co/splits?' + urlencode({'dataset': repo})
        body, _ = http.get(splits_url, out / 'splits.json', revision=revision)
        selected = choose_train_split(source, json.loads(body))
        if selected is None:
            result.update(status='no_permitted_training_split', limitation='Metadata available; no approved training split imported')
            return result
        result.update(config=selected['config'], split=selected['split'])
        # /rows itself is authoritative for total count; this small metadata row
        # is included in the actual sample rather than discarded as metadata.
        first_url = 'https://datasets-server.huggingface.co/rows?' + urlencode({'dataset': repo, 'config': selected['config'], 'split': selected['split'], 'offset': 0, 'length': min(4, sample_rows)})
        body, blockmeta = http.get(first_url, out / 'rows_000000.json', revision=revision)
        first = json.loads(body)
        # HF documents partial:true as limited DATASET coverage for large
        # collections, not truncation of returned /rows records. Keep that
        # limitation explicit; individual truncated_cells are still rejected.
        result['viewer_partial_coverage'] = check_rows_coverage(first)
        total = first['num_rows_total']
        wrappers = list(first['rows'])
        raw_blocks = [blockmeta]
        if sample_rows > len(wrappers) and total > len(wrappers):
            remaining = min(sample_rows - len(wrappers), total - len(wrappers))
            # The first block is a fixed anchor; the second block is seeded.
            source_seed = SEED ^ int(digest(repo.encode())[:8], 16)
            offset = random.Random(source_seed).randint(len(wrappers), max(len(wrappers), total - remaining))
            url = 'https://datasets-server.huggingface.co/rows?' + urlencode({'dataset': repo, 'config': selected['config'], 'split': selected['split'], 'offset': offset, 'length': remaining})
            try:
                body, blockmeta = http.get(url, out / f'rows_{offset:06d}.json', revision=revision)
                second = json.loads(body)
                check_rows_coverage(second, expected_total=total, expected_partial=first['partial'])
                wrappers.extend(second['rows'])
                raw_blocks.append(blockmeta)
            except (urllib.error.HTTPError, DownloadLimit) as error:
                # The first real rows remain a valid, explicitly smaller import.
                append_event(folder, {'event': 'second_sample_block_unavailable', 'repo': repo,
                                      'error_type': type(error).__name__, 'http_status': getattr(error, 'code', None)})
                result['sampling_note'] = 'Second bounded block unavailable; count reflects only actual first-block rows'
        seen = set()
        adapted = []
        for wrapper in wrappers:
            index = wrapper['row_idx']
            if index in seen:
                continue
            seen.add(index)
            result['sample_rows'] += 1
            if wrapper.get('truncated_cells'):
                continue
            result['untruncated_rows'] += 1
            prompt, answer = prompt_and_reference(wrapper['row'])
            # Logical/science/code records are imported raw, not forced into a
            # numeric task just because a numeric label happens to exist.
            if not prompt or answer is None or source['domain'] not in ('numeric_math', 'symbolic_math', 'multilingual_math'):
                continue
            record = {'id': f'hf:{repo}:{revision}:{selected["config"]}:{selected["split"]}:{index}',
                'prompt': prompt, 'gold_answer': answer, 'source': repo, 'source_split': 'train',
                'hf_split': selected['split'], 'source_revision': revision, 'source_config': selected['config'],
                'source_family': source['family'], 'task_domain': source['domain'],
                'source_row_sha256': digest(canonical(wrapper['row']).encode('utf-8')),
                'teacher_generated': False, 'teacher_provenance': 'No new teaching target generated; raw source answers remain privately preserved',
                'training_ready': False, 'reference_verification': 'Scalar parse only; source correctness is not independently verified',
                'license_listed': result['license_listed']}
            overlap = dedup.match(record)
            if overlap:
                result['duplicate_prompts'] += 1
                continue
            dedup.add(record)
            adapted.append(record)
        raw_content = b''.join((canonical(row) + '\n').encode('utf-8') for row in wrappers)
        (out / 'raw_rows.jsonl').write_bytes(raw_content)
        (out / 'numeric_prompts.jsonl').write_text(''.join(canonical(row) + '\n' for row in adapted), encoding='utf-8')
        result.update(status='sample_imported', raw_bytes=sum(block['bytes'] for block in raw_blocks),
                      raw_sha256=digest(raw_content), numeric_reference_prompts=len(adapted),
                      limitation='Bounded raw training sample only; source/family overlap and reference correctness remain to be reviewed')
        write(out / 'manifest.json', dict(result, blocks=raw_blocks, source_train_rows=total,
                                        imported_at_utc=now(), teacher_calls=0, gpu_jobs=0))
    except Exception as error:
        result.update(status='import_failed', error_type=type(error).__name__)
        if isinstance(error, urllib.error.HTTPError):
            result['http_status'] = error.code
        # No credential-bearing URLs or errors are possible with the fixed public
        # endpoints, but error text is still excluded from the public inventory.
        append_event(folder, {'event': 'source_failed', 'repo': repo, 'error_type': type(error).__name__,
                              'http_status': getattr(error, 'code', None)})
        write(out / 'failure.json', dict(result, at_utc=now()))
    return result


def run(output=RUN, public=PUBLIC, *, target=40, sample_rows=8, max_seconds=1500,
        offline=False, registry=REGISTRY, inherit_from=None):
    output, public = Path(output).resolve(), Path(public).resolve()
    if not output.is_relative_to((ROOT / 'runs').resolve()) or public != PUBLIC.resolve():
        raise ValueError('Only ignored run artifacts and the explicit sanitized inventory path are permitted')
    if not 1 <= target <= 40 or not 1 <= sample_rows <= 8 or not 1 <= max_seconds <= 1800:
        raise ValueError('Use <=40 imports, <=8 rows/source and <=1800 seconds')
    registry = Path(registry).resolve()
    if not registry.is_relative_to(ROOT) or registry.suffix != '.json':
        raise ValueError('Registry must be a local cloud JSON artifact')
    registry_raw = registry.read_bytes()
    sources = json.loads(registry_raw)['sources']
    if len(sources) > 64 or len({source['repo'] for source in sources}) != len(sources):
        raise ValueError('Registry needs <=64 distinct repository identities')
    if any(not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', source['repo']) for source in sources):
        raise ValueError('Invalid registry repository identity')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'sources').mkdir(exist_ok=True)
    public.parent.mkdir(parents=True, exist_ok=True)
    lock = output / 'importer.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, str(os.getpid()).encode('ascii'))
        os.fsync(fd)
        settings = {'registry_sha256': digest(registry_raw), 'target_imported_datasets': target,
                    'sample_rows_per_source': sample_rows, 'seed': SEED, 'max_total_source_bytes': MAX_TOTAL_BYTES,
                    'max_response_bytes': MAX_RESPONSE_BYTES, 'no_evaluation_splits': True,
                    'new_teacher_calls': 0, 'gpu_jobs': 0}
        inherited = None
        if inherit_from:
            inherit_from = Path(inherit_from).resolve()
            if not inherit_from.is_relative_to((ROOT / 'runs').resolve()) or inherit_from == output:
                raise ValueError('Inherited artifacts must be a different local ignored run')
            if (inherit_from / 'importer.lock').exists():
                raise RuntimeError('Do not inherit a still-active import run')
            inherited_raw = (inherit_from / 'manifest.json').read_bytes()
            inherited = json.loads(inherited_raw)
            settings.update(inherited_run=str(inherit_from), inherited_manifest_sha256=digest(inherited_raw))
        if (output / 'plan.json').exists():
            if json.loads((output / 'plan.json').read_text()) != settings:
                raise RuntimeError('Frozen registry/import settings differ')
        else:
            write(output / 'plan.json', settings)
        path = output / 'manifest.json'
        fresh = not path.exists()
        manifest = json.loads(path.read_text()) if path.exists() else {
            'schema_version': SCHEMA_VERSION, 'run_id': output.name, 'stage': 'importing',
            'created_at_utc': now(), 'target_imported_datasets': target,
            'sources': [{key: source[key] for key in ('repo', 'family', 'domain')} | {'status': 'queued'} for source in sources]}
        if fresh and inherited:
            old_sources = {row['repo']: row for row in inherited['sources']}
            for index, source in enumerate(sources):
                previous = old_sources.get(source['repo'])
                if previous is None:
                    continue
                old_folder = inherit_from / 'sources' / source['repo'].replace('/', '__')
                new_folder = output / 'sources' / source['repo'].replace('/', '__')
                if old_folder.exists():
                    shutil.copytree(old_folder, new_folder, dirs_exist_ok=True)
                manifest['sources'][index] = dict(previous)
                if previous['status'] != 'sample_imported' and source.get('recovery_reason'):
                    # Requeue only a concrete documented format fix, never
                    # gated/auth failures or unchanged network-error attempts.
                    manifest['sources'][index] = {key: source[key] for key in ('repo', 'family', 'domain')} | {
                        'status': 'queued', 'prior_status': previous['status'],
                        'recovery_reason': source['recovery_reason']}
            manifest.update(inherited_run=inherit_from.name,
                            inherited_manifest_sha256=settings['inherited_manifest_sha256'])
            append_event(output, {'event': 'inherited_immutable_run', 'source_run': inherit_from.name,
                                  'source_manifest_sha256': settings['inherited_manifest_sha256']})
        try:
            from .prepare_verified_math import load_exclusions, EXCLUSION_PATHS, Deduplicator
        except ImportError:
            from prepare_verified_math import load_exclusions, EXCLUSION_PATHS, Deduplicator
        extra = (ROOT.parent / 'ranking/runs/gsm8k_preview_128_seed42/target_queries.jsonl',
                 ROOT / 'runs/student_valuation_pool512_v1/candidates.jsonl')
        exclusions, hashes = load_exclusions((*EXCLUSION_PATHS, *extra))
        dedup = Deduplicator(exclusions)
        manifest['existing_exclusion_sources'] = hashes
        for source in sources:
            adapted_path = output / 'sources' / source['repo'].replace('/', '__') / 'numeric_prompts.jsonl'
            if adapted_path.exists():
                for line in adapted_path.read_text(encoding='utf-8').split('\n'):
                    if line:
                        dedup.add(json.loads(line))
        started = time.monotonic()
        http = SourceHTTP(output, offline=offline, deadline=started + max_seconds)

        def checkpoint():
            manifest.update(updated_at_utc=now(), current_invocation_network_bytes=http.network_bytes,
                            current_invocation_source_bytes=http.source_bytes)
            write(path, manifest)
            write(public, public_snapshot(manifest))

        manifest['stage'] = 'importing'
        checkpoint()
        append_event(output, {'event': 'importer_started', 'pid': os.getpid(), 'offline': offline})
        for index, source in enumerate(sources):
            if sum(row.get('status') == 'sample_imported' for row in manifest['sources']) >= target:
                break
            if time.monotonic() - started >= max_seconds or http.source_bytes >= MAX_TOTAL_BYTES:
                manifest['stage'] = 'bounded_pause'
                break
            if manifest['sources'][index]['status'] != 'queued':
                continue  # Permanent failures are recorded, never blindly repeated.
            result = import_one(source, output, http, dedup, sample_rows)
            manifest['sources'][index] = result
            checkpoint()
            imported = sum(row.get('status') == 'sample_imported' for row in manifest['sources'])
            print(json.dumps({'repo': source['repo'], 'status': result['status'],
                              'actually_imported': imported, 'sample_rows': result.get('sample_rows', 0),
                              'numeric_prompts': result.get('numeric_reference_prompts', 0)}), flush=True)
        else:
            manifest['stage'] = 'completed_with_recorded_gaps'
        if sum(row.get('status') == 'sample_imported' for row in manifest['sources']) >= target:
            manifest['stage'] = 'completed'
        # A combined prompt pool is still unverified and cannot become teaching
        # data merely because 40 repositories were successfully sampled.
        combined = []
        for source in sources:
            adapted_path = output / 'sources' / source['repo'].replace('/', '__') / 'numeric_prompts.jsonl'
            if adapted_path.exists():
                combined.extend(json.loads(line) for line in adapted_path.read_text(encoding='utf-8').split('\n') if line)
        (output / 'numeric_prompt_pool.jsonl').write_text(''.join(canonical(row) + '\n' for row in combined), encoding='utf-8')
        manifest['numeric_pool_sha256'] = digest((output / 'numeric_prompt_pool.jsonl').read_bytes())
        checkpoint()
        append_event(output, {'event': 'importer_stopped', 'stage': manifest['stage'],
                              'imported': sum(row.get('status') == 'sample_imported' for row in manifest['sources'])})
        return public_snapshot(manifest)
    finally:
        os.close(fd)
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=RUN)
    parser.add_argument('--target', type=int, default=40)
    parser.add_argument('--sample-rows', type=int, default=8)
    parser.add_argument('--max-seconds', type=int, default=1500)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--registry', type=Path, default=REGISTRY)
    parser.add_argument('--inherit-from', type=Path)
    args = parser.parse_args()
    snapshot = run(args.output, target=args.target, sample_rows=args.sample_rows,
                   max_seconds=args.max_seconds, offline=args.offline,
                   registry=args.registry, inherit_from=args.inherit_from)
    print(json.dumps({key: snapshot[key] for key in ('stage', 'actually_imported_sources',
                            'sample_rows_imported', 'numeric_reference_prompts')}), flush=True)


if __name__ == '__main__':
    main()
