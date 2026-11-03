"""No-network audit of source references and frozen selection targets.

Checks equation/reference alignment with a restricted arithmetic AST, then
reproduces SVAMP target context and raw-row hashes. These checks do not establish
that a natural-language problem is well-posed or its reasoning is valid. Nothing
in an existing pool, eligibility file, target file or experiment is modified.
"""
from __future__ import annotations
import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from ranking.verification import numeric_answer

TEACHER = ROOT / 'runs/math_source_teacher1800_v1'
COHORT = ROOT / 'runs/math_source_cohort1800_v1'
TARGETS = ROOT / 'runs/gradient_features_math_v1/targets.jsonl'
PUBLIC = ROOT.parents[1] / 'progress/SOURCE_REFERENCE_AUDIT.json'
SVAMP = 'ChilleD/SVAMP'


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8-sig').split('\n') if line.strip()]


def arithmetic_value(expression):
    """Numbers, +/- unary signs, and binary +,-,*,/ only; never eval/exec."""
    if not isinstance(expression, str) or len(expression) > 2048:
        raise ValueError('Require a short arithmetic expression')
    tree = ast.parse(expression.strip(), mode='eval')
    if sum(1 for _ in ast.walk(tree)) > 128:
        raise ValueError('Arithmetic expression exceeds node bound')

    def calculate(node):
        if isinstance(node, ast.Expression):
            return calculate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            value = Decimal(str(node.value))
            if not value.is_finite() or abs(value.adjusted()) > 50:
                raise ValueError('Numeric literal outside arithmetic bounds')
            return value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = calculate(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp):
            left, right = calculate(node.left), calculate(node.right)
            if isinstance(node.op, ast.Add): return left + right
            if isinstance(node.op, ast.Sub): return left - right
            if isinstance(node.op, ast.Mult): return left * right
            if isinstance(node.op, ast.Div): return left / right
        raise ValueError('Only bounded numeric arithmetic syntax is permitted')

    with localcontext() as context:
        context.prec = 50
        result = calculate(tree)
        if not result.is_finite():
            raise ValueError('Non-finite arithmetic result')
        return result


def record_checks(target, raw):
    equation = arithmetic_value(raw['Equation'])
    gold = numeric_answer(target['gold_answer'])
    response = target.get('response', '')
    final = numeric_answer(response.rsplit('####', 1)[-1].strip()) if '####' in response else None
    return {'equation_equals_reference': equation == gold,
        'source_answer_equals_reference': numeric_answer(str(raw['Answer'])) == gold,
        'complete_context_projection_matches': target['prompt'] == raw['Body'] + '\n\n' + raw['Question'],
        'raw_row_attribution_hash_matches': target['source_row_sha256'] == sha(canonical(raw).encode('utf-8')),
        'teacher_final_equals_reference': final == gold}


