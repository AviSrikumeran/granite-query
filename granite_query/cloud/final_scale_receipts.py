"""Pure validation of future sharded final receipts; no I/O or authorization.

All arguments are already loaded mappings. This module neither reads official
data nor repairs receipts, launches work, refreshes providers or changes funds.
A later reviewed controller must validate the whole execution review/live source
inventory before loading data or executing. A proposal alone grants no access.
"""
from decimal import Decimal, InvalidOperation
import math
import re

from cloud import final_scale_contract as contract_api
from cloud.comparison_metrics import score
from cloud.evaluation_stats import paired

ROLE = 'final_eval_only'
CHECKPOINTS = ('base', 'chosen')
OUTCOMES = {'generated', 'failed', 'input_limit'}
TERMINAL = {'completed', 'failed', 'timed_out', 'cancelled'}
HASH = re.compile(r'[a-f0-9]{64}')
CALL = re.compile(r'fc-[A-Za-z0-9][A-Za-z0-9-]{0,127}')
BINDING_FIELDS = {'schema_version', 'role', 'freeze_sha256', 'source_bundle_sha256',
    'full_source_sha256', 'sample_sha256', 'questions', 'binding_sha256'}
QUESTION_FIELDS = {'id', 'source_index', 'gold_answer', 'input_sha256'}
IDENTITY_FIELDS = ('role', 'freeze_sha256', 'source_bundle_sha256', 'full_source_sha256',
    'sample_sha256', 'binding_sha256', 'checkpoint', 'checkpoint_sha256', 'model', 'revision', 'shard_id')
ROW_FIELDS = {'id', 'source_index', 'global_position', 'input_sha256', 'gold_answer',
    'outcome', 'response', 'truncated', 'generated_tokens', 'elapsed_seconds', 'failure_type'}


def digest(value):
    return contract_api.digest(value)


def _hash(value):
    return isinstance(value, str) and HASH.fullmatch(value) is not None


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def _object(value, description):
    if not isinstance(value, dict):
        raise ValueError(description+' must be an object')
    return value


def _sealed(value, field):
    if not _hash(value.get(field)) or digest({k: v for k, v in value.items() if k != field}) != value[field]:
        raise ValueError('Receipt hash differs: '+field)


def _gold(value):
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError('Reference must be a bounded decimal string')
    try:
        result = Decimal(value.replace(',', ''))
    except InvalidOperation:
        raise ValueError('Invalid decimal reference') from None
    if not result.is_finite():
        raise ValueError('Reference must be finite')


