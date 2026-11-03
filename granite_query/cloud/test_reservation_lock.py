import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cloud import comparison_control as control


class ReservationLockTests(unittest.TestCase):
    def test_busy_watcher_lock_never_overwrites_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); state=root/'runs/supervisor';state.mkdir(parents=True)
            path=state/'budget.json'
            path.write_text(json.dumps({'jobs':[],'limits':{'modal':30,'deepseek':20},'estimated_spend':{'modal':0,'deepseek':0},'reserved':{'modal':0,'deepseek':0}}))
            original=path.read_bytes();(state/'budget_reconcile.lock').write_text('watcher')
            with patch.object(control,'ROOT',root),self.assertRaises(FileExistsError):
                control.reserve('modal',3,'next')
            self.assertEqual(path.read_bytes(),original)
            self.assertEqual((state/'budget_reconcile.lock').read_text(),'watcher')

    def test_run_identity_is_idempotent_but_cannot_change_amount(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); state=root/'runs/supervisor';state.mkdir(parents=True)
            path=state/'budget.json'
            path.write_text(json.dumps({'jobs':[],'limits':{'modal':30,'deepseek':20},'estimated_spend':{'modal':0,'deepseek':0},'reserved':{'modal':0,'deepseek':0}}))
            with patch.object(control,'ROOT',root):
                control.reserve('modal',3,'same')
                control.reserve('modal',3,'same')
                with self.assertRaises(ValueError):
                    control.reserve('modal',4,'same')
            self.assertEqual(json.loads(path.read_text())['reserved']['modal'],3)
            self.assertFalse((state/'budget_reconcile.lock').exists())


if __name__=='__main__':
    unittest.main()
