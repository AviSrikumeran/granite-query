"""Synthetic mount-recovery funding/call proofs; no actual providers or ledgers."""
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
import sys,tempfile,unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cloud import native_reasoning_control_v2 as control
from cloud import native_reasoning_control as original
from cloud import native_reasoning_collection as collection
from cloud import budget_reconcile as accounting


def graph(call_id,status='FAILURE',value=2):
    return {'queried_call_id':call_id,'observed_at_utc':datetime.now(timezone.utc).isoformat(),
        'source':'Supported FunctionCall.get_call_graph()', 'inputs':[{
            'input_id':'in-INVENTED','function_call_id':call_id,'task_id':'','status':status,
            'status_value':value,'function_name':'INVENTED.execute','module_name':'cloud','children':[]}]}


class Backend:
    def __init__(self):self.tasks=0;self.launches=0;self.acknowledge=False;self.owner=None;self.answer={'kind':'running'}
    def apps(self):return [{'tasks':self.tasks}]
    def launch(self,folder):
        self.launches+=1
        if self.acknowledge:
            d=control.read(folder/'dispatch.json')
            control.write(folder/'launch.json',{'run_id':d['run_id'],'claim_id':d['claim_id'],
                'intent_sha256':d['intent_sha256'],'call_id':'fc-INVENTED-new'},immutable=True)
        return {'return_code':0,'app_id':'ap-INVENTED-new'}
    def lookup(self,run_id):return deepcopy(self.owner)
    def poll(self,call_id):return deepcopy(self.answer)


