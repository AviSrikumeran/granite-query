import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import progress

class JournalTests(unittest.TestCase):
    def test_append_dedup_export_and_private_field_exclusion(self):
        test_root = Path(__file__).resolve().parent / 'runs/test_progress'
        test_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as folder:
            root = Path(folder)
            with patch.object(progress, 'JOURNAL', root / 'progress/events.jsonl'), patch.object(progress, 'SITE', root / 'docs'):
                self.assertTrue(progress.record('failed', 'Formatting rejected', 'Currency symbol retained.', 'one'))
                original = progress.JOURNAL.read_text()
                self.assertFalse(progress.record('failed', 'Formatting rejected', 'Currency symbol retained.', 'one'))
                self.assertEqual(original, progress.JOURNAL.read_text())
                progress.record('resolved', 'Parser policy clarified', 'Original remains preserved.', 'two')
                result = progress.build({'teacher_pilot': {'completed': 16, 'verified_final_answers': 15},
                                         'private_account': 'DO_NOT_EXPORT'})
                self.assertEqual(len(result['events']), 2)
                self.assertNotIn('DO_NOT_EXPORT', (progress.SITE / 'status.json').read_text())
                self.assertIn('Formatting rejected', (root / 'progress/JOURNAL.md').read_text())
                self.assertEqual(json.loads((progress.SITE / 'status.json').read_text())['metrics']['teacher_responses'], 16)

    def test_reject_credentials_and_private_paths(self):
        for value in ['Bearer example-secret', 'sk-abcdefghijklmnopqrst', 'C:\\Users\\private\\file']:
            with self.assertRaises(ValueError):
                progress.clean(value)

if __name__ == '__main__':
    unittest.main()
