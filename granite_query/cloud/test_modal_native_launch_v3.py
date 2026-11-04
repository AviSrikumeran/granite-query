"""Synthetic V3 launcher proof gates; no model/provider calls."""
import os,unittest
from unittest.mock import patch
from cloud import native_reasoning_control_v3 as control
from cloud import modal_native_launch_v3 as launch
from cloud import test_native_reasoning_control_v3 as fixtures


class LaunchV3Tests(unittest.TestCase):
    def setUp(self):self.f=fixtures.Fixture();self.addCleanup(self.f.close)
    def test_parent_lease_funding_and_exact_claim_are_checked_before_spawn(self):
        runner,job=self.f.state_controller()
        dispatch=control.make_dispatch(job['plan'],job['data'],self.f.sources,control.sha(self.f.output/'review_baseline.json'))
        ledger=control.read(self.f.state/'budget.json');control._bind_child(ledger,job,self.f.output,dispatch)
        control.write(self.f.state/'budget.json',ledger);control.write(job['folder_path']/'dispatch.json',dispatch)
        control.write(job['folder_path']/'controller_owner.json',{'pid':os.getpid(),'claim_id':dispatch['claim_id']})
        with patch.object(control,'load_jobs',return_value=[job]),patch.object(launch.worker,'verify_sources',return_value={'INVENTED':True}):
            with self.assertRaises(ValueError):launch.preflight(job['folder_path'])
            with control.exclusive(self.f.state/'gpu_launch.lock'):
                actual,_=launch.preflight(job['folder_path']);self.assertEqual(actual['run_id'],job['run_id'])
                ledger=control.read(self.f.state/'budget.json');control._one(ledger,job['run_id'])['native_claim_id']='0'*32
                control.write(self.f.state/'budget.json',ledger)
                with self.assertRaises(ValueError):launch.preflight(job['folder_path'])
        self.assertFalse((job['folder_path']/'cli_spawn_started.json').exists());self.assertEqual(self.f.backend.launches,0)


if __name__=='__main__':unittest.main()
