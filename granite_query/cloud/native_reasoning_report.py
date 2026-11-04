"""Sanitized native study snapshot; read-only unless --write is explicit.

This is a local receipt report, never a provider poll, teacher inspection, model
loader or accounting operation. No original questions, responses or channels
are included in its public projection.
"""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path

from cloud import native_reasoning_control as control
from cloud import native_reasoning_contract as contract
from cloud.evaluation_stats import paired

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT.parents[1] / 'progress'
DOCS = ROOT.parents[1] / 'docs'
VERSION = 'native-reasoning-public-receipts-v1'
LABELS = {'baseline': 'Fresh untouched Granite', 'concise': 'Concise supervision',
          'thinking': 'Native reasoning supervision'}
TEACHER_STAGES = {'completed', 'collecting', 'halted', 'prepared_unpaid', 'prepared_or_partial',
                  'failed_requires_reconciliation'}


def _count(value, maximum):
    return value if type(value) is int and 0 <= value <= maximum else None

def _live_counts(result,collection,plan):
    history=collection/'teacher_results.jsonl'
    if not (collection/'collector.lock').exists() or not history.exists() or history.stat().st_size>64*1024*1024:return
    # Only complete LF-terminated records count during an append. These are
    # progress counts, not final raw verification or student accuracy.
    complete=history.read_bytes().split(b'\n')[:-1];seen=set()
    expected={qid+'::'+mode for qid in plan.get('candidate_ids',[]) for mode in contract.MODES}
    for line in complete:
        if not line.strip():continue
        try:value=json.loads(line)
        except (ValueError,UnicodeError):return
        if not isinstance(value,dict) or value.get('id') not in expected or value['id'] in seen:return
        seen.add(value['id'])
    result['retained_original_outcomes']=len(seen)
    result['live_counts_note']='Complete append-only outcome records; final raw receipt validation is pending.'


def _teacher(collection):
    result = {'stage': 'prepared_unpaid', 'planned_questions': 256, 'planned_original_calls': 512,
        'conditions': {'concise': {'thinking': False, 'teacher_output_cap': 1024},
                       'thinking': {'thinking': True, 'reasoning_effort': 'high', 'teacher_output_cap': 4096}},
        'retained_original_outcomes': None, 'eligible_question_pairs': None,
        'unknown_usage_attempts': None, 'raw_channels_public': False}
    path = collection / 'teacher_summary.json'
    if (collection / 'collector.lock').exists(): result['stage'] = 'collecting'
    if not path.exists():
        _live_counts(result,collection,control.read(collection/'plan.json'))
        return result
    summary = control.read(path)
    plan = control.read(collection / 'plan.json')
    if (summary.get('run_id') != collection.name or summary.get('plan_sha256') != plan.get('plan_sha256')
            or summary.get('requested_questions') != 256 or summary.get('requested_original_calls') != 512):
        result['stage'] = 'summary_validation_failed'
        return result
    result['stage'] = summary.get('stage') if summary.get('stage') in TEACHER_STAGES else 'unrecognized_summary'
    if (collection / 'collector.lock').exists(): result['stage'] = 'collecting'
    for key, maximum in (('retained_original_outcomes', 512), ('eligible_question_pairs', 256), ('unknown_usage_attempts', 512)):
        result[key] = _count(summary.get(key), maximum)
    for mode in contract.MODES:
        values = summary.get('conditions', {}).get(mode, {})
        for key, maximum in (('retained_original_outcomes', 256), ('individually_eligible', 256),
                             ('paired_eligible_supervised_tokens', 256 * 4096)):
            result['conditions'][mode][key] = _count(values.get(key), maximum)
    _live_counts(result,collection,plan)
    return result


def _empty(role):
    return {'role': role, 'label': LABELS[role], 'status': 'not_prepared',
        'accuracy_percent': None, 'metrics': None, 'actual_supervised_tokens': None,
        'actual_optimizer_updates': None, 'retained_evaluation_count': None,
        'planned_evaluation_count': 200, 'provider_terminal_receipt_verified': False}