class Fixture:
    def __init__(self):
        self.stack=ExitStack();parent=control.PRIVATE/'test_native_reasoning_control_v2';parent.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=parent);self.root=Path(self.temp.name)
        self.state=self.root/'state';self.old=self.root/'original';self.output=self.root/'mount_v2';self.collection=self.root/'collection'
        self.state.mkdir();self.collection.mkdir();control.write(self.collection/'plan.json',{'INVENTED':'collection'})
        self.dev=[{'id':f'gsm8k:train:{5000+i:05d}','prompt':f'INVENTED development {i}',
            'gold_answer':'7','source_split':'train'} for i in range(200)]
        self.dev_path=self.root/'fixture.json';control.write(self.dev_path,self.dev)
        self.sources={name:'a'*64 for name in control.SOURCES}
        self.stack.enter_context(patch.object(control,'STATE',self.state))
        self.stack.enter_context(patch.object(control,'DEV',self.dev_path))
        self.stack.enter_context(patch.object(control,'source_inventory',return_value=self.sources))
        self.stack.enter_context(patch.object(control,'development',return_value=self.dev))
        self.stack.enter_context(patch.multiple(control.contract,DEVELOPMENT_SOURCE_SHA256=control.sha(self.dev_path),
            DEVELOPMENT_PROJECTION_SHA256=control.digest(self.dev)))
        self.stack.enter_context(patch.object(control,'EXPECTED_ORIGINAL_CALL','fc-INVENTED-old'))
        self.stack.enter_context(patch.object(collection,'validate_run',return_value=({},[],[])))
        self.old_design={'source_sha256':{'INVENTED_old.py':'b'*64},
            'collection':self.collection.relative_to(control.PRIVATE).as_posix(),
            'collection_plan_sha256':control.sha(self.collection/'plan.json')}
        self.stack.enter_context(patch.object(original,'verify_design',return_value=self.old_design))
        control.write(self.old/'design.json',self.old_design)
        self.old_run=self.old.name+'_baseline';self.old_folder=self.old/'arms'/self.old_run
        jobs=[{'role':role,'run_id':self.old.name+'_'+role,'folder':'arms/'+self.old.name+'_'+role} for role in control.ROLES]
        control.write(self.old/'study_manifest.json',{'version':original.VERSION,
            'design_sha256':control.sha(self.old/'design.json'),'jobs':jobs})
        old_dispatch={'claim_id':'c'*32,'intent_sha256':'d'*64}
        self.old_launch=dict(old_dispatch,run_id=self.old_run,call_id='fc-INVENTED-old')
        control.write(self.old_folder/'dispatch.json',old_dispatch);control.write(self.old_folder/'launch.json',self.old_launch)
        control.write(self.old_folder/'first_observed_call_graph.private.json',graph('fc-INVENTED-old'))
        (self.old_folder/'first_observed_provider_error.private.log').write_bytes(b'ValueError: INVENTED pre-model mount alias failure\n')
        self.terminal=dict(self.old_launch,kind='failed',confirmed_terminal=True,error_type='ValueError',
            observed_at_utc=datetime.now(timezone.utc).isoformat(),positive_provider_failure_status=True,
            worker_result_available=False,validated_evaluation_rows=0,failure_before_artifact_owner_and_model_load=True,
            provider_call_graph_sha256=control.sha(self.old_folder/'first_observed_call_graph.private.json'),
            provider_exception_trace_sha256=control.sha(self.old_folder/'first_observed_provider_error.private.log'))
        control.write(self.old_folder/'provider_terminal.json',self.terminal)
        control.prepare_design(self.collection,self.output,original=self.old)
        control.write(self.output/'study_manifest.json',{'INVENTED':'exact three-plan manifest fixture'})
        control.write(self.output/'review_recovery.json',dict(control.recovery_review_template(self.output),reviewed=True))
        stamp=datetime.now(timezone.utc)
        self.billing={'queried_at_utc':stamp.isoformat(),'start_utc':(stamp-timedelta(days=1)).isoformat(),
            'metered_cost':'9','billed_cost':'0','source':'INVENTED supported-observation fixture'}
        self.apps=[{'app_id':app,'state':'stopped','tasks':0,'stopped_at':stamp.isoformat()}
            for app in ('ap-INVENTED-old','ap-INVENTED-new')]
        self.child={'run_id':self.old_run,'service':'modal','status':'failed','reserved_usd':1.75,
            'native_design_sha256':control.sha(self.old/'design.json'),'native_envelope_parent':self.old.name+'-envelope',
            'native_claim_id':old_dispatch['claim_id'],'native_intent_sha256':old_dispatch['intent_sha256'],
            'native_terminal_sha256':control.sha(self.old_folder/'provider_terminal.json'),'call_id':'fc-INVENTED-old',
            'app_id':'ap-INVENTED-old','terminal_observed_at_utc':stamp.isoformat()}
        envelope={'run_id':self.old.name+'-envelope','service':'modal','status':'reserved','reserved_usd':5.25,
            'initial_reserved_usd':7.,'dispatches':[self.old_run],'native_design_sha256':control.sha(self.old/'design.json')}
        base={'limits':{'modal':30,'deepseek':20},'estimated_spend':{'modal':0,'deepseek':0},
            'reserved':{'modal':0,'deepseek':0},'jobs':[envelope,deepcopy(self.child)]}
        self.ledger=accounting.reconcile(base,self.billing,now=stamp,apps=self.apps,lag_buffer_usd=3)
        control.write(self.state/'budget.json',self.ledger)
        control.write(self.state/'modal_billing_snapshot.json',self.billing)
        control.write(self.state/'modal_app_status_snapshot.json',{'apps':self.apps})
        self.backend=Backend()
    def close(self):self.stack.close();self.temp.cleanup()
    def migrate(self):return control.migrate_envelope(self.output,backend=self.backend)
    def state_controller(self):
        self.migrate();plan={'run_id':self.output.name+'_baseline','arm':'baseline','token_budget':0,'optimizer_updates':0}
        job={'run_id':plan['run_id'],'role':'baseline','plan':plan,'data':{'development':self.dev},
            'folder_path':self.output/'arms'/plan['run_id']}
        control.write(self.output/'review_baseline.json',{'reviewed':True,'phase':'baseline',
            'design_sha256':control.sha(self.output/'design.json'),'source_sha256':self.sources,'protected_modal_usd':5.,
            'study_manifest_sha256':control.sha(self.output/'study_manifest.json')})
        runner=control.Controller(self.output,self.backend)
        self.stack.enter_context(patch.object(runner,'jobs',return_value=[job]))
        return runner,job


