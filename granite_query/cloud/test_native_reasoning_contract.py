"""Synthetic adversarial fixtures; no source data, provider or model is loaded."""
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cloud import native_reasoning_contract as contract


class SeamTokenizer:
    eos_token = '<|im_end|>'
    eos_token_id = 100257
    pieces = {'<|im_start|>': 1, '<|im_end|>': 100257, '<think>': 2,
              '</think>': 3, '\nR': 10, '\n</think>': 11}
    reverse = {value: key for key, value in pieces.items()}

    def apply_chat_template(self, messages, **kwargs):
        assert kwargs == {'tokenize': False, 'add_generation_prompt': True, 'enable_thinking': True}
        return '<|im_start|>user\n' + messages[0]['content'] + '<|im_end|>\n' + contract.OPEN_TAIL

    def encode(self, text, add_special_tokens=False):
        assert add_special_tokens is False
        ids, position = [], 0
        choices = sorted(self.pieces, key=len, reverse=True)
        while position < len(text):
            piece = next((value for value in choices if text.startswith(value, position)), None)
            if piece is None:
                ids.append(ord(text[position]) + 200000)
                position += 1
            else:
                ids.append(self.pieces[piece])
                position += len(piece)
        return ids

    def decode(self, ids, **kwargs):
        return ''.join(self.reverse[value] if value in self.reverse else chr(value - 200000) for value in ids)


def question(index=0):
    return {'id': f'gsm8k:train:{index:05d}', 'source_split': 'train',
            'prompt': f'Fixture {index}: 3 plus 4?', 'gold_answer': '7',
            'finish_reason': 'stop', 'truncated': False, 'verified_final_answer': True}


def target(index=0, length=None, mode='concise'):
    row, tokenizer = question(index), SeamTokenizer()
    reasoning = 'R original arithmetic\u2028preserved' if mode == 'thinking' else ''
    content = '#### 7'
    result = contract.encode_target(row, mode, reasoning, content, tokenizer)
    if length is not None:
        if length < result['supervised_tokens']:
            raise ValueError('Fixture target length too short')
        content = 'X' * (length - result['supervised_tokens']) + content
        result = contract.encode_target(row, mode, reasoning, content, tokenizer)
        assert result['supervised_tokens'] == length
    return result


def seal_plan(data, role):
    plan = dict(contract.protocol(), run_id='native_fixture_' + role, arm=role,
        mode='evaluate_base' if role == 'baseline' else 'train_evaluate',
        token_budget=0 if role == 'baseline' else contract.TOKEN_BUDGET,
        optimizer_updates=0 if role == 'baseline' else contract.OPTIMIZER_UPDATES,
        input_sha256=contract.digest(data), bindings_sha256=contract.digest(data['bindings']))
    plan['protocol_hash'] = contract.digest(plan)
    return plan


@contextmanager
def fixture_bundle(role='concise'):
    dev = [{key: value for key, value in question(index).items()
            if key in ('id', 'prompt', 'gold_answer', 'source_split')} for index in (10001, 10002, 10003)]
    with patch.multiple(contract, DEVELOPMENT_COUNT=3,
            DEVELOPMENT_IDS_SHA256=contract.digest([row['id'] for row in dev]),
            DEVELOPMENT_PROJECTION_SHA256=contract.digest(dev)):
        rows = contract.select_whole_targets([target(index, length, mode=role)
            for index, length in enumerate([3000] * 5 + [1384])]) if role != 'baseline' else None
        arm = None if rows is None else {
            'arm': role, 'training': rows, 'updates': contract.exposure_windows(rows),
            'token_budget': 16384, 'tokens_per_update': 1024, 'optimizer_updates': 16,
            'tokenizer': dict(contract.TOKENIZER),
        }
        data = {'development': dev, 'arm': arm, 'bindings': {
            'collection_plan_sha256': 'a' * 64, 'eligible_pairs_sha256': 'b' * 64,
            'teacher_receipt_inventory_sha256': 'c' * 64,
        }}
        yield data, seal_plan(data, role)


