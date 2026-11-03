"""Critical preparation boundaries; no network, weights, GPU or paid API calls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import prepare_verified_math as prep


class TinyTokenizer:
    eos_token = '<eos>'

    def apply_chat_template(self, messages, **kwargs):
        assert kwargs['enable_thinking'] is False
        return messages[0]['content']

    def __call__(self, text, **kwargs):
        assert kwargs['add_special_tokens'] is False
        return {'input_ids': text.split()}


def fixture():
    return {'row_idx': 42, 'truncated_cells': [], 'row': {
        'uuid': 'fixture-uuid', 'problem': 'Ann has 3 cakes and gets 4 cakes. How many cakes?',
        'answer': '7', 'question_type': 'math-word-problem', 'source': 'synthetic_amc',
        'problem_type': 'Algebra', 'generations': [r'<think>3 plus 4 is 7.</think> Therefore \boxed{7}.'],
        'is_reasoning_complete': [True], 'correctness_math_verify': [True], 'finish_reasons': None,
    }}


class PreparationTests(unittest.TestCase):
    def select(self, wrapped=None, **kwargs):
        return prep.eligible_row(wrapped or fixture(), TinyTokenizer(),
                                 max_response_tokens=kwargs.get('max_response_tokens', 768),
                                 context_limit=2048)

    def test_exact_trace_and_explicit_teacher_provenance(self):
        wrapped = fixture()
        row, reason, _ = self.select(wrapped)
        self.assertEqual(reason, 'eligible')
        self.assertEqual(row['response'], wrapped['row']['generations'][0])
        self.assertTrue(row['verified_final_answer'])
        self.assertEqual(row['source_revision'], prep.REVISION)
        self.assertEqual(row['teacher_model'], 'deepseek-ai/DeepSeek-R1')
        self.assertFalse(row['trace_truncated'])
        before = row.pop('record_sha256')
        self.assertEqual(before, prep.digest(prep.canonical(row)))

    def test_rejects_mismatch_truncation_incompletion_and_non_numeric_gold(self):
        for change, expected in [
            ({'answer': '8'}, 'no_short_complete_verified_trace'),
            ({'answer': 'x+1'}, 'not_scalar_numeric_reference'),
            ({'is_reasoning_complete': [False]}, 'no_short_complete_verified_trace'),
            ({'correctness_math_verify': [False]}, 'no_short_complete_verified_trace'),
            ({'finish_reasons': ['length']}, 'no_short_complete_verified_trace'),
        ]:
            wrapped = fixture()
            wrapped['row'].update(change)
            row, reason, _ = self.select(wrapped)
            self.assertIsNone(row)
            self.assertEqual(reason, expected)
        wrapped = fixture()
        wrapped['truncated_cells'] = ['generations']
        self.assertEqual(self.select(wrapped)[1], 'server_truncated_cells')

    def test_shortest_complete_verified_generation_and_no_silent_truncation(self):
        wrapped = fixture()
        original = copy.deepcopy(wrapped)
        row, reason, stats = self.select(wrapped, max_response_tokens=2)
        self.assertIsNone(row)
        self.assertEqual(reason, 'no_short_complete_verified_trace')
        self.assertEqual(stats['generation_rejections']['response_too_long'], 1)
        self.assertEqual(wrapped, original)
        wrapped['row']['generations'].append(r'3+4=7. \boxed{7}')
        wrapped['row']['is_reasoning_complete'].append(True)
        wrapped['row']['correctness_math_verify'].append(True)
        row, _, _ = self.select(wrapped)
        self.assertEqual(row['generation']['generation_index'], 1)

    def test_exclusion_uses_only_training_prompts_and_rejects_test(self):
        folder = prep.ROOT / '.test_work'
        folder.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=folder) as temporary:
            source = Path(temporary) / 'development.jsonl'
            source.write_text(json.dumps({'id': 'x', 'source_split': 'test', 'prompt': 'Secret question'}))
            with self.assertRaisesRegex(ValueError, 'training-split'):
                prep.load_exclusions([source])
            # Refuse a test-named path BEFORE any file open (does not exist).
            with self.assertRaisesRegex(ValueError, 'Official-test'):
                prep.load_exclusions([Path(temporary) / 'official_test.jsonl'])
            source.write_text(json.dumps({'id': 'x', 'source_split': 'train', 'prompt': 'How many cakes?',
                                          'gold_answer': 'deliberately unused'}))
            rows, meta = prep.load_exclusions([source])
            self.assertEqual(rows, [{'id': 'x', 'prompt': 'How many cakes?'}])
            self.assertEqual(meta[0]['rows'], 1)

    def test_dedup_exact_and_near_without_erasing_distinct_numbers(self):
        text = 'Ann has 3 cakes and then buys 4 more cakes from the bakery. How many cakes does Ann have in total?'
        dedup = prep.Deduplicator([{'id': 'dev:1', 'prompt': text}])
        self.assertIn('exact', dedup.match({'prompt': text.upper()})['reason'])
        near = text.replace('total', 'all')
        self.assertIn('near', dedup.match({'prompt': near})['reason'])
        self.assertIsNone(dedup.match({'prompt': text.replace('4', '9')}))

    def test_seeded_blocks_do_not_overlap_and_are_reproducible(self):
        first = prep.sample_offsets(93733, 8, 42, 512)
        self.assertEqual(first, prep.sample_offsets(93733, 8, 42, 512))
        self.assertEqual(len(first), len(set(first)))
        self.assertEqual(len(first), 64)
        self.assertNotEqual(first, prep.sample_offsets(93733, 8, 43, 512))

    def test_live_revision_mismatch_fails_before_reading(self):
        class Response:
            headers = {'x-revision': 'different'}
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self, length):
                raise AssertionError('Must not read mismatched data')
        client = prep.BoundedHTTP(1000, 1000)
        with patch.object(prep.urllib.request, 'urlopen', return_value=Response()):
            with self.assertRaisesRegex(RuntimeError, 'revision mismatch'):
                client.get(prep.block_url(0, 1), revision=prep.REVISION)
        self.assertEqual(client.downloaded_bytes, 0)


if __name__ == '__main__':
    unittest.main()