class RecoveryControlTests(unittest.TestCase):
    def setUp(self):self.f=Fixture();self.addCleanup(self.f.close)
    def test_migration_moves_only_existing525_preserves_failed175_and_total_commitment(self):
        before=control.read(self.f.state/'budget.json');child=deepcopy(control._one(before,self.f.old_run))
        record=self.f.migrate();after=control.read(self.f.state/'budget.json')
        self.assertEqual(before['reserved'],after['reserved']);self.assertEqual(before['estimated_spend'],after['estimated_spend'])
        self.assertEqual(control._one(after,self.f.old_run),child)
        self.assertEqual(control._one(after,self.f.old.name+'-envelope')['reserved_usd'],0)
        self.assertEqual(control._one(after,self.f.old.name+'-envelope')['status'],'superseded')
        self.assertEqual(control.validate_migration(self.f.output,after)['reserved_usd'],5.25)
        self.assertEqual(record['migrated_usd'],5.25);self.assertFalse(record['new_reservation_created'])
        saved=(self.f.state/'budget.json').read_bytes();self.assertEqual(self.f.migrate(),record)
        self.assertEqual((self.f.state/'budget.json').read_bytes(),saved)
        with self.assertRaises(ValueError):control.allocate_envelope(self.f.output)
    def test_migration_requires_exact_review_positive_old_terminal_fresh_funding_and_gpu_clear(self):
        review=control.read(self.f.output/'review_recovery.json')
        for value in (False,1):
            control.write(self.f.output/'review_recovery.json',dict(review,remote_owner_absent=value))
            with self.subTest(remote_owner_absent=value),self.assertRaises(ValueError):self.f.migrate()
        control.write(self.f.output/'review_recovery.json',review)
        self.f.backend.tasks=1
        with self.assertRaises(ValueError):self.f.migrate()
        self.f.backend.tasks=0;ledger=control.read(self.f.state/'budget.json')
        ledger['modal_observation']['queried_at_utc']=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
        control.write(self.f.state/'budget.json',ledger)
        with self.assertRaises((ValueError,RuntimeError)):self.f.migrate()
        self.assertFalse((self.f.output/'migration.json').exists())
        control.write(self.f.old_folder/'provider_terminal.json',dict(self.f.terminal,positive_provider_failure_status=False))
        with self.assertRaises(ValueError):control.verify_design(self.f.output)
    def test_migration_receipt_write_crash_reconstructs_without_second_transfer(self):
        original_write=control.write
        def interrupted(path,value,**kwargs):
            if Path(path)==self.f.output/'migration.json':raise PermissionError('INVENTED receipt interruption')
            return original_write(path,value,**kwargs)
        with patch.object(control,'write',side_effect=interrupted),self.assertRaises(PermissionError):self.f.migrate()
        after=(self.f.state/'budget.json').read_bytes()
        self.assertFalse((self.f.output/'migration.json').exists())
        self.f.migrate();self.assertEqual((self.f.state/'budget.json').read_bytes(),after)
        self.assertTrue((self.f.output/'migration.json').exists())
    def test_only_three_roles_receive_migrated_calls_no_fourth_or_recovery(self):
        self.f.migrate();ledger=control.read(self.f.state/'budget.json');reserved=deepcopy(ledger['reserved'])
        for role in control.ROLES:
            job={'run_id':self.f.output.name+'_'+role,'role':role}
            dispatch={'claim_id':role+'-fixture','intent_sha256':'a'*64}
            control._bind_child(ledger,job,self.f.output,dispatch)
            ledger['jobs'][-1]['status']='completed'
            self.assertEqual(ledger['reserved'],reserved)
        self.assertEqual(control.validate_migration(self.f.output,ledger)['reserved_usd'],0)
        before=deepcopy(ledger)
        with self.assertRaises(ValueError):control._bind_child(ledger,{'run_id':'extra','role':'recovery'},self.f.output,dispatch)
        self.assertEqual(ledger,before)
    def test_funding_failure_precedes_any_irreversible_dispatch_intent(self):
        runner,job=self.f.state_controller();ledger=control.read(self.f.state/'budget.json')
        ledger['estimated_spend']['modal']=18.01;control.write(self.f.state/'budget.json',ledger)
        before=(self.f.state/'budget.json').read_bytes()
        with self.assertRaises(ValueError):runner.advance()
        self.assertFalse((job['folder_path']/'dispatch.json').exists())
        self.assertFalse((job['folder_path']/'controller_owner.json').exists())
        self.assertEqual((self.f.state/'budget.json').read_bytes(),before);self.assertEqual(self.f.backend.launches,0)
    def test_ambiguous_transmitted_call_never_reserves_or_launches_twice(self):
        runner,job=self.f.state_controller();self.assertEqual(runner.advance()['stage'],'ambiguous_dispatch_requires_reconciliation')
        before=(self.f.state/'budget.json').read_bytes()
        self.assertEqual(runner.advance()['stage'],'ambiguous_dispatch_requires_reconciliation')
        self.assertEqual(self.f.backend.launches,1);self.assertEqual((self.f.state/'budget.json').read_bytes(),before)
    def test_sdk_error_requires_positive_matching_graph_and_original_exception(self):
        import modal
        class Status(Enum):FAILURE=2;SUCCESS=1
        def node(status,call_id):return SimpleNamespace(input_id='in-fixture',function_call_id=call_id,task_id='',
            status=status,function_name='fixture.execute',module_name='cloud',children=[])
        call=SimpleNamespace(get=Mock(side_effect=RuntimeError('INVENTED SDK failure')),
            get_call_graph=Mock(return_value=[node(Status.FAILURE,'fc-fixture')]))
        with patch.object(modal.FunctionCall,'from_id',return_value=call):
            answer=control.Backend().poll('fc-fixture');self.assertEqual(answer['kind'],'failed')
            self.assertEqual(answer['positive_failure']['evidence']['provider_status'],'FAILURE')
            call.get_call_graph.return_value=[node(Status.SUCCESS,'fc-fixture')]
            self.assertEqual(control.Backend().poll('fc-fixture')['kind'],'monitoring_error')
            call.get_call_graph.return_value=[node(Status.FAILURE,'fc-other')]
            self.assertEqual(control.Backend().poll('fc-fixture')['kind'],'monitoring_error')
    def test_timeout_error_uses_positive_graph_to_distinguish_pending_remote_error_and_hard_timeout(self):
        import modal
        class Status(Enum):PENDING=0;FAILURE=2;TIMEOUT=4
        def node(status,call_id='fc-fixture'):return SimpleNamespace(input_id='in-fixture',function_call_id=call_id,
            task_id='',status=status,function_name='fixture.execute',module_name='cloud',children=[])
        call=SimpleNamespace(get=Mock(side_effect=TimeoutError('INVENTED get or remote timeout')),
            get_call_graph=Mock(return_value=[node(Status.PENDING)]))
        with patch.object(modal.FunctionCall,'from_id',return_value=call):
            self.assertEqual(control.Backend().poll('fc-fixture')['kind'],'running')
            for status in (Status.FAILURE,Status.TIMEOUT):
                call.get_call_graph.return_value=[node(status)]
                answer=control.Backend().poll('fc-fixture')
                self.assertEqual(answer['kind'],'failed')
                self.assertEqual(answer['positive_failure']['evidence']['provider_status'],status.name)
            call.get_call_graph.return_value=[node(Status.TIMEOUT,'fc-other')]
            self.assertEqual(control.Backend().poll('fc-fixture')['kind'],'monitoring_error')
            call.get_call_graph.side_effect=RuntimeError('INVENTED graph temporarily unavailable')
            self.assertEqual(control.Backend().poll('fc-fixture')['kind'],'monitoring_error')
    def test_positive_failure_saved_before_terminal_and_ledger_crash_reuses_proof(self):
        runner,job=self.f.state_controller();self.f.backend.acknowledge=True;runner.advance()
        call='fc-INVENTED-new';stamp=datetime.now(timezone.utc).isoformat();g=graph(call);trace='ValueError: INVENTED failure'
        proof=control.failure_evidence(call,g,trace.encode(),error_type='ValueError',observed_at_utc=stamp)
        self.f.backend.answer={'kind':'failed','error_type':'ValueError',
            'positive_failure':{'evidence':proof,'call_graph':g,'exception_trace':trace}}
        actual_write=control.write
        def interrupted(path,value,**kwargs):
            if Path(path)==self.f.state/'budget.json' and (job['folder_path']/'provider_terminal.json').exists():
                raise PermissionError('INVENTED ledger commit crash')
            return actual_write(path,value,**kwargs)
        with patch.object(control,'write',side_effect=interrupted),self.assertRaises(PermissionError):runner.poll()
        self.assertTrue((job['folder_path']/'provider_failure_evidence.json').exists())
        self.assertTrue((job['folder_path']/'provider_terminal.json').exists())
        self.f.backend.poll=Mock(side_effect=AssertionError('Reuse saved actual terminal'))
        runner.poll();ledger=control.read(self.f.state/'budget.json')
        self.assertEqual(control._one(ledger,job['run_id'])['status'],'failed')
        self.assertEqual(control._one(ledger,job['run_id'])['reserved_usd'],1.75)
        self.assertEqual(control._one(ledger,self.f.old_run)['reserved_usd'],1.75)
    def test_unproven_backend_failure_never_writes_terminal_or_releases_allowance(self):
        runner,job=self.f.state_controller();self.f.backend.acknowledge=True;runner.advance()
        self.f.backend.answer={'kind':'failed','error_type':'UnprovenSDKError'}
        before=(self.f.state/'budget.json').read_bytes()
        with self.assertRaises(ValueError):runner.poll()
        self.assertFalse((job['folder_path']/'provider_terminal.json').exists())
        self.assertEqual((self.f.state/'budget.json').read_bytes(),before)


if __name__=='__main__':unittest.main()
