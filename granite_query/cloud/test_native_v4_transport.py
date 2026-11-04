"""Synthetic transport delegation; no providers, GPU or real ledger writes."""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
from cloud import native_v4_transport as transport


class Fixture:
    def __init__(self):
        self.stack=ExitStack();boundary=transport.control.PRIVATE/'test_native_v4_transport';boundary.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=boundary);self.root=Path(self.temp.name)
        self.output=self.root/'batch_v4';self.state=self.root/'state';self.state.mkdir()
        self.folder=self.output/'arms/batch_v4_baseline';self.dispatch={'claim_id':'a'*32,'intent_sha256':'b'*64}
        self.job={'role':'baseline','run_id':'batch_v4_baseline','folder_path':self.folder,'plan':{},'data':{}}
        self.sources={'frozen.py':'c'*64};self.dispatch['source_sha256']=self.sources
        self.owner={'claim_id':self.dispatch['claim_id'],'pid':21432}
        self.stack.enter_context(patch.object(transport.control,'STATE',self.state))
        self.stack.enter_context(patch.object(transport.control,'load_jobs',return_value=[self.job]))
        self.stack.enter_context(patch.object(transport.control,'verify_design',return_value={'source_sha256':self.sources}))
        self.stack.enter_context(patch.object(transport.control.Controller,'_dispatch',return_value=self.dispatch))
        self.stack.enter_context(patch.object(transport.control,'fresh_funding',side_effect=deepcopy))
        self.stack.enter_context(patch.object(transport.control,'validate_stage_funding',return_value={}))
        for path,value in ((self.output/'design.json',{'INVENTED':'design'}),(self.output/'study_manifest.json',{'INVENTED':'manifest'}),
                (self.output/'funding.json',{'INVENTED':'funding'}),(self.folder/'dispatch.json',self.dispatch),
                (self.folder/'controller_owner.json',self.owner),(self.folder/'launch_receipt.private.json',{'return_code':1,'app_id':'ap-INVENTED-old'})):
            transport.control.write(path,value)
        (self.folder/'launch.stdout.private.log').write_bytes(b'INVENTED oldCLI log\n')
        (self.folder/'launch.stderr.private.log').write_bytes(b'modal_native_launch_v3.py preflight\nValueError: Native study design or frozen sources changed\n')
        self.provider=self.state/'provider.json';self.host=self.state/'host.json'
        self.advance=self.state/'advance.json';self.process=self.state/'process.json'
        self.evidence={'run_id':self.job['run_id'],'observed_at_utc':transport.control.now(),
            'actual_remote_owner':None,'actual_remote_progress':None,'volume':{'exists':False,'provider_exception':'NotFoundError'},
            'apps':[{'app_id':'ap-INVENTED-old','state':'stopped','tasks':0}],'old_processes':[None,None]}
        transport.control.write(self.provider,dict(self.evidence,failed_cli_receipt=transport.control.read(self.folder/'launch_receipt.private.json')))
        transport.control.write(self.host,{'provider_reconciliation_sha256':transport.control.sha(self.provider),
            'original_controller':{'pid':21432,'creation_utc':'2026-11-04T03:56:05Z'},
            'original_venv_launcher':{'pid':32920,'creation_time_was_not_captured':True,'creation_utc':None},
            'queried_pids':[21432,32920],'observed_processes':[],'both_queried_pids_absent':True,'modal_cli_child_pid_not_recorded':True})
        transport.control.write(self.advance,{'action':'advance_baseline_once','actual_python_pid':21432,
            'run_id':self.output.name,'creation_utc':'2026-11-04T03:56:05Z',
            'design_sha256':transport.control.sha(self.output/'design.json'),'manifest_sha256':transport.control.sha(self.output/'study_manifest.json')})
        transport.control.write(self.process,{'pid':21432,'parent_pid':32920,'creation_utc':'2026-11-04T03:56:05Z'})
        transport.control.write(self.output/'transport_review.json',dict(transport.review_template(
            self.output,provider_path=self.provider,host_path=self.host,advance_path=self.advance,process_path=self.process),reviewed=True))
        transport.control.write(self.output/'review_baseline.json',{'study_manifest_sha256':transport.control.sha(self.output/'study_manifest.json')})
        self.ledger={'limits':{'modal':30,'deepseek':20},'estimated_spend':{'modal':10,'deepseek':2},'reserved':{'modal':7,'deepseek':4},
            'jobs':[{'run_id':self.job['run_id'],'service':'modal','status':'spawning','reserved_usd':1.75,
                'native_claim_id':self.dispatch['claim_id'],'native_intent_sha256':self.dispatch['intent_sha256'],
                'native_design_sha256':transport.control.sha(self.output/'design.json'),'app_id':'ap-INVENTED-old'}]}
        transport.control.write(self.state/'budget.json',self.ledger)
        self.identity={'pid':os.getpid(),'creation_utc':'2026-11-04T04:10:00Z','parent_pid':123,'executable_path':'C:/fixture/python.exe'}
        self.stack.enter_context(patch.object(transport,'process_identity',side_effect=lambda pid:deepcopy(self.identity) if pid==os.getpid() else None))
        self.backend=Backend(self)
    def close(self):self.stack.close();self.temp.cleanup()


