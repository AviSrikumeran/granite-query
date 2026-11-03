"""Unpaid boundary/recovery checks for the bounded teaching collector."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import student_pool as pool
from test_prepare_verified_math import TinyTokenizer


class StudentPoolTests(unittest.TestCase):
    def test_exact_common_user_text_and_no_gold_in_paid_payload(self):
        row = {'id': 'gsm8k:train:00001', 'prompt': 'How many apples?',
               'gold_answer': 'PRIVATE-GOLD', 'reference_solution': 'PRIVATE-REFERENCE'}
        payload = pool.build_payload(row)
        self.assertEqual(payload['messages'], [{'role': 'user', 'content': pool.PREFIX + row['prompt']}])
        self.assertEqual(payload['max_tokens'], 1024)
        self.assertEqual(payload['thinking'], {'type': 'disabled'})
        self.assertNotIn('PRIVATE', json.dumps(payload))
        self.assertLess(pool.WORST_CASE_USD, pool.RESERVATION_USD)

    def test_wrong_or_incomplete_responses_are_retained_but_not_eligible(self):
        base = {'id': 'x', 'prompt': '3 plus 4?', 'gold_answer': '7',
                'teacher_model': pool.MODEL, 'teacher_revision': pool.MODEL,
                'finish_reason': 'stop', 'response': '3 plus 4 is 7.\n#### 7',
                'generation': {'prompt_version': pool.PROMPT_VERSION, 'settings': {}}}
        okay = pool.verify(base, TinyTokenizer())
        self.assertTrue(okay['eligible'])
        self.assertEqual(okay['response'], base['response'])
        wrong = pool.verify(dict(base, response='3 plus 4 is 8.\n#### 8'), TinyTokenizer())
        self.assertFalse(wrong['eligible'])
        self.assertIn('#### 8', wrong['response'])
        incomplete = pool.verify(dict(base, finish_reason='length', truncated=True), TinyTokenizer())
        self.assertFalse(incomplete['eligible'])
        self.assertTrue(incomplete['trace_truncated'])
        long = pool.verify(dict(base, response=('word ' * 800) + '\n#### 7'), TinyTokenizer())
        self.assertFalse(long['eligible'])
        self.assertEqual(long['verification'], 'response_too_long')
        self.assertGreater(len(long['response']), 3900)

    def test_durable_receipt_recovery_and_zero_duplicate_requests(self):
        parent = pool.ROOT / '.test_work'
        parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as temporary:
            root = Path(temporary)
            rows = [{'id': 'gsm8k:train:00001', 'prompt': '3 plus 4?', 'gold_answer': '7',
                     'source_split': 'train'}]
            requests = [{'id': rows[0]['id'], 'payload': pool.build_payload(rows[0])}]
            plan = {'candidate_count': 1, 'candidates_sha256': pool._digest(rows),
                    'requests_sha256': pool._digest(requests), 'budget_job_id': pool.JOB_ID}
            pool._write(root / 'plan.json', plan)
            pool.write_jsonl(root / 'candidates.jsonl', rows)
            pool.write_jsonl(root / 'requests.jsonl', requests)
            raw = {'model': pool.MODEL, 'choices': [{'finish_reason': 'stop',
                   'message': {'content': '3 plus 4 is 7.\n#### 7'}}],
                   'usage': {'prompt_tokens': 30, 'completion_tokens': 12}}
            with patch.object(pool, 'assert_reserved'), \
                 patch.object(pool, 'load_tokenizer', return_value=TinyTokenizer()), \
                 patch.object(pool, 'credential', return_value='fake-for-local-test'), \
                 patch.object(pool.urllib.request, 'urlopen', side_effect=lambda *a, **k: io.BytesIO(json.dumps(raw).encode())) as call:
                first = pool.collect(root, 1)
                second = pool.collect(root, 1)
                self.assertEqual(call.call_count, 1)
                self.assertEqual(first['eligible'], 1)
                self.assertEqual(second['eligible'], 1)
                # Simulate crash after per-attempt receipt, before aggregate append.
                (root / 'teacher_results.jsonl').unlink()
                recovered = pool.collect(root, 1)
                self.assertEqual(recovered['eligible'], 1)
                self.assertEqual(call.call_count, 1)
                (root / 'teacher_results.jsonl').unlink()
                _, saved = pool._attempt_paths(root, rows[0]['id'])
                saved.unlink()
                with self.assertRaisesRegex(RuntimeError, 'Ambiguous'):
                    pool.collect(root, 1)
                self.assertEqual(call.call_count, 1)

    def test_account_failure_halts_unattempted_rows(self):
        parent = pool.ROOT / '.test_work'
        parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as temporary:
            root = Path(temporary)
            rows = [{'id': f'gsm8k:train:{i:05d}', 'prompt': '3 plus 4?', 'gold_answer': '7',
                     'source_split': 'train'} for i in range(8)]
            requests = [{'id': row['id'], 'payload': pool.build_payload(row)} for row in rows]
            pool._write(root / 'plan.json', {'candidate_count': len(rows),
                'candidates_sha256': pool._digest(rows), 'requests_sha256': pool._digest(requests)})
            pool.write_jsonl(root / 'candidates.jsonl', rows)
            pool.write_jsonl(root / 'requests.jsonl', requests)
            error = pool.urllib.error.HTTPError(pool.API_URL, 402, 'no credit', {}, None)
            with patch.object(pool, 'assert_reserved'), \
                 patch.object(pool, 'load_tokenizer', return_value=TinyTokenizer()), \
                 patch.object(pool, 'credential', return_value='fake-for-local-test'), \
                 patch.object(pool.urllib.request, 'urlopen', side_effect=error) as call:
                summary = pool.collect(root, 1)
                self.assertEqual(call.call_count, 1)
                self.assertEqual(summary['completed'], 1)
                self.assertEqual(summary['stage'], 'halted')
                self.assertEqual(summary['halt_reason'], 'provider_http_402')


if __name__ == '__main__':
    unittest.main()