def _completed(controller, job, terminal):
    """Accept metrics only after the complete local source/call/raw proof chain."""
    folder = job['folder_path']
    dispatch = controller._dispatch(job)
    launch = control.validate_launch(folder, job, dispatch, control.read(folder / 'launch.json'))
    if (terminal.get('kind') != 'completed' or terminal.get('call_id') != launch['call_id']
            or terminal.get('claim_id') != dispatch['claim_id']
            or terminal.get('intent_sha256') != dispatch['intent_sha256']
            or terminal.get('result_sha256') != control.sha(folder / 'result.json')
            or terminal.get('raw_validation_sha256') != control.sha(folder / 'raw_validation.json')):
        raise ValueError('Completed call/result/raw-validation receipt bindings differ')
    result = control.read(folder / 'result.json')
    if (result.get('dispatch') != dispatch or result.get('dispatch_sha256') != control.digest(dispatch)
            or result.get('call_id') != launch['call_id'] or result.get('protocol_hash') != job['plan']['protocol_hash']):
        raise ValueError('Worker result belongs to another immutable call or plan')
    metrics = control.validate_result(job, result)
    proof = control.read(folder / 'raw_validation.json')
    if (proof.get('raw_batches_verified') != 25 or proof.get('fixed_denominator') != 200
            or proof.get('metrics') != metrics or proof.get('dispatch_sha256') != control.digest(dispatch)):
        raise ValueError('Independent full-denominator raw replay proof differs')
    rows = result['evaluations'][job['role']]
    arm = job['data'].get('arm')
    public = dict(_empty(job['role']), status='completed', accuracy_percent=metrics['numeric_correct'] / 2,
        metrics=metrics, actual_supervised_tokens=result['supervised_tokens'],
        actual_optimizer_updates=result['optimizer_updates'], retained_evaluation_count=200,
        provider_terminal_receipt_verified=True, call_id=launch['call_id'],
        result_sha256=terminal['result_sha256'], raw_validation_sha256=terminal['raw_validation_sha256'],
        unique_teaching_questions=len(arm['training']) if arm else 0,
        complete_target_exposure=True, inference_mode='native OPEN thinking / 1024 new tokens',
        latency_measurement='Amortized batched GPU generation time; not single-request or API latency')
    return public, rows


def _job(controller, job):
    public = dict(_empty(job['role']), status='prepared')
    folder = job['folder_path']
    if (folder / 'dispatch.json').exists(): public['status'] = 'dispatch_claimed'
    if (folder / 'launch.json').exists(): public['status'] = 'running_or_awaiting_terminal'
    terminal_path = folder / 'provider_terminal.json'
    if not terminal_path.exists(): return public, None
    terminal = control.read(terminal_path)
    if terminal.get('kind') == 'completed': return _completed(controller, job, terminal)
    public['status'] = 'failed_or_incomplete'
    # A partial attempt is never scored as a smaller benchmark. Its retained
    # count is descriptive only and has no numeric accuracy attached.
    partial = folder / 'provider_result.json'
    if partial.exists() and terminal.get('partial_result_sha256') == control.sha(partial):
        value = control.read(partial)
        public['retained_evaluation_count'] = _count(value.get('retained_evaluation_count'), 200)
        public['actual_supervised_tokens'] = _count(value.get('supervised_tokens'), 16384)
        public['actual_optimizer_updates'] = _count(value.get('optimizer_updates'), 16)
    return public, None