class Backend:
    def __init__(self,fixture):self.fixture=fixture;self.calls=0;self.acknowledge=False;self.mutate=None
    def absence(self,run_id,pids):
        value=deepcopy(self.fixture.evidence);value['observed_at_utc']=transport.control.now()
        if self.mutate:self.mutate(value)
        return value
    def run_cli(self,folder,*,repair):
        self.calls+=1
        if self.acknowledge:
            transport.control.write(folder/'launch.json',dict(self.fixture.dispatch,run_id=self.fixture.job['run_id'],call_id='fc-INVENTED-new'))
        return {'return_code':0 if self.acknowledge else None,'app_id':'ap-INVENTED-correct','module':transport.REPAIR_CLI}


class TransportTests(unittest.TestCase):
    def setUp(self):self.f=Fixture();self.addCleanup(self.f.close)
    def test_existing_claim_repair_preserves_original_owner_logs_and_allowances(self):
        original={name:(self.f.folder/name).read_bytes() for name in ('controller_owner.json','dispatch.json',
            'launch_receipt.private.json','launch.stdout.private.log','launch.stderr.private.log')}
        before=transport.control.read(self.f.state/'budget.json');self.f.backend.acknowledge=True
        result=transport.repair_existing(self.f.output,backend=self.f.backend)
        self.assertEqual(result['stage'],'transport_acknowledged');self.assertFalse(result['new_reservation_created'])
        self.assertEqual({name:(self.f.folder/name).read_bytes() for name in original},original)
        after=transport.control.read(self.f.state/'budget.json');self.assertEqual(after['reserved'],before['reserved'])
        child=after['jobs'][0];self.assertEqual(child['app_id'],'ap-INVENTED-correct');self.assertEqual(child['reserved_usd'],1.75)
        self.assertEqual(child['call_id'],'fc-INVENTED-new')
        owner=transport.control.read(self.f.folder/'transport_delegation.json')
        self.assertEqual(owner['new_driver'],self.f.identity);self.assertNotEqual(owner['new_driver']['pid'],21432)
    def test_every_unknown_or_nonzero_absence_proof_blocks_before_intent(self):
        changes=(lambda x:x.update(actual_remote_owner={'call_id':'fc-unknown'}),lambda x:x.update(volume={'exists':True,'provider_exception':None}),
            lambda x:x['apps'][0].update(tasks=1),lambda x:x.update(old_processes=[{'pid':21432},None]))
        for change in changes:
            self.f.backend.mutate=change
            with self.subTest(change=change),self.assertRaises(ValueError):transport.repair_existing(self.f.output,backend=self.f.backend)
            self.assertFalse((self.f.folder/'transport_repair_intent.json').exists())
        self.assertEqual(self.f.backend.calls,0)
    def test_ambiguous_one_shot_is_never_resent_or_refunded(self):
        self.assertEqual(transport.repair_existing(self.f.output,backend=self.f.backend)['stage'],'transport_ambiguous_requires_reconciliation')
        before=(self.f.state/'budget.json').read_bytes()
        with self.assertRaises(ValueError):transport.repair_existing(self.f.output,backend=self.f.backend)
        self.assertEqual(self.f.backend.calls,1);self.assertEqual((self.f.state/'budget.json').read_bytes(),before)
    def test_delegated_cli_requires_real_new_pid_lease_and_exact_hashes(self):
        transport.repair_existing(self.f.output,backend=self.f.backend)
        with transport.control.exclusive(self.f.state/'gpu_launch.lock'),patch.object(transport,'observe_cli_ancestry',return_value={'depth':1}),\
                patch.object(transport.control,'review',return_value=transport.control.read(self.f.output/'review_baseline.json')),\
                patch.object(transport.frozen_cli.worker,'validate_dispatch',return_value=True),\
                patch.object(transport.frozen_cli.worker,'verify_sources',return_value={}):
            job,_=transport.delegated_preflight(self.f.folder);self.assertEqual(job['run_id'],self.f.job['run_id'])
            intent=transport.control.read(self.f.folder/'transport_repair_intent.json');intent['fresh_reconciliation_sha256']='f'*64
            transport.control.write(self.f.folder/'transport_repair_intent.json',intent)
            with self.assertRaises(ValueError):transport.delegated_preflight(self.f.folder)
    def test_review_source_tamper_and_existing_transmission_block(self):
        review=transport.control.read(self.f.output/'transport_review.json');review['normal_cli']='cloud.modal_native_launch_v3'
        transport.control.write(self.f.output/'transport_review.json',review)
        with self.assertRaises(ValueError):transport.repair_existing(self.f.output,backend=self.f.backend)
        self.assertEqual(self.f.backend.calls,0)


if __name__=='__main__':unittest.main()