class _Context:
    def __init__(self, contract, binding):
        contract_api.validate(contract)
        self.contract, self.protocol = contract, contract['protocol']
        # Completeness is a declaration check, not a physical source check or
        # permission. Live inventories/review/funding belong to the controller.
        contract_api.validate_sources(contract, self.protocol['source_hashes'], complete=True)
        if self.protocol['selected'] is None:
            raise ValueError('Freeze the chosen checkpoint before accepting any final sample or base receipts')
        self.binding = _object(binding, 'Sample binding')
        if set(binding) != BINDING_FIELDS or binding['schema_version'] != 1 or type(binding['schema_version']) is not int:
            raise ValueError('Unknown sample binding schema')
        _sealed(binding, 'binding_sha256')
        if (binding['role'] != ROLE or binding['freeze_sha256'] != contract['freeze_sha256']
                or binding['source_bundle_sha256'] != digest(self.protocol['source_hashes'])
                or not _hash(binding['full_source_sha256']) or not _hash(binding['sample_sha256'])):
            raise ValueError('Sample source, role or protocol binding differs')
        self.ids = contract_api.expected_ids(contract)
        questions = binding['questions']
        if not isinstance(questions, list) or len(questions) != self.protocol['dataset']['sample_count']:
            raise ValueError('Sample binding must retain the whole frozen denominator')
        self.questions = questions
        for position, (question, identifier, index) in enumerate(zip(questions, self.ids, self.protocol['dataset']['indices'])):
            _object(question, 'Bound question')
            if (set(question) != QUESTION_FIELDS or question['id'] != identifier
                    or not _integer(question['source_index']) or question['source_index'] != index
                    or not _hash(question['input_sha256'])):
                raise ValueError('Bound question identity, order or input hash differs')
            _gold(question['gold_answer'])
        self.shards = {shard['id']: shard for shard in self.protocol['shards']}

    def identity(self, checkpoint, shard_id):
        if not isinstance(checkpoint, str) or not isinstance(shard_id, str) or checkpoint not in CHECKPOINTS or shard_id not in self.shards:
            raise ValueError('Unknown checkpoint or shard')
        checkpoint_data = self.protocol['base'] if checkpoint == 'base' else self.protocol['selected']
        if not checkpoint_data:
            raise ValueError('Chosen checkpoint must be frozen before accepting chosen receipts')
        return {**{key: self.binding[key] for key in ('role', 'freeze_sha256', 'source_bundle_sha256',
                    'full_source_sha256', 'sample_sha256', 'binding_sha256')},
            'checkpoint': checkpoint, 'checkpoint_sha256': digest(checkpoint_data),
            'model': self.protocol['base']['model'], 'revision': self.protocol['base']['revision'], 'shard_id': shard_id}

    def check_identity(self, receipt, checkpoint, shard_id):
        _object(receipt, 'Execution receipt')
        expected = self.identity(checkpoint, shard_id)
        if any(receipt.get(key) != value for key, value in expected.items()):
            raise ValueError('Receipt checkpoint, source, role or frozen input identity differs')

    def batch(self, receipt, *, checkpoint, shard_id, call_id=None, launch_hash=None):
        self.check_identity(receipt, checkpoint, shard_id)
        _sealed(receipt, 'batch_sha256')
        if (not isinstance(receipt.get('call_id'), str) or not CALL.fullmatch(receipt['call_id'])
                or not _hash(receipt.get('launch_sha256'))
                or call_id is not None and receipt['call_id'] != call_id
                or launch_hash is not None and receipt['launch_sha256'] != launch_hash):
            raise ValueError('Batch call or launch identity differs')
        shard = self.shards[shard_id]
        start, stop, count = (receipt.get(key) for key in ('start', 'stop', 'count'))
        if (not all(_integer(x) for x in (start, stop, count))
                or not shard['start'] <= start < shard['stop'] or (start-shard['start']) % 8
                or stop != min(start+8, shard['stop']) or count != stop-start):
            raise ValueError('Batch must cover the exact next logical batch, including an unpadded tail')
        rows = receipt.get('rows')
        if not isinstance(rows, list) or len(rows) != count or receipt.get('rows_sha256') != digest(rows):
            raise ValueError('Batch row count or content hash differs')
        if receipt.get('question_ids_sha256') != digest(self.ids[start:stop]):
            raise ValueError('Batch question identities differ')
        for position, row in zip(range(start, stop), rows):
            _object(row, 'Outcome')
            question = self.questions[position]
            if (set(row) != ROW_FIELDS or row['id'] != question['id']
                    or not _integer(row['global_position']) or row['global_position'] != position
                    or not _integer(row['source_index']) or row['source_index'] != question['source_index']
                    or row['input_sha256'] != question['input_sha256'] or row['gold_answer'] != question['gold_answer']):
                raise ValueError('Outcome order, source, reference or input identity differs')
            outcome = row['outcome']
            if (not isinstance(outcome, str) or outcome not in OUTCOMES
                    or not isinstance(row['response'], str) or len(row['response'].encode('utf-8')) > 1024*1024
                    or type(row['truncated']) is not bool or not _integer(row['generated_tokens'])
                    or row['generated_tokens'] > 512 or not _finite(row['elapsed_seconds'])):
                raise ValueError('Outcome is malformed or exceeds frozen generation bounds')
            if outcome == 'generated':
                if row['failure_type'] is not None:
                    raise ValueError('Generated outcome cannot claim a failure')
            elif outcome == 'input_limit':
                if (row['failure_type'] != 'input_limit' or row['response'] or row['generated_tokens']
                        or row['truncated'] or row['elapsed_seconds']):
                    raise ValueError('Input-limit outcome must be retained without invented generation')
            elif row['failure_type'] != 'generation_error':
                raise ValueError('Failed outcome needs its bounded failure identity')
        return rows


def validate_binding(contract, binding):
    """Validate metadata supplied by a later hash-checked loader; never read it."""
    context = _Context(contract, binding)
    return {'count': len(context.ids), 'binding_sha256': binding['binding_sha256'], 'role': ROLE}


def validate_batch(contract, binding, receipt):
    context = _Context(contract, binding)
    _object(receipt, 'Batch')
    return context.batch(receipt, checkpoint=receipt.get('checkpoint'), shard_id=receipt.get('shard_id'))


