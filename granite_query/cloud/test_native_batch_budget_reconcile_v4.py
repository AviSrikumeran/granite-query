"""Invented completed-parent transfer graph; no providers or production files."""
from copy import deepcopy
import unittest
from cloud import native_batch_budget_reconcile_v4 as accounting
from cloud import native_reasoning_batch_control_v4 as control
from cloud.test_native_reasoning_batch_control_v4 import Fixture


class BatchAccountingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=Fixture();cls.receipt=cls.fixture.fund()
        cls.ledger=control.read(cls.fixture.state/'budget.json')
        cls.snapshot=control.read(cls.fixture.state/'modal_billing_snapshot.json')
        cls.apps=control.read(cls.fixture.state/'modal_app_status_snapshot.json')['apps']
    @classmethod
    def tearDownClass(cls):cls.fixture.close()
    def reseal(self,value,change):
        record=deepcopy(self.receipt);change(record)
        record['funding_sha256']=accounting.prior.digest({k:v for k,v in record.items() if k!='funding_sha256'})
        for job in value['jobs']:
            if 'native_batch_funding' in job:job['native_batch_funding']=deepcopy(record)
    def test_actual_zero_billing_view_does_not_count_restored_proof_three_fifty(self):
        before=deepcopy(self.ledger);result=accounting.reconcile(before,self.snapshot,apps=self.apps)
        self.assertEqual(before,self.ledger);self.assertIsNot(result,before)
        self.assertEqual(result['reserved']['modal'],self.ledger['reserved']['modal'])
        self.assertEqual(result['reserved']['modal'],10.5)
        self.assertTrue(result['native_transfer_accounting']['conservation_verified'])
        child=control._one(result,self.fixture.job['run_id'])
        self.assertEqual(child['status'],'completed');self.assertEqual(child['reserved_usd'],1.75)
        self.assertEqual(control._one(result,self.fixture.parent.name+'-envelope')['reserved_usd'],0)
    def test_forged_success_or_zero_source_or_fork_never_normalizes(self):
        for mutation in (
                lambda x:control._one(x,self.fixture.job['run_id']).update(status='failed'),
                lambda x:control._one(x,self.fixture.parent.name+'-envelope').update(reserved_usd=.01),
                lambda x:control._one(x,self.fixture.output.name+'-envelope').update(reserved_usd=5.26),
                lambda x:x['jobs'].append({'run_id':'INVENTED-third-edge','service':'modal','status':'reserved',
                    'reserved_usd':0,'native_batch_funding':deepcopy(self.receipt)})):
            value=deepcopy(self.ledger);mutation(value)
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):accounting.verify_transfers(value)
    def test_false_gate_sidecar_does_not_override_recomputed_feasible_time(self):
        value=deepcopy(self.ledger)
        def mutate(record):
            parent=record['parent_completed'];c=parent['original_calibration'];c['baseline_generation_seconds']=100.
            c['forecast_seconds']={role:round(80+125+.0032*n,3) for role,n in parent['original_forwarded_input_tokens'].items()}
            parent['original_calibration_sha256']=accounting.prior._file_digest(c)
        self.reseal(value,mutate)
        with self.assertRaises(ValueError):accounting.verify_transfers(value)
    def test_explicit_new_allowance_and_unknown_superseded_stay_strict(self):
        value=deepcopy(self.ledger);self.reseal(value,lambda r:r.update(additional_new_reservation_usd=0))
        with self.assertRaises(ValueError):accounting.verify_transfers(value)
        value=deepcopy(self.ledger);self.reseal(value,lambda r:r.update(new_max_new_tokens=1024))
        with self.assertRaises(ValueError):accounting.verify_transfers(value)
        value=deepcopy(self.ledger);value['jobs'].append({'run_id':'INVENTED-unproven','service':'modal','status':'superseded','reserved_usd':0})
        with self.assertRaises(ValueError):accounting.reconcile(value,self.snapshot,apps=self.apps)


if __name__=='__main__':unittest.main()
