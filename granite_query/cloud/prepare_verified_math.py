"""Prepare a small, reproducible OpenR1 candidate pool without parquet downloads.

This is an unpaid, local preparation step. It reads ONLY explicitly allowlisted
existing training/development files and the public dataset's training split.
The datasets-server serves its current revision; every block's x-revision must
equal the pinned commit or the run stops. Cached raw responses make replay
independent of later server availability. No response is shortened or rewritten.

Run from the workspace with the project Python:
  granite_query/.venv-modal/Scripts/python.exe -m cloud.prepare_verified_math
with the working directory set to granite_query (or set PYTHONPATH accordingly).
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import random
import re
import sys
import time
import unicodedata
from urllib.parse import urlencode
import urllib.request


ROOT = Path(__file__).resolve().parent
DATASET = 'open-r1/OpenR1-Math-220k'
REVISION = 'e4e141ec9dea9f8326f4d347be56105859b2bd68'
CONFIG = 'default'
SPLIT = 'train'
SEED = 20261103
DEFAULT_OUTPUT = ROOT / 'runs/openr1_short_numeric_seed20261103_v1'
MODEL = 'ibm-granite/granite-4.2-3b'
MODEL_REVISION = '4e9c275e232f10211ec88644d106a1f6a1b60e06'
EXCLUSION_PATHS = (
    ROOT / 'runs/ranked_random_32_seed42_v1/candidates.jsonl',
    ROOT / 'runs/ranked_random_32_seed42_v1/development.jsonl',
    ROOT / 'runs/matched_eval64_v1/development.jsonl',
    ROOT / 'runs/deepseek32b_pilot16_seed42/requests.jsonl',
)
SOURCE_URL = f'https://huggingface.co/datasets/{DATASET}/tree/{REVISION}'
PROMPT_PREFIX = ('Solve the math problem. Explain only the necessary calculation '
                 'steps concisely. Finish with #### followed by the numeric final answer.\n\n')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(data) -> bytes:
    return (json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')


def write_json(path: Path, data) -> None:
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temp.replace(path)


def numeric(text: str) -> Decimal | None:
    value = str(text).strip().replace('−', '-')
    # Restrict to scalar numbers. No symbolic evaluation or answer guessing.
    if not re.fullmatch(r'[+-]?(?:(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d*)?|\.\d+)', value):
        return None
    return Decimal(value.replace(',', ''))


def scalar_reference(text: str) -> Decimal | None:
    value = str(text).strip()
    if value.startswith('$') and value.endswith('$'):
        value = value[1:-1].strip()
    if value.startswith(r'\boxed{') and value.endswith('}'):
        value = value[7:-1].strip()
    return numeric(value)


def final_number(response: str) -> Decimal | None:
    # The last explicit final-answer marker is used, never the last free number.
    boxes = list(re.finditer(r'\\boxed\{([^{}]*)\}', response))
    if boxes:
        return scalar_reference(boxes[-1].group(1))
    if '####' in response:
        return numeric(response.rsplit('####', 1)[-1])
    return None


def question_tokens(text: str) -> list[str]:
    value = unicodedata.normalize('NFKC', text).casefold()
    value = value.translate(str.maketrans({'−': '-', '×': '*', '÷': '/'}))
    return re.findall(r'\d+(?:[.,]\d+)*|[^\W\d_]+|[+*/=<>%$^-]', value, flags=re.UNICODE)


def normalized(text: str) -> str:
    return ' '.join(question_tokens(text))


def math_signature(text: str) -> tuple[str, ...]:
    return tuple(t for t in question_tokens(text) if any(c.isdigit() for c in t)
                 or t in {'+', '-', '*', '/', '=', '<', '>', '%', '$', '^'})


def shingles(text: str, width: int = 5) -> set[str]:
    tokens = question_tokens(text)
    if len(tokens) < width:
        return {' '.join(tokens)} if tokens else set()
    return {' '.join(tokens[i:i + width]) for i in range(len(tokens) - width + 1)}


class Deduplicator:
    """Exhaustive bounded-pool comparisons; no approximate index can miss pairs."""
    def __init__(self, exclusions: list[dict], threshold: float = 0.8):
        self.threshold = threshold
        self.rows = []
        self.exact = {}
        for row in exclusions:
            self.add(row, 'existing_training_or_development')

    def add(self, row: dict, role: str = 'candidate') -> None:
        text = row['prompt']
        self.rows.append((row['id'], math_signature(text), shingles(text), role))
        self.exact.setdefault(normalized(text), (row['id'], role))

    def match(self, row: dict) -> dict | None:
        key = normalized(row['prompt'])
        if key in self.exact:
            other_id, role = self.exact[key]
            return {'reason': role + '_exact_overlap', 'matched_id': other_id, 'jaccard': 1.0}
        parts, signature = shingles(row['prompt']), math_signature(row['prompt'])
        if not parts:
            return {'reason': 'empty_normalized_prompt'}
        for other_id, other_signature, other_parts, role in self.rows:
            if signature != other_signature:
                continue
            union = parts | other_parts
            score = len(parts & other_parts) / len(union) if union else 0.0
            if score >= self.threshold:
                return {'reason': role + '_near_overlap', 'matched_id': other_id, 'jaccard': score}
        return None


def load_exclusions(paths=EXCLUSION_PATHS) -> tuple[list[dict], list[dict]]:
    """The default is an explicit allowlist, never a glob of dataset/test files."""
    rows, sources = [], []
    for path in paths:
        path = Path(path)
        if re.search(r'(^|[_.-])test([_.-]|$)', path.name, re.I):
            raise ValueError('Official-test access is forbidden in preparation')
        raw = path.read_bytes()
        records = [json.loads(line) for line in raw.decode('utf-8-sig').splitlines() if line.strip()]
        for row in records:
            # The original 16-row request artifact predates source_split but its
            # GSM8K ID encodes the training split. Reject any conflicting label.
            split = row.get('source_split')
            encoded_train = re.fullmatch(r'gsm8k:train:\d{5}', str(row.get('id', ''))) is not None
            if (split != 'train' and not (split is None and encoded_train)) or ':test:' in row.get('id', ''):
                raise ValueError('Exclusion inputs must contain training-split rows only')
            if not isinstance(row.get('prompt'), str) or not row['prompt'].strip():
                raise ValueError('Exclusion input has no usable prompt')
            # Keep only prompt/id in memory; reference answers do not affect dedup.
            rows.append({'id': row['id'], 'prompt': row['prompt']})
        sources.append({'path': str(path.resolve()), 'sha256': digest(raw), 'rows': len(records)})
    return rows, sources


class BoundedHTTP:
    def __init__(self, max_total_bytes: int, max_block_bytes: int):
        self.max_total_bytes = max_total_bytes
        self.max_block_bytes = max_block_bytes
        self.downloaded_bytes = 0
        self.last_request_time = None

    def get(self, url: str, *, revision: str | None = None) -> tuple[bytes, dict]:
        if not url.startswith(('https://datasets-server.huggingface.co/', 'https://huggingface.co/')):
            raise ValueError('Only explicitly public Hugging Face URLs are permitted')
        available = min(self.max_block_bytes, self.max_total_bytes - self.downloaded_bytes)
        if available <= 0:
            raise RuntimeError('Download byte budget exhausted')
        request = urllib.request.Request(url, headers={'User-Agent': 'GraniteQuery-bounded-research/1.0',
                                                      'Accept-Encoding': 'identity'})
        if self.last_request_time is not None:
            time.sleep(max(0.0, 3.0 - (time.monotonic() - self.last_request_time)))
        self.last_request_time = time.monotonic()
        with urllib.request.urlopen(request, timeout=45) as response:
            headers = {k.casefold(): v for k, v in response.headers.items()}
            if revision is not None and headers.get('x-revision') != revision:
                raise RuntimeError('Dataset-server revision mismatch; refusing unpinned rows')
            length = headers.get('content-length')
            if length and int(length) > available:
                raise RuntimeError('Response exceeds remaining per-block or total byte limit')
            chunks = []
            while True:
                chunk = response.read(min(65536, available - sum(map(len, chunks)) + 1))
                if not chunk:
                    break
                chunks.append(chunk)
                self.downloaded_bytes += len(chunk)
                if sum(map(len, chunks)) > available:
                    raise RuntimeError('Response exceeded byte limit while reading')
            return b''.join(chunks), headers


def block_url(offset: int, length: int) -> str:
    return 'https://datasets-server.huggingface.co/rows?' + urlencode(
        {'dataset': DATASET, 'config': CONFIG, 'split': SPLIT, 'offset': offset, 'length': length})


class CachedSampleExhausted(RuntimeError):
    pass


def cached_block(folder: Path, http: BoundedHTTP, offset: int, length: int,
                 *, cached_only: bool = False) -> tuple[dict, dict]:
    name = f'{offset:06d}_{length:03d}'
    body_path, meta_path = folder / (name + '.json'), folder / (name + '.metadata.json')
    url = block_url(offset, length)
    if body_path.exists() or meta_path.exists():
        if not body_path.exists() or not meta_path.exists():
            raise RuntimeError('Incomplete cached block; inspect partial artifacts before retrying')
        body, meta = body_path.read_bytes(), json.loads(meta_path.read_text(encoding='utf-8'))
        if (meta.get('url') != url or meta.get('revision') != REVISION
                or meta.get('sha256') != digest(body)):
            raise RuntimeError('Cached source block hash/provenance mismatch')
        if len(body) > http.max_block_bytes:
            raise RuntimeError('Cached block exceeds per-block limit')
    else:
        if cached_only:
            raise CachedSampleExhausted('No further cached blocks; no network request attempted')
        body, headers = http.get(url, revision=REVISION)
        meta = {'url': url, 'revision': headers['x-revision'], 'sha256': digest(body),
                'bytes': len(body), 'offset': offset, 'length': length}
        body_path.write_bytes(body)
        write_json(meta_path, meta)
    payload = json.loads(body)
    if payload.get('partial') is not False:
        raise RuntimeError('Dataset-server returned partial dataset information')
    return payload, meta


def encode(row: dict, tokenizer) -> tuple[int, int]:
    prefix = tokenizer.apply_chat_template(
        [{'role': 'user', 'content': PROMPT_PREFIX + row['prompt']}], tokenize=False,
        add_generation_prompt=True, enable_thinking=False)
    prefix_ids = tokenizer(prefix, add_special_tokens=False)['input_ids']
    response_ids = tokenizer(row['response'] + tokenizer.eos_token, add_special_tokens=False)['input_ids']
    return len(prefix_ids), len(response_ids)


def eligible_row(wrapped: dict, tokenizer, *, max_response_tokens: int,
                 context_limit: int) -> tuple[dict | None, str, dict]:
    row = wrapped.get('row', {})
    stats = {'source': row.get('source'), 'problem_type': row.get('problem_type'),
             'question_type': row.get('question_type'), 'row_idx': wrapped.get('row_idx')}
    if wrapped.get('truncated_cells'):
        return None, 'server_truncated_cells', stats
    if row.get('question_type') != 'math-word-problem':
        return None, 'not_math_word_problem', stats
    prompt = row.get('problem')
    if not isinstance(prompt, str) or not prompt.strip():
        return None, 'missing_problem', stats
    # No images, graphs, choices or proof/abstract-geometry objectives in this pool.
    if re.search(r'!\[|<img|\[asy\]|\\includegraphics|(?:shown|given)\s+(?:in\s+)?(?:the\s+)?(?:figure|diagram)|'
                 r'\b(?:prove|proof|show that|multiple.choice|select all|which of the following)\b', prompt, re.I):
        return None, 'unsupported_problem_format', stats
    gold = scalar_reference(row.get('answer', ''))
    if gold is None:
        return None, 'not_scalar_numeric_reference', stats
    generations, complete, verified = (row.get('generations'), row.get('is_reasoning_complete'),
                                        row.get('correctness_math_verify'))
    if not all(isinstance(v, list) for v in (generations, complete, verified)):
        return None, 'missing_generation_verification', stats
    if not len(generations) == len(complete) == len(verified):
        return None, 'misaligned_generation_metadata', stats
    finish = row.get('finish_reasons')
    if finish is not None and (not isinstance(finish, list) or len(finish) != len(generations)):
        return None, 'misaligned_finish_metadata', stats
    # Freeze one independently eligible generation per problem. Choosing the
    # shortest verified trace is a common preparation rule, not a valued-arm score.
    possibilities, reasons, lengths = [], Counter(), []
    for i, response in enumerate(generations):
        if complete[i] is not True or verified[i] is not True:
            reasons['unverified_or_incomplete_generation'] += 1
            continue
        if finish and finish[i] not in (None, 'stop', 'eos', 'eos_token'):
            reasons['non_success_finish_reason'] += 1
            continue
        if not isinstance(response, str) or not response.strip():
            reasons['empty_generation'] += 1
            continue
        if response.count('<think>') != response.count('</think>'):
            reasons['unclosed_reasoning_tag'] += 1
            continue
        if final_number(response) != gold:
            reasons['final_scalar_mismatch_or_missing'] += 1
            continue
        prefix_tokens, response_tokens = encode({'prompt': prompt, 'response': response}, tokenizer)
        lengths.append(response_tokens)
        if response_tokens > max_response_tokens:
            reasons['response_too_long'] += 1
            continue
        if prefix_tokens + response_tokens > context_limit:
            reasons['context_too_long'] += 1
            continue
        possibilities.append((response_tokens, i, response, prefix_tokens))
    stats['generation_rejections'] = dict(reasons)
    stats['verified_response_token_lengths'] = lengths
    if not possibilities:
        return None, 'no_short_complete_verified_trace', stats
    response_tokens, index, response, prefix_tokens = min(possibilities, key=lambda v: (v[0], v[1]))
    if not row.get('uuid') or not isinstance(wrapped.get('row_idx'), int):
        return None, 'missing_source_identity', stats
    candidate = {
        'id': f'openr1:default:train:{row["uuid"]}',
        'prompt': prompt, 'response': response, 'gold_answer': str(gold),
        'source': DATASET, 'source_split': 'train', 'source_revision': REVISION,
        'source_config': CONFIG, 'original_source': row.get('source'),
        'problem_type': row.get('problem_type'), 'question_type': row.get('question_type'),
        'teacher_model': 'deepseek-ai/DeepSeek-R1',
        'teacher_revision': 'Public OpenR1 trace; original teacher weight revision unspecified',
        'eligible': True, 'verified_final_answer': True,
        'verification': {'method': 'public_math_verify_and_local_scalar_match',
                         'math_verify': True, 'complete': True,
                         'boxed_numeric_match': True, 'trace_truncated': False},
        'prompt_sha256': digest(prompt.encode('utf-8')),
        'response_sha256': digest(response.encode('utf-8')),
        'source_row_sha256': digest(canonical(row)),
        'prefix_tokens': prefix_tokens, 'supervised_tokens': response_tokens,
        'total_tokens': prefix_tokens + response_tokens, 'trace_truncated': False,
        'generation': {
            'dataset': DATASET, 'revision': REVISION, 'config': CONFIG, 'split': 'train',
            'row_idx': wrapped['row_idx'], 'uuid': row['uuid'], 'generation_index': index,
            'verification': {'math_verify': True, 'complete': True,
                             'boxed_numeric_match': True, 'trace_truncated': False},
            'verified_final_answer': True,
            'verification_method': 'dataset Math-Verify flag plus independent scalar final/reference match',
            'is_reasoning_complete': True, 'correctness_math_verify': True,
            'finish_reason': finish[index] if finish else None,
            'raw_response_sha256': digest(response.encode('utf-8')),
            'prompt_version': 'public-openr1-unmodified',
            'settings': {'original_generation_parameters': 'Not inferred from dataset row'},
        },
        'attribution': {'dataset_url': SOURCE_URL, 'license_listed': 'Apache-2.0',
                        'teacher': 'DeepSeek-R1', 'questions': 'NuminaMath 1.5 sources'},
    }
    candidate['record_sha256'] = digest(canonical(candidate))
    return candidate, 'eligible', stats


def sample_offsets(total: int, block_size: int, seed: int, max_rows: int) -> list[int]:
    offsets = list(range(0, total, block_size))
    random.Random(seed).shuffle(offsets)
    return offsets[:(max_rows + block_size - 1) // block_size]


def prepare(args, tokenizer) -> dict:
    output = Path(args.output).resolve()
    if not output.is_relative_to((ROOT / 'runs').resolve()):
        raise ValueError('Preparation artifacts must stay under ignored cloud/runs')
    if not 1 <= args.max_candidates <= 512 or not 1 <= args.max_rows <= 4096:
        raise ValueError('Require <=512 candidates and <=4096 examined rows')
    if not 1 <= args.block_size <= 20 or not 1 <= args.max_block_mib <= 4 or not 1 <= args.max_download_mib <= 48:
        raise ValueError('Require <=20 rows/block, <=4MiB/block and <=48MiB total')
    if not 1 <= args.max_response_tokens <= 1024 or not 1 <= args.context_limit <= 2048:
        raise ValueError('Require bounded short traces and a <=2048-token context')
    exclusions, exclusion_sources = load_exclusions()
    output.mkdir(parents=True, exist_ok=True)
    raw_folder = output / 'raw_blocks'
    raw_folder.mkdir(exist_ok=True)
    settings = {'dataset': DATASET, 'revision': REVISION, 'config': CONFIG, 'split': SPLIT,
                'seed': args.seed, 'max_candidates': args.max_candidates, 'max_rows': args.max_rows,
                'block_size': args.block_size, 'max_response_tokens': args.max_response_tokens,
                'context_limit': args.context_limit, 'max_block_mib': args.max_block_mib,
                'max_download_mib': args.max_download_mib, 'model': MODEL, 'model_revision': MODEL_REVISION,
                'exclusions': exclusion_sources}
    plan_path = output / 'preparation_plan.json'
    if plan_path.exists():
        if json.loads(plan_path.read_text(encoding='utf-8')) != settings:
            raise ValueError('Frozen preparation settings differ; use a new output directory')
    else:
        write_json(plan_path, settings)
    prior_manifest = output / 'manifest.json'
    if prior_manifest.exists():
        # Preserve the failed/rate-limited attempt when replaying cached data.
        with (output / 'manifest_history.jsonl').open('a', encoding='utf-8') as history:
            history.write(prior_manifest.read_text(encoding='utf-8').replace('\n', '') + '\n')
    http = BoundedHTTP(args.max_download_mib * 1024**2, args.max_block_mib * 1024**2)
    counts, sources, types, generation_rejections = Counter(), Counter(), Counter(), Counter()
    blocks, decisions, candidates, lengths = [], [], [], []
    dedup = Deduplicator(exclusions)
    manifest = {'schema_version': 1, 'status': 'preparing', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
                'settings': settings, 'official_test_accessed': False, 'teacher_api_calls': 0,
                'gpu_jobs_launched': 0, 'trace_rewriting': False, 'trace_truncation': False,
                'limitations': [
                    'Small seeded block sample, not a uniform sample of all eligible dataset rows.',
                    'Scalar final correctness does not establish correctness of every reasoning step.',
                    'Public teacher is DeepSeek-R1; it is not the project DeepSeek-V4 API teacher.',
                    'Official test remains sealed; no claim of complete benchmark decontamination.',
                    'Numeric word-problem filtering does not prove GSM8K-level difficulty.',
                ]}

    def checkpoint(status: str, error: str | None = None) -> None:
        body = b''.join(canonical(r) for r in sorted(candidates, key=lambda r: r['id']))
        (output / 'candidates.jsonl').write_bytes(body)
        (output / 'decisions.jsonl').write_bytes(b''.join(canonical(r) for r in decisions))
        manifest.update(status=status, counts=dict(counts), candidate_count=len(candidates),
                        source_counts=dict(sources), problem_type_counts=dict(types),
                        generation_rejections=dict(generation_rejections),
                        examined_verified_response_token_lengths=lengths,
                        blocks=blocks, cached_source_bytes=sum(b['bytes'] for b in blocks),
                        current_invocation_network_bytes=http.downloaded_bytes,
                        candidates_sha256=digest(body), updated_at_utc=datetime.now(timezone.utc).isoformat())
        if error:
            manifest['error'] = error
        else:
            manifest.pop('error', None)
        write_json(output / 'manifest.json', manifest)

    checkpoint('preparing')
    try:
        # One bounded metadata row supplies dataset size and validates live revision.
        metadata, block = cached_block(raw_folder, http, 0, 1, cached_only=args.cached_only)
        blocks.append(block)
        total = metadata['num_rows_total']
        manifest['source_train_rows'] = total
        remaining_source_bytes = args.max_download_mib * 1024**2 - block['bytes']
        for offset in sample_offsets(total, args.block_size, args.seed, args.max_rows):
            if len(candidates) >= args.max_candidates or counts['examined_rows'] >= args.max_rows:
                break
            length = min(args.block_size, total - offset, args.max_rows - counts['examined_rows'])
            # Cached blocks count toward the same frozen source-data limit as
            # fresh downloads. Never spend the full network allowance again on
            # a resumed run after reading earlier blocks from cache.
            http.max_total_bytes = http.downloaded_bytes + remaining_source_bytes
            payload, block = cached_block(raw_folder, http, offset, length, cached_only=args.cached_only)
            if block['bytes'] > remaining_source_bytes:
                raise RuntimeError('Cached/remote source blocks exceed frozen total byte budget')
            remaining_source_bytes -= block['bytes']
            blocks.append(block)
            if payload['num_rows_total'] != total or len(payload['rows']) != length:
                raise RuntimeError('Dataset row count/layout changed or response lacks requested rows')
            if [r['row_idx'] for r in payload['rows']] != list(range(offset, offset + length)):
                raise RuntimeError('Dataset-server row indices differ from requested range')
            for wrapped in payload['rows']:
                counts['examined_rows'] += 1
                candidate, reason, stats = eligible_row(wrapped, tokenizer,
                    max_response_tokens=args.max_response_tokens, context_limit=args.context_limit)
                sources[str(stats.get('source'))] += 1
                types[str(stats.get('problem_type'))] += 1
                generation_rejections.update(stats.get('generation_rejections', {}))
                lengths.extend(stats.get('verified_response_token_lengths', []))
                decision = {'row_idx': wrapped['row_idx'], 'reason': reason,
                            'source_block_sha256': block['sha256']}
                if candidate is not None:
                    overlap = dedup.match(candidate)
                    if overlap:
                        candidate, reason = None, overlap['reason']
                        decision.update(overlap)
                    elif len(candidates) >= args.max_candidates:
                        candidate, reason = None, 'candidate_cap_reached'
                        decision['reason'] = reason
                    else:
                        candidates.append(candidate)
                        dedup.add(candidate)
                        decision['id'] = candidate['id']
                counts[reason] += 1
                decisions.append(decision)
            checkpoint('preparing')
            print(json.dumps({'examined': counts['examined_rows'], 'eligible': len(candidates),
                              'source_bytes': sum(b['bytes'] for b in blocks)}), flush=True)
        checkpoint('prepared')
    except CachedSampleExhausted:
        manifest['coverage_note'] = 'Replayed the available bounded cached sample; full requested scan not completed'
        checkpoint('prepared_cached_sample')
    except Exception as error:
        checkpoint('stopped', f'{type(error).__name__}: {error}')
        raise
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--seed', type=int, default=SEED)
    parser.add_argument('--max-candidates', type=int, default=512)
    parser.add_argument('--max-rows', type=int, default=512)
    parser.add_argument('--block-size', type=int, default=8)
    parser.add_argument('--max-response-tokens', type=int, default=768)
    parser.add_argument('--context-limit', type=int, default=2048)
    parser.add_argument('--max-block-mib', type=int, default=3)
    parser.add_argument('--max-download-mib', type=int, default=24)
    parser.add_argument('--allow-tokenizer-download', action='store_true',
                        help='Permit only the shared pinned tokenizer loader to fetch its assets; no model weights')
    parser.add_argument('--cached-only', action='store_true',
                        help='Replay only cached pinned blocks and stop cleanly before any missing block')
    args = parser.parse_args()
    # The companion selector owns the shared, pinned tokenizer loader. It loads
    # tokenizer assets only; this preparation step never loads model weights.
    if __package__:
        from .student_valuation import load_tokenizer
    else:
        from student_valuation import load_tokenizer
    tokenizer = load_tokenizer(local_files_only=not args.allow_tokenizer_download)
    manifest = prepare(args, tokenizer)
    print(json.dumps({k: manifest[k] for k in ('status', 'candidate_count', 'counts', 'candidates_sha256')}))


if __name__ == '__main__':
    main()
