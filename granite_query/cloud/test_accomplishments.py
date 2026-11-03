import json
from pathlib import Path
import tempfile
import unittest

import accomplishments


class AccomplishmentTests(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).resolve().parent / 'runs/test_accomplishments'
        parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.temporary.name)
        self.runs = self.root / 'granite_query/cloud/runs'

    def tearDown(self):
        self.temporary.cleanup()

    def save(self, path, data):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data), encoding='utf-8')

    def test_plans_are_not_mistaken_for_launched_or_completed_work(self):
        self.save('granite_query/cloud/runs/matched_eval64_v1/plan.json', {'run_id': 'matched_eval64_v1'})
        self.save('granite_query/cloud/runs/granite_full120_v1/plan.json', {'train_ids': ['fixture']})
        public = accomplishments.build(self.root)
        self.assertFalse(public['accuracy_improved'])
        self.assertTrue(all(row['status'] == 'queued' for row in public['current_work']))
        self.assertFalse(any('64-question Granite benchmark fully recovered' == row['title'] for row in public['completed']))

    def test_failed_original_and_running_resume_are_separate_and_redacted(self):
        self.save('granite_query/cloud/runs/matched_eval64_v1/remote_status.json', {
            'stage': 'failed', 'error_type': 'TimeoutError',
            'error': 'DO_NOT_EXPORT_PRIVATE_ERROR sk-abcdefghijklmnop', 'raw_response': 'PRIVATE_REASONING'})
        self.save('granite_query/cloud/runs/matched_eval64_resume1/plan.json', {'resume_from': 'matched_eval64_v1'})
        self.save('granite_query/cloud/runs/matched_eval64_resume1/launch.json', {
            'call_id': 'fc-fixture', 'DEEPSEEK_API_KEY': 'PRIVATE_KEY'})
        self.save('granite_query/cloud/runs/matched_eval64_resume1/remote_status.json', {
            'stage': 'ranked32_evaluation', 'local_path': 'C:\\Users\\private\\data'})
        public = accomplishments.build(self.root)
        phases = {row['title']: row['status'] for row in public['current_work']}
        self.assertEqual(phases['Original 64-question Granite attempt'], 'failed')
        self.assertEqual(phases['Resume of unfinished 64-question evaluations'], 'running')
        exported = (self.root / 'docs/project-status.json').read_text(encoding='utf-8')
        for secret in ('PRIVATE_KEY', 'PRIVATE_REASONING', 'DO_NOT_EXPORT', 'sk-abcdefghijklmnop', 'C:\\\\Users'):
            self.assertNotIn(secret, exported)
        self.assertTrue((self.root / 'progress/ACCOMPLISHMENTS.md').exists())

    def test_worker_completed_stage_without_results_is_not_completed(self):
        self.save('granite_query/cloud/runs/matched_eval64_v1/launch.json', {'call_id': 'fc-fixture'})
        self.save('granite_query/cloud/runs/matched_eval64_v1/remote_status.json', {'stage': 'completed'})
        public = accomplishments.build(self.root)
        self.assertEqual(public['current_work'][0]['status'], 'running')
        self.assertIn('recovering', public['current_work'][0]['detail'])


if __name__ == '__main__':
    unittest.main()