def build(output=control.DEFAULT, *, write=False):
    """Read only existing local metadata. Explicit write emits three safe files."""
    output = control.safe(output)
    result = {'schema_version': 1, 'version': VERSION, 'updated_at_utc': datetime.now(timezone.utc).isoformat(),
        'run_id': output.name, 'stage': 'unprepared', 'paid_work_launched_by_reporter': False,
        'official_test_used': False, 'current_work': {'stage': 'unprepared', 'detail': 'No native study design is frozen.'},
        'protocol': {'teacher_candidate_pairs': 256, 'teacher_output_caps': {'concise': 1024, 'thinking': 4096},
            'loss_tokens_per_adapter': 16384, 'optimizer_updates': 16, 'tokens_per_update': 1024,
            'context_limit': 4096, 'student_evaluation_count': 200, 'evaluation_split': 'GSM8K TRAIN development',
            'enable_thinking': True, 'native_generation_prefix': 'OPEN', 'max_new_tokens': 1024,
            'evaluation_batch_size': 8, 'input_limit': 1536, 'training_seed': 42},
        'teacher': None, 'jobs': [_empty(role) for role in control.ROLES], 'comparisons': None,
        'strong_teacher_reference': {'status': 'pending_separate_review_and_funding', 'proposed_thinking_output_cap': 8192,
            'included_in_this_study': False},
        'limitations': [
            'Adaptive 200-question training-split development evaluation; not official final-test evidence.',
            'The common OPEN/1024 inference condition requires a fresh baseline; prior closed nonthinking 512-token results are separate.',
            'Equal complete loss tokens and updates do not match examples, forwarded tokens, compute or wall time.',
            'This compares supervision recipes, not ranking superiority or a pure causal effect of explanation depth.',
            'Final-number/reference matches do not verify every reasoning step; common full-fit pairs are a selected intersection.',
            'One training seed; paired intervals cover questions, not training-seed variation; exploratory comparisons are not multiplicity corrected.',
            'Preparation, collection and a runnable implementation do not establish student improvement.']}
    if (output / 'design.json').exists():
        try:
            design = control.verify_design(output)
            result['design_sha256'] = control.sha(output / 'design.json')
            collection = control.safe(control.PRIVATE / design['collection'])
            result['teacher'] = _teacher(collection)
            result['stage'] = 'collecting_or_awaiting_teacher_pool'
            result['current_work'] = {'stage': result['stage'], 'detail': 'Preparing or collecting 256 paired TRAIN teaching questions; student metrics are unavailable.'}
            halted = result['teacher']['stage'] in ('halted', 'failed_requires_reconciliation')
            if halted:
                teacher = result['teacher']
                retained = teacher['retained_original_outcomes']
                unknown = teacher['unknown_usage_attempts']
                outcome_text = f'{retained}/512 original outcomes retained' if retained is not None else 'Incomplete original outcomes retained'
                unknown_text = f'{unknown} unknown-usage attempt' + ('' if unknown == 1 else 's') if unknown is not None else 'Unknown usage needs reconciliation'
                result['stage'] = 'teacher_collection_halted_requires_reconciliation'
                result['current_work'] = {'stage': result['stage'],
                    'detail': f'Teacher collection halted: {outcome_text}; {unknown_text}. The original failed request must not be resent. Reconciliation and a reviewed continuation are required; student metrics are unavailable.'}
            if (output / 'study_manifest.json').exists() and not halted:
                jobs = control.load_jobs(output)
                controller = control.Controller(output)
                public, rows = [], {}
                for job in jobs:
                    try:
                        summary, values = _job(controller, job)
                    except (ValueError, KeyError, TypeError, OSError):
                        summary, values = dict(_empty(job['role']), status='receipt_validation_failed'), None
                    public.append(summary)
                    if values is not None: rows[job['role']] = values
                result['jobs'] = public
                result['stage'] = 'student_study_active_or_prepared'
                result['current_work'] = {'stage': result['stage'], 'detail': 'Fresh baseline, concise and native reasoning arms share the OPEN/1024 development protocol. Pending or failed attempts have no accuracy.'}
                if len(rows) == 3 and set(rows) == set(control.ROLES):
                    result['comparisons'] = {
                        'concise_minus_baseline': paired(rows['baseline'], rows['concise']),
                        'thinking_minus_baseline': paired(rows['baseline'], rows['thinking']),
                        'thinking_minus_concise': paired(rows['concise'], rows['thinking'])}
                    result['stage'] = 'all_three_completed_and_locally_validated'
                    result['current_work'] = {'stage': result['stage'], 'detail': 'All three fixed 200-question development results and local raw replay receipts validate. Interpret the paired estimates with single-seed and adaptive-development limits.'}
        except (ValueError, KeyError, TypeError, OSError):
            result['stage'] = 'design_or_source_validation_failed'
            result['current_work'] = {'stage': result['stage'], 'detail': 'Frozen local design/source metadata needs reconciliation; student metrics are unavailable.'}
    if write:
        _publish(result)
    return result


def _publish(result):
    """Explicit local generation only; no GitHub upload or shared generator."""
    raw = (json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
    for path in (PUBLIC / 'NATIVE_REASONING_STUDY.json', DOCS / 'native-reasoning-study.json'):
        _replace(path, raw)
    lines = ['# Native reasoning study', '', result['current_work']['detail'], '',
        'This study uses 256 planned paired TRAIN questions and three fresh student conditions. Each adapter receives 16,384 complete supervised tokens over 16 updates. Evaluation uses the same adaptive 200 TRAIN-development questions with native OPEN thinking and a 1024-token generation cap.', '',
        '| Condition | State | Accuracy |', '|---|---|---|']
    for job in result['jobs']:
        accuracy = f"{job['accuracy_percent']:.1f}%" if job['accuracy_percent'] is not None else 'Unavailable'
        lines.append(f"| {job['label']} | {job['status']} | {accuracy} |")
    lines.extend(['', 'The stronger 8192-token teacher reference is pending separate review and funding.', ''])
    lines.extend('- ' + value for value in result['limitations'])
    _replace(PUBLIC / 'NATIVE_REASONING_STUDY.md', ('\n'.join(lines) + '\n').encode('utf-8'))


def _replace(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.native-report.pending')
    with temporary.open('wb') as handle:
        handle.write(raw); handle.flush(); os.fsync(handle.fileno())
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, default=control.DEFAULT)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    value = build(args.run, write=args.write)
    print(json.dumps({'stage': value['stage'], 'current_work': value['current_work'],
        'completed_student_roles': sum(job['status'] == 'completed' for job in value['jobs'])}))


if __name__ == '__main__': main()
