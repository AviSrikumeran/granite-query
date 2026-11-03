import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cloud import math_teacher as teacher
from test_prepare_verified_math import TinyTokenizer


def rows():
    return [{'id': f'hfmath:{source}:train:{i}', 'source': source, 'source_split': 'train',
        'prompt': f'3 plus 4? Version {i}', 'gold_answer': '7',
        'reference_type': origin, 'reference_limitation': 'Fixture origin retained'}
        for i in range(3) for source, origin in [('a/svamp', 'human_dataset_answer'),
            ('b/template', 'procedurally_generated_result'), ('c/majority', 'synthetic_majority_vote_answer')]]


class MathTeacherTests(unittest.TestCase):
    def setUp(self):
        parent = teacher.ROOT / 'runs/test_math_teacher'
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def freeze(self, limit=9):
        with patch.object(teacher, 'audit_cohort', return_value=(rows(), {'fixture': True})):
            return teacher.prepare(output=self.root, limit=limit)

    def test_frozen_balanced_requests_exclude_gold_and_preserve_origins(self):
        plan = self.freeze(8)
        requests = teacher.read_rows(self.root / 'requests.jsonl')
        candidates = teacher.read_rows(self.root / 'candidates.jsonl')
        self.assertEqual(len(requests), 8)
        self.assertEqual([row['source'] for row in candidates[:3]], ['a/svamp', 'b/template', 'c/majority'])
        self.assertEqual(len({row['reference_type'] for row in candidates}), 3)
        for request, candidate in zip(requests, candidates):
            self.assertEqual(request['payload']['messages'], [{'role': 'user', 'content': teacher.transport.PREFIX + candidate['prompt']}])
            self.assertNotIn('gold_answer', json.dumps(request))
        self.assertLess(plan['conservative_max_cost_usd'], plan['reserved_usd_required'])
        self.assertEqual(plan['max_attempts'], 8)

    def test_durable_resume_does_not_repeat_paid_request_or_relabel_reference(self):
        self.freeze(2)
        raw = {'model': teacher.transport.MODEL, 'choices': [{'finish_reason': 'stop',
               'message': {'content': '3 plus 4 equals 7.\n#### 7'}}],
               'usage': {'prompt_tokens': 20, 'completion_tokens': 11}}
        with patch.object(teacher, 'assert_reserved'), \
             patch.object(teacher, 'other_collector_locks', return_value=[]), \
             patch.object(teacher, 'load_tokenizer', return_value=TinyTokenizer()), \
             patch.object(teacher, 'record'), \
             patch.object(teacher, 'PUBLIC', self.root / 'public_summary.json'), \
             patch.object(teacher.transport, 'credential', return_value='local-fixture-only'), \
             patch.object(teacher.transport.urllib.request, 'urlopen', side_effect=lambda *a, **k: io.BytesIO(json.dumps(raw).encode())) as request:
            first = teacher.collect(self.root, 1)
            second = teacher.collect(self.root, 1)
            self.assertEqual(request.call_count, 2)
            self.assertEqual(first['eligible'], 2)
            self.assertEqual(second['stage'], 'completed')
            eligible = teacher.read_rows(self.root / 'eligible.jsonl')
            self.assertEqual({row['reference_type'] for row in eligible}, {'human_dataset_answer', 'procedurally_generated_result'})
            self.assertEqual(sum(row['reference_match_is_independent_gold'] for row in eligible), 1)
            (self.root / 'teacher_results.jsonl').unlink()
            recovered = teacher.collect(self.root, 1)
            self.assertEqual(recovered['eligible'], 2)
            self.assertEqual(request.call_count, 2)
            (self.root / 'teacher_results.jsonl').unlink()
            first_id = teacher.read_rows(self.root / 'candidates.jsonl')[0]['id']
            _, saved = teacher._attempt_paths(self.root, first_id)
            saved.unlink()
            with self.assertRaisesRegex(RuntimeError, 'Ambiguous'):
                teacher.collect(self.root, 1)
            self.assertEqual(request.call_count, 2)

    def test_chunk_tampering_stops_before_generation(self):
        self.freeze(2)
        path = self.root / 'plan.json'
        plan = json.loads(path.read_text())
        plan['chunks'][0]['ids'].reverse()
        teacher._write(path, plan)
        with self.assertRaisesRegex(ValueError, 'Chunk'):
            teacher.collect(self.root, 1)

    def test_active_source_preparation_cannot_be_frozen(self):
        (self.root / 'cohort.lock').write_text('123')
        with self.assertRaisesRegex(RuntimeError, 'still active'):
            teacher.audit_cohort(self.root)

    def test_funding_freshness_guard_is_not_bypassed(self):
        with patch.object(Path, 'read_text', return_value='{}'), \
             patch.object(teacher, 'require_fresh_deepseek_budget', side_effect=RuntimeError('stale')) as guard:
            with self.assertRaisesRegex(RuntimeError, 'stale'):
                teacher.assert_reserved({'budget_job_id': 'fixture'})
            guard.assert_called_once()


if __name__ == '__main__':
    unittest.main()