def audit(teacher_run=TEACHER, cohort_run=COHORT, targets=TARGETS):
    teacher_run, cohort_run, targets = map(lambda value: Path(value).resolve(), (teacher_run, cohort_run, targets))
    if any(not path.is_relative_to((ROOT / 'runs').resolve()) for path in (teacher_run, cohort_run, targets)):
        raise ValueError('Audit inputs must be the ignored local research artifacts')
    summary_raw = (teacher_run / 'teacher_summary.json').read_bytes()
    summary = json.loads(summary_raw)
    if summary.get('stage') != 'completed' or summary.get('official_test_accessed') is not False:
        raise ValueError('Require a completed training-only teacher pool')
    attempts = jsonl(teacher_run / 'teacher_results.jsonl')
    selected = jsonl(targets)
    if (len(attempts) != summary['completed'] or summary['completed'] != summary['requested']
            or sum(bool(row['eligible']) for row in attempts) != summary['eligible']
            or len({row['id'] for row in attempts}) != len(attempts)):
        raise ValueError('Completed teacher summary and original attempts differ')
    if any(row.get('source_split') != 'train' for row in attempts + selected):
        raise ValueError('Only training-split records may be audited')
    svamp = {row['row_idx']: row for row in attempts if row.get('source') == SVAMP}
    targets_by_index = {row['row_idx']: row for row in selected if row.get('source') == SVAMP}
    if len(targets_by_index) != len(selected):
        raise ValueError('This target audit requires unique SVAMP targets')
    source_counts, target_counts = Counter(), Counter()
    source_mismatches, target_failures, seen, found_targets = [], [], set(), set()
    folder = cohort_run / 'sources/ChilleD__SVAMP'
    for path in sorted(folder.glob('rows_*.json')):
        if path.name.endswith('.metadata.json'): continue
        block_raw = path.read_bytes()
        metadata = json.loads(path.with_suffix('.json.metadata.json').read_text(encoding='utf-8'))
        if sha(block_raw) != metadata['sha256']:
            raise ValueError('Raw source block hash changed')
        for wrapper in json.loads(block_raw)['rows']:
            index, raw = wrapper['row_idx'], wrapper['row']
            if index not in svamp or index in seen: continue
            seen.add(index)
            if wrapper.get('truncated_cells'):
                source_counts['truncated_source_rows'] += 1
                continue
            teacher = svamp[index]
            if metadata.get('revision') != teacher['source_revision']:
                raise ValueError('Raw source revision differs from teacher attribution')
            checks = record_checks(teacher, raw)
            source_counts['equations_checked'] += 1
            if not (checks['complete_context_projection_matches'] and checks['raw_row_attribution_hash_matches']):
                source_counts['context_or_attribution_disagreements'] += 1
            if not checks['equation_equals_reference']:
                source_counts['equation_reference_disagreements'] += 1
                source_counts['disagreement_teacher_eligible' if teacher['eligible'] else 'disagreement_teacher_rejected'] += 1
                final = numeric_answer(teacher['response'].rsplit('####', 1)[-1]) if '####' in teacher['response'] else None
                if final == arithmetic_value(raw['Equation']):
                    source_counts['teacher_matches_equation_not_reference'] += 1
                source_mismatches.append({'source_row_idx': index, 'upstream_id': raw.get('ID'),
                    'source': SVAMP, 'teacher_eligible': teacher['eligible'],
                    'equation_result': str(arithmetic_value(raw['Equation'])), 'provided_reference': teacher['gold_answer']})
            if index in targets_by_index:
                found_targets.add(index)
                checked = record_checks(targets_by_index[index], raw)
                target_counts['targets_checked'] += 1
                for name, okay in checked.items():
                    target_counts[name + '_passed'] += int(okay)
                if not all(checked.values()):
                    target_failures.append({'id': targets_by_index[index]['id'], 'failed_checks': [key for key, value in checked.items() if not value]})
    if seen != set(svamp) or found_targets != set(targets_by_index):
        raise ValueError('Not all declared source/target attributions could be found')
    origins = []
    near = []
    for source in sorted({row['source'] for row in attempts}):
        rows = [row for row in attempts if row['source'] == source]
        eligible = [row for row in rows if row['eligible']]
        origins.append({'source': source, 'attempts': len(rows), 'reference_match_eligible': len(eligible),
            'eligible_supervised_tokens': sum(row.get('supervised_tokens', 0) for row in eligible),
            'reference_origins': dict(Counter(row['reference_type'] for row in rows)),
            'rejection_labels': dict(Counter(row['verification'] for row in rows if not row['eligible']))})
        close = 0
        for row in rows:
            if row['verification'] != 'incorrect_teacher_final_answer' or '####' not in row['response']: continue
            gold, predicted = numeric_answer(row['gold_answer']), numeric_answer(row['response'].rsplit('####', 1)[-1])
            if gold is not None and predicted is not None and abs(gold-predicted) <= Decimal('1e-9') * max(abs(gold), Decimal(1)):
                close += 1
        near.append({'source': source, 'within_relative_1e9_but_exactly_rejected': close})
    return {'schema_version': 1, 'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'audit_type': 'No-network source-reference and target-projection checks',
        'teacher_run': teacher_run.name, 'teacher_summary_sha256': sha(summary_raw),
        'target_file_sha256': sha(targets.read_bytes()), 'official_test_accessed': False,
        'new_teacher_calls': 0, 'new_gpu_jobs': 0, 'frozen_artifacts_modified': False,
        'teacher_attempts': len(attempts), 'reference_match_eligible': sum(row['eligible'] for row in attempts),
        'source_breakdown': origins,
        'svamp_equation_audit': {'counts': dict(source_counts), 'reference_disagreements': source_mismatches},
        'selection_target_audit': {'target_count': len(selected), 'counts': dict(target_counts),
            'mismatched_target_ids': target_failures, 'all_arithmetic_projection_checks_pass': not target_failures},
        'numeric_precision_diagnostic': {'policy': 'Diagnostic only; no tolerance or eligibility changed', 'sources': near},
        'manual_semantic_observations': [
            {'source': SVAMP, 'source_row_idx': 278, 'issue': 'Question time horizon is not supported by the provided two-day equation; not a selection target'},
            {'source': 'math-ai/TemplateGSM', 'source_row_idx': 304152, 'issue': 'Time-per-distance question omits total distance; provided program result does not establish self-contained question validity'},
            {'source': 'nvidia/OpenMathInstruct-2', 'source_row_idx': 23036, 'issue': 'Four consecutive integer ages cannot sum to the stated total; a majority reference is not independent gold'},
            {'source': SVAMP, 'source_row_idx': 52, 'selection_target': 52 in targets_by_index, 'issue': 'Irrelevant inventory fact is physically inconsistent, while asked wrapper quantity remains arithmetically determined'},
            {'source': SVAMP, 'source_row_idx': 696, 'selection_target': 696 in targets_by_index, 'issue': 'Irrelevant initial inventory is smaller than stated picked total, while asked picked total remains arithmetically determined'}],
        'limitations': ['Equation/reference agreement does not verify semantic sufficiency of a question.',
            'Reference-match eligibility is a training gate, not independent teacher accuracy or proof that each reasoning step is correct.',
            'Procedural and synthetic majority-vote references retain their stated origins.',
            'Manual semantic observations are documented examples, not an exhaustive semantic audit.',
            'Current frozen targets and pools were inspected without alteration.'],
        'interpretation': f"Source equation/reference disagreements and their existing eligibility are reported above. All {len(selected)} current selection targets were checked for equation/reference, complete raw-context projection, attribution hash and teacher-final agreement; individual failures, if any, are listed explicitly. Broader semantic/reference-quality work remains necessary."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--teacher-run', type=Path, default=TEACHER)
    parser.add_argument('--cohort-run', type=Path, default=COHORT)
    parser.add_argument('--targets', type=Path, default=TARGETS)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    report = audit(args.teacher_run, args.cohort_run, args.targets)
    if not args.dry_run:
        temporary = PUBLIC.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        temporary.replace(PUBLIC)
    print(json.dumps({'source_equations_checked': report['svamp_equation_audit']['counts']['equations_checked'],
        'source_reference_disagreements': report['svamp_equation_audit']['counts'].get('equation_reference_disagreements', 0),
        'targets_checked': report['selection_target_audit']['target_count'],
        'target_checks_pass': report['selection_target_audit']['all_arithmetic_projection_checks_pass'],
        'saved': not args.dry_run}))


if __name__ == '__main__':
    main()
