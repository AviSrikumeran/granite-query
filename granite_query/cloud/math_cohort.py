"""Unpaid source-specific math prompt expansion for a future controlled cohort.

The four existing arms are never read or modified. This creates references and
questions, not training targets: a separately reserved teacher stage must produce
concise complete answers and verify them before either selector receives data.
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
import sys
import time
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
if __package__:
    from .import_hf_sources import SourceHTTP, DownloadLimit, check_rows_coverage
    from .prepare_verified_math import load_exclusions, EXCLUSION_PATHS, Deduplicator, scalar_reference
    from .matched_teacher import PREFIX
else:
    from cloud.import_hf_sources import SourceHTTP, DownloadLimit, check_rows_coverage
    from cloud.prepare_verified_math import load_exclusions, EXCLUSION_PATHS, Deduplicator, scalar_reference
    from cloud.matched_teacher import PREFIX

RUN = ROOT / 'runs/math_source_cohort1800_v1'
PUBLIC = ROOT.parents[1] / 'progress/MATH_COHORT.json'
SOURCE_RUN = ROOT / 'runs/hf_training_sources_40_v2/sources'
SEED = 20261107
MAX_BYTES = 64 * 1024**2
MAX_BLOCK_BYTES = 2 * 1024**2
QUOTA = 600
TEMPLATE_CAP = 5
SOURCES = [
    {'repo': 'ChilleD/SVAMP', 'family': 'svamp-original', 'revision': '5e0bf1e5e7c0e9c4bc39180d224f41f3f801b7ef',
     'config': 'default', 'split': 'train', 'rows': 700, 'max_examined': 700,
     'max_source_bytes': 8 * 1024**2, 'reference_type': 'human_dataset_answer',
     'reference_limitation': 'Provided SVAMP answer, parsed locally; not independently re-solved in this unpaid stage'},
    {'repo': 'math-ai/TemplateGSM', 'family': 'templategsm-generated', 'revision': '0c8ed6b60fea0a84f25ddb1b8b761db695df2e19',
     'config': 'templategsm-1000-1k', 'split': 'train', 'rows': 1000000, 'max_examined': 12000,
     'max_source_bytes': 24 * 1024**2, 'reference_type': 'procedurally_generated_result',
     'reference_limitation': 'Upstream claims programmatic verification; no downloaded solution code is executed here'},
    {'repo': 'nvidia/OpenMathInstruct-2', 'family': 'nvidia-openmath-instruct', 'revision': '469216e3f46f4dacf476b382e192485ea51a143e',
     'config': 'default', 'split': 'train_1M', 'rows': 1000000, 'max_examined': 6000,
     'max_source_bytes': 32 * 1024**2, 'reference_type': 'synthetic_majority_vote_answer',
     'reference_limitation': 'Only augmented_gsm8k prompts; expected_answer is a generated majority-vote reference, not independent human gold'},
]


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def write_rows(path, rows):
    raw = ''.join(canonical(row) + '\n' for row in rows).encode('utf-8')
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_bytes(raw)
    temporary.replace(path)
    return digest(raw)


def event(folder, kind, **details):
    with (folder / 'events.jsonl').open('a', encoding='utf-8') as handle:
        handle.write(canonical(dict(at_utc=now(), event=kind, **details)) + '\n')
        handle.flush()
        os.fsync(handle.fileno())


def offsets(source):
    # Shuffled, non-overlapping 50-row blocks. Template blocks are scattered
    # across template groups; the explicit per-template cap prevents domination.
    blocks = list(range(0, source['rows'], 50))
    source_seed = SEED ^ int(digest(source['repo'].encode())[:8], 16)
    random.Random(source_seed).shuffle(blocks)
    return blocks[:(source['max_examined'] + 49) // 50]


def adapt(source, wrapper, forbidden_templates):
    row = wrapper.get('row', {})
    if wrapper.get('truncated_cells'):
        return None, 'server_truncated_cells'
    repo = source['repo']
    template = None
    if repo == 'ChilleD/SVAMP':
        if not all(isinstance(row.get(key), str) and row[key].strip() for key in ('Body', 'Question')):
            return None, 'missing_svamp_context'
        prompt, answer = row['Body'] + '\n\n' + row['Question'], row.get('Answer')
    elif repo == 'math-ai/TemplateGSM':
        prompt, answer, template = row.get('problem'), row.get('result'), row.get('template_id')
        if not isinstance(template, int):
            return None, 'missing_template_identity'
        if 'gsm8k-train' not in str(row.get('source', '')).casefold():
            return None, 'unconfirmed_training_template_origin'
        if template in forbidden_templates:
            return None, 'template_id_matches_excluded_gsm8k_id'
    elif repo == 'nvidia/OpenMathInstruct-2':
        if row.get('problem_source') != 'augmented_gsm8k':
            return None, 'not_augmented_gsm8k'
        prompt, answer = row.get('problem'), row.get('expected_answer')
    else:
        raise ValueError('No source-specific adapter')
    if not isinstance(prompt, str) or not prompt.strip():
        return None, 'missing_prompt'
    if isinstance(answer, bool) or not isinstance(answer, (str, int, float)):
        return None, 'non_scalar_reference_type'
    number = scalar_reference(str(answer))
    if number is None:
        return None, 'non_plain_numeric_reference'
    if re.search(r'!\[|<img|\\includegraphics|\[asy\]|\b(?:prove|proof|show that|which of the following)\b', prompt, re.I):
        return None, 'unsupported_prompt_format'
    user_bytes = len((PREFIX + prompt).encode('utf-8'))
    if user_bytes > 1800:
        return None, 'prospective_teacher_input_byte_bound'
    index = wrapper.get('row_idx')
    if not isinstance(index, int) or not 0 <= index < source['rows']:
        return None, 'invalid_source_index'
    candidate = {'id': f'hfmath:{repo}:{source["revision"]}:{source["config"]}:{source["split"]}:{index}',
        'prompt': prompt, 'gold_answer': str(number), 'source': repo, 'source_family': source['family'],
        'source_revision': source['revision'], 'source_config': source['config'], 'source_split': 'train',
        'hf_split': source['split'], 'row_idx': index, 'template_id': template,
        'reference_type': source['reference_type'], 'reference_limitation': source['reference_limitation'],
        'reference_verified_by_this_stage': False, 'teacher_generated': False, 'training_ready': False,
        'source_row_sha256': digest(canonical(row).encode('utf-8')),
        'prompt_sha256': digest(prompt.encode('utf-8')), 'prospective_teacher_user_utf8_bytes': user_bytes}
    return candidate, 'adapter_eligible'


def public_snapshot(manifest):
    allow = ('repo', 'family', 'revision', 'config', 'split', 'reference_type', 'reference_limitation',
             'status', 'examined_rows', 'accepted_prompts', 'bytes_cached', 'rejections',
             'observed_problem_sources', 'unique_templates', 'template_cap', 'error_type',
             'viewer_partial_coverage', 'license_listed', 'license_metadata_status')
    return {'schema_version': 1, 'run_id': manifest['run_id'], 'stage': manifest['stage'],
        'updated_at_utc': now(), 'max_prompts_per_source': QUOTA, 'max_prompts_total': 3 * QUOTA,
        'actual_prompts': manifest['actual_prompts'],
        'sources': [{key: value for key, value in source.items() if key in allow} for source in manifest['sources']],
        'training_ready_examples': 0, 'new_teacher_calls': 0, 'new_gpu_jobs': 0,
        'official_evaluation_splits_accessed': False,
        'purpose': 'Prospective shared pool for a future controlled 131072-supervised-token comparison; feasibility and funds must be checked after teacher verification',
        'next_stage': 'Separately reserved concise DeepSeek-V4 targets, strict numeric/completion/context checks, then matched selectors from the same frozen eligible pool',
        'limitations': ['Forty-source coverage samples are not blindly mixed into numeric training.',
            'Source references have different origins and uncertainty; majority-vote references are not independent gold.',
            'No provided teacher traces are copied or truncated into targets.',
            'Template-ID exclusion is a conservative lineage guard, not proof of full semantic decontamination.',
            'Source and template quotas must remain controlled when comparing selection policies.',
            'The existing four frozen arms and their prepared pool remain unchanged.']}


def prepare(output=RUN, max_seconds=1500, offline=False):
    output = Path(output).resolve()
    if not output.is_relative_to((ROOT / 'runs').resolve()) or not 1 <= max_seconds <= 1800:
        raise ValueError('Require ignored run artifacts and <=1800 seconds')
    extra = (ROOT.parent / 'ranking/runs/gsm8k_preview_128_seed42/target_queries.jsonl',
             ROOT / 'runs/student_valuation_pool512_v1/candidates.jsonl')
    exclusions, exclusion_sources = load_exclusions((*EXCLUSION_PATHS, *extra))
    forbidden_templates = {int(match.group(1)) for row in exclusions
        if (match := re.fullmatch(r'gsm8k:train:(\d{5})', row['id']))}
    source_identities = []
    for source in SOURCES:
        path = SOURCE_RUN / source['repo'].replace('/', '__') / 'manifest.json'
        raw = path.read_bytes()
        old = json.loads(raw)
        if any(old[key] != source[key] for key in ('repo', 'revision', 'config', 'split')):
            raise ValueError('Source differs from the pinned, actually imported dataset identity')
        source_identities.append({'repo': source['repo'], 'manifest_sha256': digest(raw),
                                  'license_listed': old['license_listed']})
    plan = {'schema_version': 1, 'run_id': output.name, 'seed': SEED, 'sources': SOURCES,
            'source_import_identities': source_identities, 'quota_per_source': QUOTA,
            'template_cap': TEMPLATE_CAP, 'exclusions': exclusion_sources,
            'excluded_unique_ids': len({row['id'] for row in exclusions}),
            'conservative_forbidden_template_ids': sorted(forbidden_templates),
            'max_total_source_bytes': MAX_BYTES, 'max_block_bytes': MAX_BLOCK_BYTES,
            'block_rows': 50, 'prospective_teacher_user_bytes_max': 1800,
            'deduplication': 'Exact normalized prompts plus exhaustive 5-token-shingle Jaccard>=0.8 with identical math-fact signature; exclude previous teachers/probes/development and the entire new512 question pool',
            'source_reference_policy': 'Human/procedural/synthetic majority origins remain separate; scalar parse is not teacher correctness verification',
            'official_test_accessed': False, 'teacher_calls': 0, 'gpu_jobs': 0,
            'selection_requirement': 'Both arms must use the same verified pool and declared per-source token quotas; source-mixture changes require a separate hypothesis',
            'prospective_supervised_tokens_per_arm': 131072,
            'prospective_token_budget_is_not_launched_or_guaranteed_feasible': True}
    output.mkdir(parents=True, exist_ok=True)
    (output / 'sources').mkdir(exist_ok=True)
    lock = output / 'cohort.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, str(os.getpid()).encode('ascii'))
        os.fsync(fd)
        if (output / 'plan.json').exists():
            if json.loads((output / 'plan.json').read_text(encoding='utf-8')) != plan:
                raise RuntimeError('Immutable cohort plan or exclusions changed')
        else:
            write(output / 'plan.json', plan)
        if (output / 'manifest.json').exists():
            with (output / 'manifest_history.jsonl').open('a', encoding='utf-8') as history:
                history.write(canonical(json.loads((output / 'manifest.json').read_text(encoding='utf-8'))) + '\n')
        manifest = {'schema_version': 1, 'run_id': output.name, 'created_at_utc': now(),
                    'stage': 'preparing', 'actual_prompts': 0, 'sources': []}
        candidates, decisions = [], []
        dedup = Deduplicator(exclusions)
        started = time.monotonic()
        http = SourceHTTP(output, max_bytes=MAX_BYTES, offline=offline, deadline=started + max_seconds)
        event(output, 'cohort_preparation_started', pid=os.getpid(), offline=offline)

        def checkpoint():
            manifest['actual_prompts'] = len(candidates)
            manifest['candidates_sha256'] = write_rows(output / 'candidates.jsonl', sorted(candidates, key=lambda row: row['id']))
            write_rows(output / 'decisions.jsonl', decisions)
            manifest.update(updated_at_utc=now(), total_cached_source_bytes=http.source_bytes,
                            current_invocation_network_bytes=http.network_bytes)
            write(output / 'manifest.json', manifest)
            write(PUBLIC, public_snapshot(manifest))

        for source, identity in zip(SOURCES, source_identities):
            stats = {key: source[key] for key in ('repo', 'family', 'revision', 'config', 'split', 'reference_type', 'reference_limitation')}
            stats.update(status='queued', examined_rows=0, accepted_prompts=0, bytes_cached=0,
                         rejections={}, observed_problem_sources={}, unique_templates=0,
                         template_cap=TEMPLATE_CAP if source['repo'] == 'math-ai/TemplateGSM' else None,
                         license_listed=identity['license_listed'],
                         license_metadata_status='listed; terms not interpreted')
            manifest['sources'].append(stats)
            rejected, category_counts, template_counts, blocks = Counter(), Counter(), Counter(), []
            folder = output / 'sources' / source['repo'].replace('/', '__')
            folder.mkdir(exist_ok=True)
            stats['status'] = 'scanning'
            checkpoint()
            try:
                for offset in offsets(source):
                    if stats['accepted_prompts'] >= QUOTA:
                        stats['status'] = 'quota_reached'
                        break
                    if stats['bytes_cached'] >= source['max_source_bytes'] or time.monotonic() - started >= max_seconds:
                        stats['status'] = 'bounded_scan_exhausted'
                        break
                    length = min(50, source['rows'] - offset)
                    url = 'https://datasets-server.huggingface.co/rows?' + urlencode({
                        'dataset': source['repo'], 'config': source['config'], 'split': source['split'],
                        'offset': offset, 'length': length})
                    body, metadata = http.get(url, folder / f'rows_{offset:07d}.json',
                                              revision=source['revision'], max_bytes=min(MAX_BLOCK_BYTES, source['max_source_bytes'] - stats['bytes_cached']))
                    payload = json.loads(body)
                    check_rows_coverage(payload, expected_total=source['rows'])
                    if [row['row_idx'] for row in payload['rows']] != list(range(offset, offset + length)):
                        raise RuntimeError('Source returned different row positions than requested')
                    stats['viewer_partial_coverage'] = payload['partial']
                    stats['bytes_cached'] += len(body)
                    blocks.append(metadata)
                    for wrapper in payload['rows']:
                        stats['examined_rows'] += 1
                        raw = wrapper['row']
                        if source['repo'] == 'nvidia/OpenMathInstruct-2':
                            category_counts[str(raw.get('problem_source'))] += 1
                        candidate, reason = adapt(source, wrapper, forbidden_templates)
                        if candidate is not None:
                            template = candidate['template_id']
                            if template is not None and template_counts[template] >= TEMPLATE_CAP:
                                candidate, reason = None, 'template_quota'
                            elif stats['accepted_prompts'] >= QUOTA:
                                candidate, reason = None, 'source_quota'
                            else:
                                overlap = dedup.match(candidate)
                                if overlap:
                                    candidate, reason = None, overlap['reason']
                        if candidate is not None:
                            candidates.append(candidate)
                            dedup.add(candidate)
                            stats['accepted_prompts'] += 1
                            if candidate['template_id'] is not None:
                                template_counts[candidate['template_id']] += 1
                        else:
                            rejected[reason] += 1
                        decisions.append({'repo': source['repo'], 'row_idx': wrapper['row_idx'],
                                          'reason': 'accepted' if candidate else reason,
                                          'raw_block_sha256': metadata['sha256']})
                    stats.update(rejections=dict(rejected), observed_problem_sources=dict(category_counts),
                                 unique_templates=len(template_counts))
                    write(folder / 'manifest.json', dict(stats, raw_blocks=blocks, template_counts=dict(template_counts)))
                    checkpoint()
                    print(json.dumps({'repo': source['repo'], 'examined': stats['examined_rows'],
                                      'accepted': stats['accepted_prompts'], 'cohort_prompts': len(candidates)}), flush=True)
                else:
                    stats['status'] = 'bounded_scan_exhausted'
                if stats['accepted_prompts'] >= QUOTA:
                    stats['status'] = 'quota_reached'
            except Exception as error:
                stats.update(status='stopped', error_type=type(error).__name__)
                event(output, 'source_stopped', repo=source['repo'], error_type=type(error).__name__)
            write(folder / 'manifest.json', dict(stats, raw_blocks=blocks, template_counts=dict(template_counts)))
            checkpoint()
        manifest['stage'] = 'prepared' if all(source['status'] == 'quota_reached' for source in manifest['sources']) else 'prepared_with_bounded_gaps'
        checkpoint()
        event(output, 'cohort_preparation_completed', actual_prompts=len(candidates), stage=manifest['stage'])
        return public_snapshot(manifest)
    finally:
        os.close(fd)
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=RUN)
    parser.add_argument('--max-seconds', type=int, default=1500)
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    result = prepare(args.output, args.max_seconds, args.offline)
    print(json.dumps({key: result[key] for key in ('run_id', 'stage', 'actual_prompts')}), flush=True)


if __name__ == '__main__':
    main()
