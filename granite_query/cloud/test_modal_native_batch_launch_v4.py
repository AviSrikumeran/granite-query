"""Prospective batch32 launch claims with only synthetic backends."""
import os
import unittest
from unittest.mock import patch
from cloud import native_reasoning_batch_control_v4 as control
from cloud import modal_native_batch_launch_v4 as launch
from cloud import test_native_reasoning_batch_control_v4 as fixtures


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.Fixture();self.addCleanup(self.f.close);self.f.fund()
        data=self.f.job['data'];plan=dict(control.contract.protocol(),run_id=self.f.output.name+'_baseline',
            arm='baseline',mode='evaluate_base',token_budget=0,optimizer_updates=0,
            input_sha256=control.digest(data),bindings_sha256=control.digest(data['bindings']))
        plan['protocol_hash']=control.digest(plan);control.contract.validate_bundle(data,plan)
        self.job={'run_id':plan['run_id'],'role':'baseline','plan':plan,'data':data,
            'folder_path':self.f.output/'arms'/plan['run_id']}
        control.write(self.f.output/'review_baseline.json',{'reviewed':True,'phase':'baseline',
            'design_sha256':control.sha(self.f.output/'design.json'),'source_sha256':self.f.sources,
            'protected_modal_usd':5.,'study_manifest_sha256':control.sha(self.f.output/'study_manifest.json')})
    def test_exact_lease_and_funded_claim_before_any_spawn(self):
        job=self.job;dispatch=control.make_dispatch(job['plan'],job['data'],self.f.sources,
            control.sha(self.f.output/'review_baseline.json'))
        ledger=control.read(self.f.state/'budget.json');control._bind_child(ledger,job,self.f.output,dispatch)
        control.write(self.f.state/'budget.json',ledger);control.write(job['folder_path']/'dispatch.json',dispatch)
        control.write(job['folder_path']/'controller_owner.json',{'pid':os.getpid(),'claim_id':dispatch['claim_id']})
        with patch.object(control,'load_jobs',return_value=[job]),patch.object(launch.worker,'verify_sources',return_value={}):
            with self.assertRaises(ValueError):launch.preflight(job['folder_path'])
            with control.exclusive(self.f.state/'gpu_launch.lock'):
                actual,_=launch.preflight(job['folder_path']);self.assertEqual(actual['plan']['evaluation_batch_size'],32)
                ledger=control.read(self.f.state/'budget.json');control._one(ledger,job['run_id'])['native_claim_id']='0'*32
                control.write(self.f.state/'budget.json',ledger)
                with self.assertRaises(ValueError):launch.preflight(job['folder_path'])
        self.assertFalse((job['folder_path']/'cli_spawn_started.json').exists())
    def test_ambiguous_dispatch_never_spawns_or_reserves_a_second_time(self):
        runner=control.Controller(self.f.output,self.f.backend)
        with patch.object(runner,'jobs',return_value=[self.job]):
            self.assertEqual(runner.advance()['stage'],'ambiguous_dispatch_requires_reconciliation')
            before=(self.f.state/'budget.json').read_bytes()
            self.assertEqual(runner.advance()['stage'],'ambiguous_dispatch_requires_reconciliation')
            self.assertEqual((self.f.state/'budget.json').read_bytes(),before)
        self.assertEqual(self.f.backend.launches,1)


if __name__=='__main__':unittest.main()