def _attempts(context, checkpoint, shard_id, attempts, *, require_terminal=False):
    identity = context.identity(checkpoint, shard_id)
    shard = context.shards[shard_id]
    if not isinstance(attempts, list):
        raise ValueError('Attempts must be an explicitly ordered lineage')
    if len(attempts) > 1+context.protocol['bounds']['max_gpu_recovery_calls']:
        raise ValueError('Call lineage exceeds the frozen recovery-call ceiling')
    rows, prior_call, last_stage, calls = [], None, None, set()
    for number, attempt in enumerate(attempts):
        _object(attempt, 'Attempt')
        if set(attempt) != {'launch', 'terminal', 'batches'}:
            raise ValueError('Unknown attempt schema')
        launch = attempt['launch']; context.check_identity(launch, checkpoint, shard_id)
        _sealed(launch, 'launch_sha256')
        call_id = launch.get('call_id')
        if not isinstance(call_id, str) or not CALL.fullmatch(call_id) or call_id in calls:
            raise ValueError('Missing or duplicated call identity')
        calls.add(call_id)
        if (launch.get('parent_call_id') != prior_call or launch.get('prefix_sha256') != digest(rows)
                or prior_call is not None and last_stage not in ('failed', 'timed_out', 'cancelled')):
            raise ValueError('Continuation does not preserve a confirmed terminal prefix')
        if number and len(rows) == shard['stop']-shard['start']:
            raise ValueError('A fully retained shard has no remaining positions for a new call')
        batches = attempt['batches']
        if not isinstance(batches, list):
            raise ValueError('Committed batches must be ordered')
        for receipt in batches:
            new_rows = context.batch(receipt, checkpoint=checkpoint, shard_id=shard_id,
                call_id=call_id, launch_hash=launch['launch_sha256'])
            if receipt['start'] != shard['start']+len(rows):
                raise ValueError('Committed batches are not a contiguous, nonduplicated shard prefix')
            rows.extend(new_rows)
        terminal = attempt['terminal']
        if terminal is None:
            if require_terminal or number != len(attempts)-1:
                raise ValueError('Unknown or ambiguous call termination cannot authorize recovery')
            last_stage = 'running'
        else:
            context.check_identity(terminal, checkpoint, shard_id)
            _sealed(terminal, 'terminal_sha256')
            stage = terminal.get('stage')
            if (terminal.get('confirmed_terminal') is not True or not isinstance(stage, str) or stage not in TERMINAL
                    or terminal.get('call_id') != call_id or terminal.get('launch_sha256') != launch['launch_sha256']
                    or terminal.get('committed_batches_sha256') != digest([b['batch_sha256'] for b in batches])
                    or terminal.get('output_prefix_sha256') != digest(rows)
                    or type(terminal.get('retained_count')) is not int or terminal['retained_count'] != len(rows)):
                raise ValueError('Terminal receipt does not confirm this exact call and retained prefix')
            if stage == 'completed' and len(rows) != shard['stop']-shard['start']:
                raise ValueError('Completed call must retain its whole shard denominator')
            last_stage = stage
        prior_call = call_id
    complete = last_stage == 'completed' and len(rows) == shard['stop']-shard['start']
    return {**identity, 'status': 'completed' if complete else last_stage or 'pending',
        'retained_count': len(rows), 'expected_count': shard['stop']-shard['start'],
        'next_position': shard['start']+len(rows), 'rows': rows, 'last_call_id': prior_call,
        'prefix_sha256': digest(rows), 'recovery_calls': max(0, len(attempts)-1),
        'can_resume': bool(attempts) and len(attempts) <= context.protocol['bounds']['max_gpu_recovery_calls']
            and last_stage in ('failed', 'timed_out', 'cancelled')
            and len(rows) < shard['stop']-shard['start'], 'call_ids': sorted(calls)}


def recover_prefix(contract, binding, checkpoint, shard_id, attempts):
    """Return only an audited prefix; running/unknown calls cannot be recovered.

    The returned can_resume flag covers this lineage only, never permission or a
    reservation. The controller must also check the whole-bundle recovery count.
    New children append only new batches and bind the exact prior prefix hash.
    A failed call with every row retained remains failed: reviewed local
    completion reconciliation is future controller work, never a paid rerun.
    """
    if not attempts:
        raise ValueError('Recovery requires an existing confirmed terminal call')
    return _attempts(_Context(contract, binding), checkpoint, shard_id, attempts, require_terminal=True)


def _scoring_rows(rows):
    # Preserve original rows; failed attempts remain denominator failures even if
    # their incomplete text happens to end with the expected final number.
    return [dict(row, truncated=row['truncated'] or row['outcome'] != 'generated') for row in rows]


