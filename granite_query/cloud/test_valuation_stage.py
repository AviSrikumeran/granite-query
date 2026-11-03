import json
from pathlib import Path
import tempfile
import unittest
from valuation_stage import collector_ready


class StagePreflightTests(unittest.TestCase):
    def test_only_finalized_collection_without_lock_is_ready(self):
        parent=Path(__file__).resolve().parent/'runs/local_check_tmp'
        parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as folder:
            root=Path(folder)
            self.assertFalse(collector_ready(root)[0])
            summary=root/'teacher_summary.json'
            summary.write_text(json.dumps({'stage':'collecting','requested':512,'completed':500}))
            self.assertFalse(collector_ready(root)[0])
            summary.write_text(json.dumps({'stage':'completed','requested':512,'completed':512}))
            self.assertTrue(collector_ready(root)[0])
            (root/'collector.lock').write_text('test-owner')
            self.assertFalse(collector_ready(root)[0])

    def test_reject_incomplete_finalized_size(self):
        parent=Path(__file__).resolve().parent/'runs/local_check_tmp'
        parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as folder:
            root=Path(folder)
            (root/'teacher_summary.json').write_text(json.dumps({'stage':'completed','requested':512,'completed':511}))
            with self.assertRaises(ValueError):
                collector_ready(root)


if __name__=='__main__':
    unittest.main()