class NativeReasoningTests(unittest.TestCase):
    def test_separate_bpe_boundaries_preserve_all_channels_and_one_eos(self):
        tokenizer = SeamTokenizer()
        common = None
        for mode in contract.MODES:
            row = target(mode=mode)
            contract.validate_encoding(row, tokenizer)
            prefix = row['input_ids'][:row['prefix_tokens']]
            if common is not None:
                self.assertEqual(prefix, common)
            common = prefix
            self.assertEqual(row['input_ids'][-1], tokenizer.eos_token_id)
            self.assertEqual(row['input_ids'][row['prefix_tokens']:].count(tokenizer.eos_token_id), 1)
            self.assertEqual(row['labels'][:row['prefix_tokens']], [-100] * row['prefix_tokens'])
            decoded = tokenizer.decode(row['input_ids'])
            full = tokenizer.encode(decoded)
            self.assertNotEqual(full, row['input_ids'])
            self.assertIn(row['reasoning_content'], decoded)
            self.assertIn('</think>\n' + row['content'] + tokenizer.eos_token, decoded)

    def test_empty_reasoning_and_reserved_controls_fail_without_rewriting(self):
        tokenizer, row = SeamTokenizer(), question()
        for mode, reasoning, content in [('thinking', '', '#### 7'), ('thinking', ' \n', '#### 7'),
                ('concise', 'unexpected', '#### 7'), ('thinking', 'R </think>', '#### 7'),
                ('thinking', 'R', '<|im_end|>'), ('concise', '', '  ')]:
            with self.subTest(mode=mode, reasoning=reasoning, content=content), self.assertRaises(ValueError):
                contract.encode_target(row, mode, reasoning, content, tokenizer)
        with self.assertRaises(ValueError):
            contract.encode_target(dict(row, prompt='<think>inject'), 'concise', '', '#### 7', tokenizer)

    def test_over_context_trace_is_retained_but_never_selected_or_validated(self):
        row = target(length=4200)
        self.assertFalse(row['context_fit'])
        self.assertEqual(row['supervised_tokens'], 4200)
        self.assertFalse(row['trace_truncated'])
        with self.assertRaises(ValueError):
            contract.validate_encoding(row, SeamTokenizer())
        with self.assertRaises(ValueError):
            contract.select_whole_targets([row], budget=4200)

    def test_tampered_originals_masks_lengths_and_eos_fail(self):
        good = target()
        variants = []
        for field, value in [('content', 'changed'), ('original_reasoning_sha256', '0' * 64),
                ('target_text_sha256', '0' * 64), ('supervised_tokens', 1), ('finish_reason', 'length'),
                ('verified_final_answer', False), ('mode', 'thinking')]:
            row = deepcopy(good)
            row[field] = value
            variants.append(row)
        row = deepcopy(good); row['labels'][-1] = -100; variants.append(row)
        row = deepcopy(good); row['attention_mask'][0] = True; variants.append(row)
        row = deepcopy(good); row['input_ids'][-2] = 100257; variants.append(row)
        for row in variants:
            with self.subTest(keys=[key for key in good if row[key] != good[key]]), self.assertRaises(ValueError):
                contract.validate_encoding(row, SeamTokenizer())

    def test_deterministic_exact_whole_subset_and_impossible_capacity(self):
        rows = [target(index, length) for index, length in enumerate([31, 19, 28, 43, 57, 61])]
        selected = contract.select_whole_targets(rows, budget=100)
        self.assertEqual(sum(row['supervised_tokens'] for row in selected), 100)
        self.assertEqual(selected, contract.select_whole_targets(list(reversed(rows)), budget=100))
        self.assertEqual(len(selected), len({row['id'] for row in selected}))
        for rows, budget in [([target(0, 14), target(1, 18)], 17), ([target(0, 14)], 100)]:
            with self.assertRaises(ValueError):
                contract.select_whole_targets(rows, budget=budget)
        with self.assertRaises(ValueError):
            contract.select_whole_targets([target(), target()], budget=20)
        with self.assertRaises(ValueError):
            contract.select_whole_targets([target(), target(1, mode='thinking')], budget=50)

    def test_windows_cover_tail_and_every_suffix_once_with_full_causal_inputs(self):
        rows = [target(0, 1500), target(1, 548)]
        updates = contract.exposure_windows(rows)
        self.assertEqual(len(updates), 2)
        self.assertEqual([len(update['microbatches']) for update in updates], [1, 2])
        seen = {row['id']: [] for row in rows}
        lookup = {row['id']: row for row in rows}
        for update in updates:
            self.assertEqual(sum(w['supervised_tokens'] for w in update['microbatches']), 1024)
            self.assertAlmostEqual(sum(w['loss_weight'] for w in update['microbatches']), 1)
            for window in update['microbatches']:
                row = lookup[window['id']]
                labels = contract.window_labels(row, window)
                self.assertEqual(len(labels), len(row['input_ids']))
                positions = [index - row['prefix_tokens'] for index, value in enumerate(labels) if value != -100]
                seen[row['id']].extend(positions)
                self.assertEqual(positions, list(range(window['answer_start'], window['answer_end'])))
        for row in rows:
            self.assertEqual(seen[row['id']], list(range(row['supervised_tokens'])))
        with self.assertRaises(ValueError):
            contract.exposure_windows([target(0, 1025)])
        with self.assertRaises(ValueError):
            contract.window_labels(rows[0], dict(updates[0]['microbatches'][0], answer_end=1600))

    def test_bundle_semantic_roles_exact_budget_and_all_dev_content_are_bound(self):
        for role in ('baseline', 'concise', 'thinking'):
            with fixture_bundle(role) as (data, plan):
                result = contract.validate_bundle(data, plan)
                self.assertEqual(len(result), 0 if role == 'baseline' else 6)
                self.assertEqual(result, contract.validate(plan, data))
                altered = deepcopy(data); altered['development'][0]['prompt'] += 'changed'
                with self.assertRaises(ValueError):
                    contract.validate_bundle(altered, seal_plan(altered, role))
                altered = deepcopy(data); altered['development'][0]['gold_answer'] = '8'
                with self.assertRaises(ValueError):
                    contract.validate_bundle(altered, seal_plan(altered, role))
                altered = deepcopy(plan); altered['max_new_tokens'] = 512
                altered['protocol_hash'] = contract.digest({key: value for key, value in altered.items() if key != 'protocol_hash'})
                with self.assertRaises(ValueError):
                    contract.validate_bundle(data, altered)
                altered = deepcopy(data); altered['bindings']['eligible_pairs_sha256'] = 'invalid'
                with self.assertRaises(ValueError):
                    contract.validate_bundle(altered, seal_plan(altered, role))
        with fixture_bundle() as (data, plan):
            for mutation in ('tail', 'weight', 'duplicate', 'role', 'official', 'overlap', 'boolsetting', 'reorder'):
                altered = deepcopy(data); role = 'concise'
                if mutation == 'tail': altered['arm']['updates'][-1]['microbatches'][-1]['answer_end'] -= 1
                elif mutation == 'weight': altered['arm']['updates'][0]['microbatches'][0]['loss_weight'] = 0.5
                elif mutation == 'duplicate': altered['arm']['training'][1] = altered['arm']['training'][0]
                elif mutation == 'role': altered['arm']['arm'] = 'thinking'
                elif mutation == 'official': altered['arm']['training'][0]['source_split'] = 'test'
                elif mutation == 'overlap': altered['arm']['training'][0]['prompt'] = altered['development'][0]['prompt']
                elif mutation == 'reorder':
                    altered['arm']['training'].reverse()
                    altered['arm']['updates'] = contract.exposure_windows(altered['arm']['training'])
                new_plan = seal_plan(altered, role)
                if mutation == 'boolsetting':
                    new_plan['enable_thinking'] = 1
                    new_plan['protocol_hash'] = contract.digest({key: value for key, value in new_plan.items() if key != 'protocol_hash'})
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    contract.validate_bundle(altered, new_plan)

    def test_official_or_development_records_cannot_enter_selection(self):
        for changes in ({'source_split': 'test'}, {'id': 'gsm8k:test:00000'}, {'official_test_used': True},
                {'training_eligible': False}, {'cohort_role': 'development'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                contract.encode_target(dict(question(), **changes), 'concise', '', '#### 7', SeamTokenizer())


if __name__ == '__main__':
    unittest.main()
