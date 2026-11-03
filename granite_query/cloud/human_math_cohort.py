"""Freeze unseen human-reference GSM teaching/development cohorts, unpaid.

Reads only the pinned canonical TRAIN cache and declared training-question
artifacts. Fractions and a bounded arithmetic AST check every reference
annotation and its link to the final answer. No eval/exec, downloaded code,
network, teacher calls, reservations or model-training changes occur.
"""
from __future__ import annotations
import argparse
import ast
from collections import Counter, defaultdict
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import random
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from ranking.prepare_gsm8k import load_source
from cloud.student_pool import build_payload, input_bound, MAX_MESSAGES_UTF8_BYTES
from cloud.source_reference_audit import canonical

RUN = ROOT / 'runs/human_math_cohort2048_dev200_v1'
PUBLIC = ROOT.parents[1] / 'progress/HUMAN_MATH_COHORT.json'
SOURCE = ROOT.parent / 'ranking/data/raw/train.jsonl'
SOURCE_SHA = '17f347dc51477c50d4efb83959dbb7c56297aba886e5544ee2aaed3024813465'
REVISION = '3101c7d5072418e28b9008a6636bde82a006892c'
PROBES = ROOT.parent / 'ranking/runs/gsm8k_preview_128_seed42/target_queries.jsonl'
SEED = 20261109
TEACHING = 2048
DEVELOPMENT = 200
QUESTION_NAMES = {'candidates.jsonl', 'development.jsonl', 'targets.jsonl', 'requests.jsonl',
                  'teaching_candidates.jsonl', 'numeric_prompt_pool.jsonl', 'numeric_prompts.jsonl',
                  'questions.jsonl', 'warmup.jsonl', 'warmup_rows.jsonl'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def rows_bytes(rows):
    return ''.join(canonical(row) + '\n' for row in rows).encode('utf-8')


def normalize(text):
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


def grouped_numbers(text):
    return re.sub(r'(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\w.])',
                  lambda match: match.group().replace(',', ''), text)


def exact_arithmetic(text):
    """Bounded literal rational arithmetic; no calls, names, indexing or code."""
    if not isinstance(text, str) or len(text) > 1024:
        raise ValueError('Expression outside text bound')
    text = grouped_numbers(text.strip().replace('−', '-'))
    tree = ast.parse(text, mode='eval')
    if sum(1 for _ in ast.walk(tree)) > 128:
        raise ValueError('Expression outside node bound')

    def calculate(node):
        if isinstance(node, ast.Expression): return calculate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            literal = ast.get_source_segment(text, node)
            if not literal or not re.fullmatch(r'(?:\d+(?:\.\d*)?|\.\d+)', literal) or len(literal) > 40:
                raise ValueError('Unsupported numeric literal')
            return Fraction(literal)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = calculate(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp):
            left, right = calculate(node.left), calculate(node.right)
            if isinstance(node.op, ast.Add): return left + right
            if isinstance(node.op, ast.Sub): return left - right
            if isinstance(node.op, ast.Mult): return left * right
            if isinstance(node.op, ast.Div): return left / right
            if isinstance(node.op, ast.Pow) and right.denominator == 1 and -3 <= right <= 6:
                return left ** int(right)
        raise ValueError('Unsupported arithmetic syntax')

    return calculate(tree)


def annotation_check(reference, final_answer):
    matches = re.findall(r'<<([^<>]+)>>', reference)
    if not matches:
        return None, 'no_arithmetic_annotations', {}
    proof, last = [], None
    diagnostics = Counter()
    for annotation in matches:
        if annotation.count('=') != 1:
            return None, 'unsupported_annotation_equation', dict(diagnostics)
        expression, expected = annotation.split('=', 1)
        try:
            actual, value = exact_arithmetic(expression), exact_arithmetic(expected)
        except (ValueError, SyntaxError, ZeroDivisionError, OverflowError):
            return None, 'unsupported_annotation_arithmetic', dict(diagnostics)
        if actual != value:
            # Diagnose possible decimal rounding but never silently accept it.
            scalar = grouped_numbers(expected.strip())
            decimal_match = re.fullmatch(r'[+-]?\d*\.(\d{1,6})', scalar)
            if decimal_match and abs(actual-value) <= Fraction(1, 2 * 10**len(decimal_match.group(1))):
                diagnostics['possible_decimal_rounding'] += 1
                return None, 'nonexact_possible_rounding', dict(diagnostics)
            return None, 'nonexact_annotation', dict(diagnostics)
        proof.append({'annotation_sha256': sha(annotation.encode('utf-8')), 'exact_result': str(actual)})
        last = value
    try:
        final = exact_arithmetic(final_answer)
    except (ValueError, SyntaxError, ZeroDivisionError, OverflowError):
        return None, 'unsupported_final_answer', dict(diagnostics)
    if final != last:
        return None, 'final_not_last_annotation', dict(diagnostics)
    return {'method': 'bounded_arithmetic_ast_and_exact_fraction', 'annotations_checked': len(proof),
            'proof': proof, 'last_annotation_matches_final': True,
            'rounding_accepted': False, 'semantic_question_validity_verified': False}, 'exact_annotations_and_final', dict(diagnostics)


def extract_question(row):
    if not isinstance(row, dict) or not isinstance(row.get('id'), str): return None
    prompt = row.get('prompt')
    if not isinstance(prompt, str):
        messages = row.get('payload', {}).get('messages', [])
        users = [message.get('content') for message in messages if message.get('role') == 'user' and isinstance(message.get('content'), str)]
        prompt = users[0] if len(users) == 1 else None
        if prompt:
            from cloud.matched_teacher import PREFIX
            if prompt.startswith(PREFIX): prompt = prompt[len(PREFIX):]
    if not isinstance(prompt, str) or not prompt.strip(): return None
    if row.get('source_split') not in (None, 'train') or ':test:' in row['id']:
        raise ValueError('Evaluation data is forbidden as a cohort selection input')
    return dict(row, prompt=prompt)


def exclusion_artifacts(output):
    paths = {PROBES}
    for path in (ROOT / 'runs').rglob('*.jsonl'):
        if path.name not in QUESTION_NAMES or path.is_relative_to(output): continue
        top = path.relative_to(ROOT / 'runs').parts[0].casefold()
        if top.startswith(('test_', 'local_check', 'tokenizer', 'matplotlib')) or re.search(r'(^|[_-])(test|finaltest)([_-]|$)', top):
            continue
        # Do not open questions in a future final-test run even if its filename
        # follows the same request convention. Only metadata is inspected here.
        plan_path = ROOT / 'runs' / path.relative_to(ROOT / 'runs').parts[0] / 'plan.json'
        if plan_path.exists():
            plan = json.loads(plan_path.read_text(encoding='utf-8-sig'))
            if (plan.get('official_test_accessed') is True or plan.get('official_test_used') is True
                    or plan.get('held_out_test_used') is True or plan.get('evaluation_kind') == 'final_test'):
                continue
        paths.add(path)
    return sorted(paths)


def load_exclusions(output):
    records, artifacts = [], []
    for path in exclusion_artifacts(output):
        raw = path.read_bytes()
        usable = []
        for line in raw.decode('utf-8-sig').split('\n'):
            if not line.strip(): continue
            row = extract_question(json.loads(line))
            if row is not None: usable.append(row)
        records.extend(usable)
        artifacts.append({'run': path.relative_to(ROOT.parent).as_posix(), 'sha256': sha(raw), 'question_records': len(usable)})
    return records, artifacts


def masked_shingles(text, width=5):
    tokens = re.findall(r'\d+(?:[.,]\d+)*|[^\W\d_]+|[+*/=<>%$^-]',
                        unicodedata.normalize('NFKC', text).casefold(), flags=re.UNICODE)
    tokens = ['<NUMBER>' if any(char.isdigit() for char in token) else token for token in tokens]
    return {' '.join(tokens[i:i+width]) for i in range(max(1, len(tokens)-width+1))}


def ancestry_exclusions(canonical_rows, records):
    by_normalized = defaultdict(set)
    for row in canonical_rows: by_normalized[normalize(row['prompt'])].add(row['id'])
    direct, exact, template, explicit_parent = set(), set(), set(), set()
    unknown_openmath = set()
    unique_prompts = {}
    for record in records:
        identifier = record['id']
        if re.fullmatch(r'gsm8k:train:\d{5}', identifier): direct.add(identifier)
        exact.update(by_normalized.get(normalize(record['prompt']), set()))
        unique_prompts.setdefault(normalize(record['prompt']), record['prompt'])
        if record.get('source') == 'math-ai/TemplateGSM' and isinstance(record.get('template_id'), int):
            template.add(f'gsm8k:train:{record["template_id"]:05d}')
        parent = record.get('original_gsm8k_id', record.get('parent_gsm8k_id'))
        if isinstance(parent, int): explicit_parent.add(f'gsm8k:train:{parent:05d}')
        elif isinstance(parent, str) and re.fullmatch(r'gsm8k:train:\d{5}', parent): explicit_parent.add(parent)
        if record.get('source') == 'nvidia/OpenMathInstruct-2' and parent is None:
            unknown_openmath.add(identifier)
    # Detect near-identical lexical skeletons with changed numeric values. This
    # catches some augmentation ancestry but is never claimed complete lineage.
    index, signatures = defaultdict(list), {}
    for row in canonical_rows:
        parts = masked_shingles(row['prompt'])
        signatures[row['id']] = parts
        for part in parts: index[part].append(row['id'])
    near = set()
    for prompt in unique_prompts.values():
        parts = masked_shingles(prompt)
        shared = Counter(identifier for part in parts for identifier in index.get(part, ()))
        minimum = math.ceil(0.85 * len(parts))
        for identifier, intersection in shared.items():
            if intersection < minimum: continue
            other = signatures[identifier]
            if intersection / max(1, len(parts | other)) >= 0.85:
                near.add(identifier)
    excluded = direct | exact | template | explicit_parent | near
    return excluded, {'direct_gsm_ids': len(direct), 'exact_normalized_gsm_questions': len(exact),
        'conservative_template_id_ancestry': len(template), 'explicit_gsm_parent_ids': len(explicit_parent),
        'numeric_masked_lexical_near_ancestry': len(near), 'combined_unique_gsm_exclusions': len(excluded),
        'openmath_records_without_explicit_parent_id': len(unknown_openmath),
        'lineage_limitations': 'Template ID is a conservative numeric proxy, not independently proven source-row mapping. OpenMath parent IDs are absent; exact/near lexical checks detect only some ancestry. No complete decontamination claim.'}


def validate_frozen(output):
    plan = json.loads((output / 'plan.json').read_text(encoding='utf-8'))
    for filename, checksum in [('candidates.jsonl', 'teaching_sha256'),
                              ('development.jsonl', 'development_sha256'),
                              ('requests.jsonl', 'requests_sha256')]:
        if sha((output / filename).read_bytes()) != plan[checksum]:
            raise RuntimeError('Frozen human-math artifact changed')
    return json.loads((output / 'manifest.json').read_text(encoding='utf-8'))


def prepare(output=RUN):
    output = Path(output).resolve()
    if not output.is_relative_to((ROOT / 'runs').resolve()): raise ValueError('Output must be an ignored run')
    source_raw = SOURCE.read_bytes()
    if sha(source_raw) != SOURCE_SHA: raise ValueError('Canonical pinned GSM training file changed')
    if (output / 'plan.json').exists():
        # New future experiments must not retroactively rewrite this split or
        # its capacity audit. A different exclusion state requires a new run.
        return validate_frozen(output)
    rows, source_sha = load_source(SOURCE, 'train')
    if len(rows) != 7473: raise ValueError('Unexpected GSM training size')
    records, artifacts = load_exclusions(output)
    excluded, ancestry = ancestry_exclusions(rows, records)
    counts, diagnostics, valid = Counter(), Counter(), []
    for row in rows:
        if row['id'] in excluded:
            counts['prior_question_or_detectable_ancestry'] += 1; continue
        if input_bound(row) > MAX_MESSAGES_UTF8_BYTES:
            counts['prospective_teacher_input_byte_bound'] += 1; continue
        proof, reason, detail = annotation_check(row['reference_solution'], row['gold_answer'])
        diagnostics.update(detail)
        counts[reason] += 1
        if proof is None: continue
        valid.append(dict(row, source_revision=REVISION,
            reference_type='human_dataset_answer_with_exact_annotation_checks',
            annotation_verification=proof, reference_solution_sha256=sha(row['reference_solution'].encode('utf-8')),
            reference_annotations_verified=True, reference_semantics_verified=False,
            teacher_generated=False, training_ready=False))
    output.mkdir(parents=True, exist_ok=True)
    capacity = {'schema_version': 1, 'run_id': output.name, 'source_rows': len(rows),
        'actual_valid_capacity': len(valid), 'required_capacity': TEACHING + DEVELOPMENT,
        'eligibility_counts': dict(counts), 'rounding_diagnostics': dict(diagnostics), 'ancestry_exclusions': ancestry}
    write(output / 'capacity.json', capacity)
    if len(valid) < TEACHING + DEVELOPMENT:
        capacity['stage'] = 'capacity_shortfall_no_split_frozen'
        write(PUBLIC, capacity)
        return capacity
    random.Random(SEED).shuffle(valid)
    development, teaching = valid[:DEVELOPMENT], valid[DEVELOPMENT:DEVELOPMENT + TEACHING]
    for row in development: row['cohort_role'] = 'independent_training_split_development_holdout'
    for row in teaching: row['cohort_role'] = 'future_teaching'
    requests = [{'id': row['id'], 'payload': build_payload(row)} for row in teaching]
    chunks = [{'index': index, 'ids': [row['id'] for row in teaching[start:start+512]],
               'requests_sha256': sha(rows_bytes(requests[start:start+512])), 'request_count': len(teaching[start:start+512]),
               'conservative_peak_bound_usd': len(teaching[start:start+512]) * (2000*1.32+1024*3.96)/1e6,
               'future_reservation_required_usd': 4, 'reserved_now': False}
              for index, start in enumerate(range(0, TEACHING, 512))]
    plan = {'schema_version': 1, 'run_id': output.name, 'seed': SEED, 'source': 'openai/grade-school-math',
        'source_revision': REVISION, 'source_train_sha256': source_sha,
        'source_url': f'https://github.com/openai/grade-school-math/blob/{REVISION}/grade_school_math/data/train.jsonl',
        'teaching_count': TEACHING, 'development_count': DEVELOPMENT,
        'teaching_ids': [row['id'] for row in teaching], 'development_ids': [row['id'] for row in development],
        'teaching_sha256': sha(rows_bytes(teaching)), 'development_sha256': sha(rows_bytes(development)),
        'requests_sha256': sha(rows_bytes(requests)), 'chunks': chunks, 'exclusion_artifacts': artifacts,
        'capacity_audit': capacity, 'max_serialized_messages_utf8_bytes': max(input_bound(row) for row in teaching),
        'model': 'deepseek-v4-pro', 'thinking_enabled': False, 'max_output_tokens': 1024,
        'new_teacher_calls': 0, 'new_reservations': 0, 'gpu_jobs': 0, 'official_test_accessed': False,
        'future_budget_policy': 'Fresh provider reconciliation and guarded reservation before each separately approved512-request chunk; no funds reserved by preparation',
        'holdout_policy': 'Training-split development only, frozen separately before any teaching; never pass these200 records to a training selector without a separately declared protocol change',
        'collector_contract': 'Question/request files follow the existing contract, but the1800-limited math_teacher adapter must not be blindly pointed at this2048 human-source run',
        'verification_scope': 'Every annotation is exact under bounded Fraction arithmetic and the last annotation equals final reference. This does not prove semantic sufficiency or every natural-language statement.'}
    if (output / 'plan.json').exists():
        if json.loads((output / 'plan.json').read_text(encoding='utf-8')) != plan:
            raise RuntimeError('Frozen human cohort/exclusion state changed; use a new run')
    else:
        (output / 'candidates.jsonl').write_bytes(rows_bytes(teaching))
        (output / 'development.jsonl').write_bytes(rows_bytes(development))
        (output / 'requests.jsonl').write_bytes(rows_bytes(requests))
        write(output / 'plan.json', plan)
        (output / 'chunks').mkdir()
        for chunk in chunks: write(output / 'chunks' / f'{chunk["index"]:03d}.json', chunk)
    public = dict(capacity, stage='prepared_unpaid', actual_teaching_prompts=TEACHING,
        actual_development_holdout=DEVELOPMENT, new_teacher_calls=0, new_gpu_jobs=0, new_reservations=0,
        official_test_accessed=False, updated_at_utc=now(), chunks=[{key: chunk[key] for key in
            ('index', 'request_count', 'conservative_peak_bound_usd', 'future_reservation_required_usd', 'reserved_now')} for chunk in chunks],
        verification_scope=plan['verification_scope'], holdout_policy=plan['holdout_policy'],
        interpretation='A future human-reference teaching cohort and separate training-split development holdout, not newly trained Granite results. Current gradient inputs and frozen pools remain unchanged.')
    write(output / 'manifest.json', public)
    write(PUBLIC, public)
    return public


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=RUN)
    args = parser.parse_args()
    result = prepare(args.output)
    print(json.dumps({key: result[key] for key in ('run_id', 'stage', 'actual_valid_capacity',
        'actual_teaching_prompts', 'actual_development_holdout') if key in result}))


if __name__ == '__main__': main()
