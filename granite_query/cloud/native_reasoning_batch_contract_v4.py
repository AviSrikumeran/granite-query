"""Prospective batch-32 protocol; no preparation or dispatch authorization.

Training, targets, exact development identities and loss exposure delegate to
the unchanged original native contract. Only the versioned evaluation batch
partition and output ceiling differ. The validation adapter never changes the original module's
globals or the incoming plan/data and performs no inference.
"""
from __future__ import annotations

from cloud import native_reasoning_contract as original

VERSION = 'native-reasoning-whole-targets16k-batch32-v4'
EVALUATION_BATCH_SIZE = 32
EVALUATION_BATCH_COUNT = 7
EVALUATION_COUNT = 200
MAX_NEW_TOKENS = 2048
_DELEGATED = frozenset(('ENCODER_VERSION MODEL REVISION PREFIX TEACHER_MODEL MODES CAPS CONTEXT TOKEN_BUDGET '
    'TOKENS_PER_UPDATE OPTIMIZER_UPDATES SEED CANDIDATE_COUNT DEVELOPMENT_COUNT DEVELOPMENT_SOURCE_SHA256 '
    'DEVELOPMENT_PROJECTION_SHA256 DEVELOPMENT_IDS_SHA256 TEMPLATE_SHA TOKENIZER CONTROL_STRINGS OPEN_TAIL '
    'canonical sha digest tokenizer_identity encode_target validate_encoding select_whole_targets exposure_windows window_labels').split())


def __getattr__(name):
    if name in _DELEGATED: return getattr(original, name)
    raise AttributeError(name)


def evaluation_batches(count=EVALUATION_COUNT):
    if type(count) is not int or count != EVALUATION_COUNT:
        raise ValueError('The batch32 protocol retains exactly the frozen200 questions')
    return [(start, min(start + EVALUATION_BATCH_SIZE, count))
        for start in range(0, count, EVALUATION_BATCH_SIZE)]


def protocol():
    return dict(original.protocol(), version=VERSION, evaluation_batch_size=EVALUATION_BATCH_SIZE,
        max_new_tokens=MAX_NEW_TOKENS,
        evaluation_batch_count=EVALUATION_BATCH_COUNT,
        evaluation_partition=[list(span) for span in evaluation_batches()],
        evaluation_memory_policy='Optional actual per-generation CUDA allocator peaks; collection failure is unavailable/None with bounded diagnostics, never zero, and does not invalidate answers or timing')


def validate_bundle(data, plan):
    if not isinstance(plan, dict) or not isinstance(data, dict): raise ValueError('Object plan and data required')
    expected = protocol()
    if any(key not in plan or original.digest(plan[key]) != original.digest(value) for key, value in expected.items()):
        raise ValueError('Fixed batch32 protocol settings differ')
    if (plan.get('input_sha256') != original.digest(data)
            or plan.get('protocol_hash') != original.digest({key: value for key, value in plan.items() if key != 'protocol_hash'})):
        raise ValueError('Actual V4 plan/input hash differs')
    # A private validation-only view reuses the reviewed training/identity
    # checks. It is never saved, dispatched, executed or passed to generation.
    legacy_view = {key: value for key, value in plan.items()
        if key not in ('evaluation_batch_count', 'evaluation_partition', 'evaluation_memory_policy')}
    legacy_view.update(original.protocol())
    legacy_view['protocol_hash'] = original.digest({key: value for key, value in legacy_view.items() if key != 'protocol_hash'})
    return original.validate_bundle(data, legacy_view)


def validate(plan, data): return validate_bundle(data, plan)
