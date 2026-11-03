"""Dependency-free validation and masking for the equal-token training worker."""
import math


def window_labels(row, window):
    start, end = window['answer_start'], window['answer_end']
    if not (0 <= start < end <= row['supervised_tokens'] <= row['full_response_tokens']):
        raise ValueError('Invalid supervised answer span')
    prefix = row['prefix_tokens']
    labels = [-100] * len(row['input_ids'])
    labels[prefix+start:prefix+end] = row['input_ids'][prefix+start:prefix+end]
    if sum(value != -100 for value in labels) != window['supervised_tokens']:
        raise ValueError('Window token count differs from label mask')
    return labels


def validate_arm(arm):
    if arm.get('arm') not in ('valued', 'random'):
        raise ValueError('Unknown selector arm')
    budget, per_update = arm['token_budget'], arm['tokens_per_update']
    if not isinstance(budget, int) or not isinstance(per_update, int) or budget <= 0 or per_update <= 0 or budget % per_update:
        raise ValueError('Positive exactly divisible token budget required')
    rows = {row['id']:row for row in arm['training']}
    if len(rows) != len(arm['training']) or not rows:
        raise ValueError('Training IDs must be unique and nonempty')
    for row in rows.values():
        ids, labels, mask = row['input_ids'], row['labels'], row['attention_mask']
        prefix, count = row['prefix_tokens'], row['supervised_tokens']
        if len(ids) != len(labels) or len(ids) != len(mask) or not (0 < prefix < len(ids)):
            raise ValueError('Training lengths or prefix invalid')
        if row['full_response_tokens'] != len(ids)-prefix or not (0 < count <= row['full_response_tokens']):
            raise ValueError('Invalid response token counts')
        if any(not isinstance(i, int) or i < 0 for i in ids) or any(i != 1 for i in mask):
            raise ValueError('Require unpadded nonnegative token IDs')
        expected = [-100]*prefix + ids[prefix:prefix+count] + [-100]*(len(ids)-prefix-count)
        if labels != expected:
            raise ValueError('Global label mask differs from the frozen exposure')
    updates = arm['updates']
    if len(updates) != arm['optimizer_updates'] or len(updates)*per_update != budget:
        raise ValueError('Optimizer update count does not match token budget')
    positions = {key:0 for key in rows}
    for index, update in enumerate(updates):
        if update['index'] != index or update['supervised_tokens'] != per_update:
            raise ValueError('Update index or token count mismatch')
        tokens = 0
        for window in update['microbatches']:
            row = rows.get(window['id'])
            if row is None or window['answer_start'] != positions[row['id']]:
                raise ValueError('Missing row or overlapping/gapped answer exposure')
            count = window['answer_end']-window['answer_start']
            if count != window['supervised_tokens'] or not math.isclose(window['loss_weight'], count/per_update, rel_tol=1e-12):
                raise ValueError('Loss must be weighted by supervised-token count')
            window_labels(row, window)
            positions[row['id']] += count
            tokens += count
        if tokens != per_update:
            raise ValueError('Incomplete effective batch')
    if sum(positions.values()) != budget or any(positions[key] != row['supervised_tokens'] for key,row in rows.items()):
        raise ValueError('Exposure does not exactly cover the frozen budget')
    return rows


def trim_generation(ids, eos_ids, max_new_tokens):
    """Trim only the generated suffix, including its first EOS if present."""
    ids = list(ids)
    eos_ids = {int(value) for value in eos_ids if value is not None}
    for index, token in enumerate(ids):
        if int(token) in eos_ids:
            return ids[:index+1], False
    return ids, len(ids) >= max_new_tokens
