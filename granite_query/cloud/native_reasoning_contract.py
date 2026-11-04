"""Pure, separately versioned contracts for complete native reasoning targets.

No import or function reads datasets, downloads a tokenizer, launches work, or
scores model answers.  The historical concise and depth-pilot contracts remain
unchanged.  Prefix and suffix are intentionally tokenized independently: their
concatenation must decode exactly, but need not equal full-string BPE encoding.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
import unicodedata

VERSION = 'native-reasoning-whole-targets16k-v1'
ENCODER_VERSION = 'native-open-explicit-boundary-v2'
MODEL = 'ibm-granite/granite-4.2-3b'
REVISION = '4e9c275e232f10211ec88644d106a1f6a1b60e06'
PREFIX = ('Solve the math problem. Explain only the necessary calculation steps concisely. '
          'Finish with #### followed by the numeric final answer.\n\n')
TEACHER_MODEL = 'deepseek-v4-pro'
MODES = ('concise', 'thinking')
CAPS = {'concise': 1024, 'thinking': 4096}
CONTEXT = 4096
TOKEN_BUDGET = 16384
TOKENS_PER_UPDATE = 1024
OPTIMIZER_UPDATES = 16
SEED = 42
CANDIDATE_COUNT = 256
DEVELOPMENT_COUNT = 200
DEVELOPMENT_SOURCE_SHA256 = 'cccdce864d728e6b43d9d4de866e719bfd9c706cc735a3a3d429095835c767c7'
DEVELOPMENT_PROJECTION_SHA256 = '2c263186467ff38c961625ec13fc8adad308e431aaaa297dd1c57e7d8595197a'
DEVELOPMENT_IDS_SHA256 = '31a74ef8b0f877e7b544d4b9afd274d381233c25e5084af03d98a091f370a2b5'
TEMPLATE_SHA = 'f0ba43f79b3cabca5e5a7584c77aec92f49feae45cdf7779c87d9fc54cd90258'
TOKENIZER = {
    'model': MODEL, 'revision': REVISION, 'chat_template_sha256': TEMPLATE_SHA,
    'backend_sha256': 'ea0abe115d2928a025701b521d950e11b578be3fc4f32bd0c1aaa9060e48a9a5',
    'transformers_version': '4.57.1', 'eos_token': '<|im_end|>', 'eos_token_id': 100257,
}
CONTROL_STRINGS = ('<|im_start|>', '<|im_end|>', '<think>', '</think>', '<s>', '</s>', '<unk>')
OPEN_TAIL = '<|im_start|>assistant\n<think>\n'
_HEX = re.compile(r'[0-9a-f]{64}\Z')
_ID = re.compile(r'gsm8k:train:[0-9]{5}\Z')


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def sha(raw):
    if not isinstance(raw, bytes):
        raise TypeError('sha requires exact bytes, not a filename or implicit encoding')
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(canonical(value).encode('utf-8'))


def protocol():
    """Fresh JSON settings; role-specific budgets and input hashes are separate."""
    return {
        'version': VERSION, 'encoder_version': ENCODER_VERSION,
        'model': MODEL, 'revision': REVISION, 'seed': SEED,
        'prefix': PREFIX, 'prefix_sha256': sha(PREFIX.encode('utf-8')),
        'tokenizer': dict(TOKENIZER), 'context_limit': CONTEXT,
        'study_token_budget': TOKEN_BUDGET, 'tokens_per_update': TOKENS_PER_UPDATE,
        'study_optimizer_updates': OPTIMIZER_UPDATES,
        'learning_rate': 2e-5, 'lora_r': 8, 'lora_alpha': 16, 'lora_dropout': 0.0,
        'target_modules': ['q_proj', 'v_proj'], 'optimizer': 'AdamW',
        'adam_betas': [0.9, 0.999], 'adam_eps': 1e-8, 'weight_decay': 0.01,
        'gradient_clip_norm': 1.0, 'scheduler': None,
        'base_dtype': 'bfloat16', 'adapter_dtype': 'float32',
        'enable_thinking': True, 'generation_prefix': 'native_open_thinking',
        'max_new_tokens': 1024, 'do_sample': False, 'evaluation_batch_size': 8,
        'input_limit': 1536, 'evaluation_kind': 'development',
        'development_count': DEVELOPMENT_COUNT,
        'development_source_sha256': DEVELOPMENT_SOURCE_SHA256,
        'development_projection_sha256': DEVELOPMENT_PROJECTION_SHA256,
        'development_ids_sha256': DEVELOPMENT_IDS_SHA256,
        'candidate_count': CANDIDATE_COUNT,
        'fresh_base': True, 'data_repetition': False, 'official_test_used': False,
        'selection_policy': 'sha256(seed,id) order; first-reached exact whole-target subset sum',
        'loss_policy': 'Complete suffix plus one EOS once; prefix/padding masked; full causal input per window',
        'estimand': 'Supervision recipe under equal loss tokens; not equal examples, forwarded compute, or pure depth causality',
    }


def tokenizer_identity(tokenizer):
    """Inspect only an already loaded tokenizer; require its exact frozen bits."""
    template = tokenizer.chat_template
    if not isinstance(template, str):
        raise ValueError('Tokenizer template must be a single pinned string')
    actual = {
        'model': MODEL, 'revision': REVISION,
        'chat_template_sha256': sha(template.encode('utf-8')),
        'backend_sha256': sha(tokenizer.backend_tokenizer.to_str().encode('utf-8')),
        'transformers_version': importlib.metadata.version('transformers'),
        'eos_token': tokenizer.eos_token, 'eos_token_id': tokenizer.eos_token_id,
    }
    if actual != TOKENIZER:
        raise ValueError('Loaded tokenizer/backend/template/version/EOS differs from frozen native contract')
    return actual


def _int(value, *, minimum=0):
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _train_row(row):
    if not isinstance(row, dict) or row.get('source_split') != 'train' or not _ID.fullmatch(str(row.get('id', ''))):
        raise ValueError('Require canonical GSM8K TRAIN identity')
    if not isinstance(row.get('prompt'), str) or not row['prompt'].strip():
        raise ValueError('Missing exact training prompt')
    if row.get('official_test_used', False) is not False or row.get('training_eligible', True) is not True:
        raise ValueError('Official or development-only records cannot be teaching inputs')
    if row.get('cohort_role') in ('development', 'holdout', 'selection_development'):
        raise ValueError('Development records cannot be teaching inputs')
    if any(control in row['prompt'] for control in CONTROL_STRINGS):
        raise ValueError('Prompt contains a reserved serialization delimiter')


def _encoding(row, mode, reasoning, content, tokenizer):
    _train_row(row)
    if mode not in MODES or not isinstance(reasoning, str) or not isinstance(content, str) or not content.strip():
        raise ValueError('Require known mode and nonempty visible content')
    if (mode == 'concise' and reasoning) or (mode == 'thinking' and not reasoning.strip()):
        raise ValueError('Reasoning channel does not match the declared treatment')
    if any(control in text for text in (reasoning, content) for control in CONTROL_STRINGS):
        raise ValueError('Original channel contains a reserved serialization delimiter')
    if tokenizer.eos_token != TOKENIZER['eos_token'] or tokenizer.eos_token_id != TOKENIZER['eos_token_id']:
        raise ValueError('Native EOS differs')
    prefix = tokenizer.apply_chat_template([{'role': 'user', 'content': PREFIX + row['prompt']}],
        tokenize=False, add_generation_prompt=True, enable_thinking=True)
    if not isinstance(prefix, str) or not prefix.endswith(OPEN_TAIL):
        raise ValueError('Unexpected OPEN native generation prefix')
    suffix = (reasoning + '\n' if mode == 'thinking' else '') + '</think>\n' + content
    prefix_ids = list(tokenizer.encode(prefix, add_special_tokens=False))
    suffix_ids = list(tokenizer.encode(suffix, add_special_tokens=False)) + [tokenizer.eos_token_id]
    ids = prefix_ids + suffix_ids
    if not prefix_ids or any(not _int(token) for token in ids):
        raise ValueError('Require nonnegative, unpadded tokenizer IDs')
    decoded = tokenizer.decode(ids, skip_special_tokens=False, clean_up_tokenization_spaces=False)
    if decoded != prefix + suffix + tokenizer.eos_token:
        raise ValueError('Explicit-boundary encoding does not preserve original text')
    if tokenizer.eos_token_id in suffix_ids[:-1]:
        raise ValueError('Supervised target must contain exactly one terminal EOS')
    return {
        'encoder_version': ENCODER_VERSION, 'mode': mode,
        'reasoning_content': reasoning, 'content': content, 'response': content,
        'input_ids': ids, 'attention_mask': [1] * len(ids),
        'labels': [-100] * len(prefix_ids) + suffix_ids,
        'prefix_tokens': len(prefix_ids), 'supervised_tokens': len(suffix_ids),
        'full_response_tokens': len(suffix_ids), 'context_tokens': len(ids),
        'context_fit': len(ids) <= CONTEXT,
        'reasoning_tokens': len(tokenizer.encode(reasoning, add_special_tokens=False)),
        'visible_content_tokens': len(tokenizer.encode(content, add_special_tokens=False)),
        'prefix_ids_sha256': digest(prefix_ids), 'target_ids_sha256': digest(suffix_ids),
        'target_text_sha256': sha(suffix.encode('utf-8')),
        'original_reasoning_sha256': sha(reasoning.encode('utf-8')),
        'original_content_sha256': sha(content.encode('utf-8')),
        'prompt_sha256': sha(row['prompt'].encode('utf-8')), 'trace_truncated': False,
    }


def encode_target(row, mode, reasoning, content, tokenizer):
    """Return a complete row; retain original channels even when over context.

    The concise target deliberately closes an empty span after the same OPEN
    prefix used for thinking.  This is not the template's full-chat empty-span
    rendering.  No eligibility, arithmetic, or intermediate-step claim is made.
    """
    return dict(row, **_encoding(row, mode, reasoning, content, tokenizer))


def validate_encoding(row, tokenizer):
    expected = _encoding(row, row.get('mode'), row.get('reasoning_content'), row.get('content'), tokenizer)
    if any(row.get(key) != value for key, value in expected.items()):
        raise ValueError('Saved encoding or original-channel binding differs')
    _structure(row)
    return row


def _structure(row):
    _train_row(row)
    prefix, total = row.get('prefix_tokens'), row.get('supervised_tokens')
    ids = row.get('input_ids')
    if (row.get('mode') not in MODES or not isinstance(ids, list)
            or not _int(prefix, minimum=1) or not _int(total, minimum=1)
            or len(ids) != prefix + total or len(ids) > CONTEXT
            or any(not _int(value) for value in ids)):
        raise ValueError('Incomplete target lengths, mode, or context')
    suffix = ids[prefix:]
    if (row.get('full_response_tokens') != total or row.get('context_tokens') != len(ids)
            or row.get('context_fit') is not True or row.get('trace_truncated') is not False
            or digest(row.get('labels')) != digest([-100] * prefix + suffix)
            or digest(row.get('attention_mask')) != digest([1] * len(ids))
            or suffix[-1] != TOKENIZER['eos_token_id'] or TOKENIZER['eos_token_id'] in suffix[:-1]
            or row.get('prefix_ids_sha256') != digest(ids[:prefix])
            or row.get('target_ids_sha256') != digest(suffix)):
        raise ValueError('Target must be complete, unpadded, bound, and end in one supervised EOS')
    if row.get('finish_reason') != 'stop' or row.get('truncated') is not False or row.get('verified_final_answer') is not True:
        raise ValueError('Teaching target lacks explicit complete, verified final-answer qualification')
    if row.get('encoder_version') != ENCODER_VERSION:
        raise ValueError('Unknown native encoder version')
    for channel, key in (('reasoning_content', 'original_reasoning_sha256'), ('content', 'original_content_sha256'), ('prompt', 'prompt_sha256')):
        text = row.get(channel)
        if not isinstance(text, str) or row.get(key) != sha(text.encode('utf-8')):
            raise ValueError('Original text/channel hash differs')
    if (not row['content'].strip() or row.get('response') != row['content']
            or (row['mode'] == 'thinking' and not row['reasoning_content'].strip())
            or (row['mode'] == 'concise' and row['reasoning_content'])):
        raise ValueError('Mode does not preserve its complete original channels')
    suffix_text = (row['reasoning_content'] + '\n' if row['mode'] == 'thinking' else '') + '</think>\n' + row['content']
    if row.get('target_text_sha256') != sha(suffix_text.encode('utf-8')):
        raise ValueError('Serialized native target text hash differs')
    if any(control in text for text in (row['reasoning_content'], row['content']) for control in CONTROL_STRINGS):
        raise ValueError('Reserved channel delimiter')


def _unique(rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError('Require a nonempty row list')
    for row in rows:
        _structure(row)
    if (len({row['id'] for row in rows}) != len(rows) or len({row['mode'] for row in rows}) != 1
            or len({_normalized(row['prompt']) for row in rows}) != len(rows)):
        raise ValueError('One treatment and unique question IDs/normalized prompts required')


def _hash_order(rows, seed):
    return sorted(sorted(rows, key=lambda row: row['id']),
        key=lambda row: (digest({'seed': seed, 'id': row['id']}), row['id']))


def select_whole_targets(rows, budget=TOKEN_BUDGET, seed=SEED):
    """Deterministic exact subset sum of complete targets, without replacements."""
    _unique(rows)
    if not _int(budget, minimum=1) or not _int(seed):
        raise ValueError('Positive integer budget and nonnegative integer seed required')
    ordered = _hash_order(rows, seed)
    mask, reachable, previous = (1 << (budget + 1)) - 1, 1, {}
    for index, row in enumerate(ordered):
        length = row['supervised_tokens']
        if length > budget:
            continue
        newly = ((reachable << length) & mask) & ~reachable
        remaining = newly
        while remaining:
            low = remaining & -remaining
            value = low.bit_length() - 1
            previous[value] = (value - length, index)
            remaining -= low
        reachable |= newly
        if (reachable >> budget) & 1:
            break
    if not (reachable >> budget) & 1:
        raise ValueError('No exact whole-target capacity; changing budget or repeating/slicing needs a new protocol')
    selected, position = set(), budget
    while position:
        position, index = previous[position]
        if index in selected:
            raise AssertionError('Subset sum attempted repeated target')
        selected.add(index)
    result = [row for index, row in enumerate(ordered) if index in selected]
    if sum(row['supervised_tokens'] for row in result) != budget:
        raise AssertionError('Subset sum reconstruction differs')
    return result


def exposure_windows(rows, tokens_per_update=TOKENS_PER_UPDATE):
    """Cover every complete suffix once, keeping full causal inputs per window."""
    _unique(rows)
    total = sum(row['supervised_tokens'] for row in rows)
    if not _int(tokens_per_update, minimum=1) or total % tokens_per_update:
        raise ValueError('All suffix tokens must fill whole effective updates; no dropped tail')
    updates, windows, used = [], [], 0
    for row in rows:
        position = 0
        while position < row['supervised_tokens']:
            count = min(tokens_per_update - used, row['supervised_tokens'] - position)
            windows.append({'id': row['id'], 'answer_start': position, 'answer_end': position + count,
                'supervised_tokens': count, 'loss_weight': count / tokens_per_update})
            position += count
            used += count
            if used == tokens_per_update:
                updates.append({'index': len(updates), 'supervised_tokens': used, 'microbatches': windows})
                windows, used = [], 0
    if used or windows:
        raise AssertionError('Unexposed tail')
    return updates


def window_labels(row, window):
    _structure(row)
    start, end, count = (window.get(key) for key in ('answer_start', 'answer_end', 'supervised_tokens'))
    if (window.get('id') != row['id'] or not _int(start) or not _int(end, minimum=1)
            or not _int(count, minimum=1) or not 0 <= start < end <= row['supervised_tokens'] or count != end - start):
        raise ValueError('Invalid complete-target exposure window')
    labels = [-100] * len(row['input_ids'])
    offset = row['prefix_tokens']
    labels[offset + start:offset + end] = row['input_ids'][offset + start:offset + end]
    return labels


def _projection(rows):
    try:
        return [{key: row[key] for key in ('id', 'prompt', 'gold_answer', 'source_split')} for row in rows]
    except (KeyError, TypeError):
        raise ValueError('Development identity projection is incomplete') from None


def _normalized(text):
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


def validate_bundle(data, plan):
    """Validate pure bytes/identity/mask contracts; runtime re-encodes separately.

    Input data binds receipt manifests but cannot prove their upstream truth by
    itself. The reviewed controller must verify those original files. Runtime
    must inspect tokenizer_identity and call validate_encoding before loading a
    model. This helper never reads official-test files or any source file.
    """
    if not isinstance(data, dict) or not isinstance(plan, dict):
        raise ValueError('Object data and plan required')
    expected = protocol()
    if any(key not in plan or digest(plan[key]) != digest(value) for key, value in expected.items()):
        raise ValueError('Plan changes a frozen native study setting')
    if plan.get('input_sha256') != digest(data) or plan.get('protocol_hash') != digest({key: value for key, value in plan.items() if key != 'protocol_hash'}):
        raise ValueError('Input or full plan hash differs')
    if not isinstance(plan.get('run_id'), str) or not re.fullmatch(r'[A-Za-z0-9_\-]{1,160}', plan['run_id']):
        raise ValueError('Safe immutable run identity required')
    bindings = data.get('bindings')
    if (not isinstance(bindings, dict) or any(not _HEX.fullmatch(str(bindings.get(key, ''))) for key in
            ('collection_plan_sha256', 'eligible_pairs_sha256', 'teacher_receipt_inventory_sha256'))
            or plan.get('bindings_sha256') != digest(bindings)):
        raise ValueError('Missing paired-source/receipt bindings')
    dev = data.get('development')
    if not isinstance(dev, list) or len(dev) != DEVELOPMENT_COUNT:
        raise ValueError('Require all fixed200 development questions')
    projection = _projection(dev)
    ids = [row['id'] for row in projection]
    if (len(set(ids)) != DEVELOPMENT_COUNT or digest(ids) != DEVELOPMENT_IDS_SHA256
            or digest(projection) != DEVELOPMENT_PROJECTION_SHA256
            or any(row['source_split'] != 'train' for row in projection)):
        raise ValueError('Exact ordered human TRAIN development payload changed')
    if any(row.get('official_test_used', False) is not False for row in dev):
        raise ValueError('Official test flags forbidden')
    role = plan.get('arm')
    arm = data.get('arm')
    if role == 'baseline':
        if (plan.get('mode') != 'evaluate_base' or arm is not None
                or plan.get('token_budget') != 0 or plan.get('optimizer_updates') != 0):
            raise ValueError('Baseline must be a fresh untouched base with zero teaching')
        return {}
    if role not in MODES or plan.get('mode') != 'train_evaluate' or not isinstance(arm, dict):
        raise ValueError('Semantic treatment identity or worker mode differs')
    if (plan.get('token_budget') != TOKEN_BUDGET or plan.get('optimizer_updates') != OPTIMIZER_UPDATES
            or arm.get('arm') != role or arm.get('token_budget') != TOKEN_BUDGET
            or arm.get('tokens_per_update') != TOKENS_PER_UPDATE or arm.get('optimizer_updates') != OPTIMIZER_UPDATES
            or arm.get('tokenizer') != TOKENIZER):
        raise ValueError('Training role, tokens, updates, or tokenizer binding differs')
    rows = arm.get('training')
    _unique(rows)
    if len(rows) > CANDIDATE_COUNT or any(row['mode'] != role for row in rows):
        raise ValueError('Too many teaching questions or mixed semantic treatment')
    if sum(row['supervised_tokens'] for row in rows) != TOKEN_BUDGET:
        raise ValueError('Require exact complete-target budget without repeats')
    if [row['id'] for row in rows] != [row['id'] for row in _hash_order(rows, SEED)]:
        raise ValueError('Selected targets must retain the frozen shared hash order')
    dev_prompts = {_normalized(row['prompt']) for row in projection}
    if any(row['id'] in set(ids) or _normalized(row['prompt']) in dev_prompts for row in rows):
        raise ValueError('Teaching overlaps fixed development IDs or normalized questions')
    if arm.get('updates') != exposure_windows(rows):
        raise ValueError('Exposure windows omit, repeat, reorder, or misweight complete target positions')
    return {row['id']: row for row in rows}


def validate(plan, data):
    """Worker-friendly argument-order alias."""
    return validate_bundle(data, plan)