def _metrics(rows):
    scored = [score(row) for row in _scoring_rows(rows)]
    return {'count': len(rows), 'numeric_correct': sum(x['correct'] for x in scored),
        'strict_format_correct': sum(x['strict_format_correct'] for x in scored),
        'generated': sum(r['outcome'] == 'generated' for r in rows),
        'failed': sum(r['outcome'] == 'failed' for r in rows),
        'input_limit': sum(r['outcome'] == 'input_limit' for r in rows),
        'truncated': sum(r['truncated'] for r in rows),
        'generated_tokens': sum(r['generated_tokens'] for r in rows),
        'latency_seconds_total': sum(r['elapsed_seconds'] for r in rows),
        'accuracy_percent': 100*sum(x['correct'] for x in scored)/len(rows),
        'scoring_policy': 'Whole frozen denominator; failed/input-limit/truncated outcomes never count correct. Numeric final-answer scoring does not verify reasoning.'}


def aggregate(contract, binding, attempts_by_checkpoint, *, paired_resamples=20000):
    """Return aggregate-only evidence; incomplete checkpoint metrics are null."""
    context = _Context(contract, binding)
    _object(attempts_by_checkpoint, 'Checkpoint receipts')
    if not set(attempts_by_checkpoint) <= set(CHECKPOINTS):
        raise ValueError('Unknown checkpoint receipts')
    if not _integer(paired_resamples, 100):
        raise ValueError('Paired bootstrap needs at least100 resamples')
    public, complete_rows, global_calls, recoveries = {}, {}, set(), 0
    for checkpoint in CHECKPOINTS:
        by_shard = attempts_by_checkpoint.get(checkpoint, {})
        _object(by_shard, 'Shard receipts')
        if not set(by_shard) <= set(context.shards):
            raise ValueError('Unknown or cross-study shard')
        shard_states, rows = [], []
        for shard_id in context.shards:
            state = _attempts(context, checkpoint, shard_id, by_shard.get(shard_id, []))
            if global_calls & set(state['call_ids']):
                raise ValueError('A call identity cannot be reused across checkpoints or shards')
            global_calls.update(state['call_ids'])
            recoveries += state['recovery_calls']
            if recoveries > context.protocol['bounds']['max_gpu_recovery_calls']:
                raise ValueError('Whole bundle exceeds the frozen recovery-call ceiling')
            if state['status'] == 'completed':
                rows.extend(state['rows'])
            shard_states.append({'shard_id': shard_id, 'status': state['status'],
                'retained_count': state['retained_count'], 'expected_count': state['expected_count']})
        complete = all(s['status'] == 'completed' for s in shard_states)
        if complete:
            if [row['id'] for row in rows] != context.ids:
                raise ValueError('Whole-denominator question identities differ')
            complete_rows[checkpoint] = rows
        retained = sum(s['retained_count'] for s in shard_states)
        statuses = {s['status'] for s in shard_states}
        checkpoint_status = ('completed' if complete else 'running' if 'running' in statuses
            else 'incomplete_terminal' if statuses & {'failed', 'timed_out', 'cancelled'}
            else 'partial' if retained else 'pending')
        public[checkpoint] = {'status': checkpoint_status,
            'expected_count': len(context.ids), 'retained_count': retained, 'shards': shard_states,
            'metrics': _metrics(rows) if complete else None}
    ready = set(complete_rows) == set(CHECKPOINTS)
    comparison = paired(_scoring_rows(complete_rows['base']), _scoring_rows(complete_rows['chosen']),
        resamples=paired_resamples) if ready else None
    if comparison is not None:
        comparison['limitations'] = ('Frozen same-question final comparison of one base and one selected training run. '
            'Question-bootstrap uncertainty does not cover training-seed variation. Numeric final-answer scoring does not verify reasoning.')
    return {'role': ROLE, 'freeze_sha256': contract['freeze_sha256'],
        'source_bundle_sha256': binding['source_bundle_sha256'], 'binding_sha256': binding['binding_sha256'],
        'sample_sha256': binding['sample_sha256'], 'count': len(context.ids),
        'recovery_calls': recoveries,
        'full_test_evaluation': context.protocol['dataset']['full_test_evaluation'],
        'checkpoints': public, 'paired_status': 'completed' if ready else 'unavailable',
        'chosen_vs_base': comparison, 'execution_authorized_by_this_module': False,
        'limitations': ['This helper validates supplied receipts, not live provider status or funding.',
            'Incomplete outcomes never become a reduced-denominator accuracy.',
            'Question-bootstrap uncertainty does not measure training-seed variation.',
            'Latency is supplied amortized batch generation timing, not single-request latency.']}
