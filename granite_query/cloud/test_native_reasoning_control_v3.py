"""Synthetic config-recovery receipts/funding; never real models or budgets."""
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import json,sys,unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cloud import native_reasoning_control_v3 as control
from cloud import native_reasoning_control_v2 as parent
from cloud import modal_native_reasoning_v3 as worker
from cloud import modal_native_reasoning_v2 as parent_worker
from cloud import granite_lora_layout as layout
from cloud import test_native_reasoning_control_v2 as prior
from cloud import test_native_reasoning_contract as encoding


class Fixture:
    def __init__(self):
        self.prior=prior.Fixture();self.stack=ExitStack();self.root=self.prior.root;self.state=self.prior.state
        self.parent=self.prior.output;self.output=self.root/'config_v3';self.collection=self.prior.collection
        ledger=parent.read(self.state/'budget.json')
        parent._one(ledger,self.prior.old.name+'-envelope')['native_envelope']=True
        parent.write(self.state/'budget.json',ledger)
        self.stack.enter_context(patch.object(control.contract,'DEVELOPMENT_IDS_SHA256',
            control.digest([r['id'] for r in self.prior.dev])))
        parent_design=parent.read(self.parent/'design.json');parent_design['protocol']=control.contract.protocol()
        parent.write(self.parent/'design.json',parent_design)
        bindings={'collection_plan_sha256':control.sha(self.collection/'plan.json'),
            'eligible_pairs_sha256':'b'*64,'teacher_receipt_inventory_sha256':'c'*64}
        self.jobs=[]
        for role in control.ROLES:
            selected=control.contract.select_whole_targets([encoding.target(i,length,mode=role)
                for i,length in enumerate([3000]*5+[1384])]) if role!='baseline' else None
            arm=None if selected is None else {'arm':role,'training':selected,
                'updates':control.contract.exposure_windows(selected),'token_budget':16384,
                'tokens_per_update':1024,'optimizer_updates':16,'tokenizer':control.contract.TOKENIZER}
            data={'development':self.prior.dev,'bindings':bindings,'arm':arm}
            plan=dict(control.contract.protocol(),run_id=self.parent.name+'_'+role,arm=role,
                mode='evaluate_base' if role=='baseline' else 'train_evaluate',
                token_budget=0 if role=='baseline' else 16384,optimizer_updates=0 if role=='baseline' else 16,
                input_sha256=control.digest(data),bindings_sha256=control.digest(bindings))
            plan['protocol_hash']=control.digest(plan);folder=self.parent/'arms'/plan['run_id']
            control.contract.validate_bundle(data,plan)
            control.write(folder/'plan.json',plan);control.write(folder/'input.json',data)
            rows={r['id']:r for r in selected or []}
            forwarded=sum(len(rows[w['id']]['input_ids']) for u in arm['updates'] for w in u['microbatches']) if arm else 0
            self.jobs.append({'run_id':plan['run_id'],'role':role,'folder':'arms/'+plan['run_id'],
                'folder_path':folder,'plan':plan,'data':data,'plan_sha256':control.digest(plan),
                'input_sha256':control.digest(data),'forwarded_input_tokens':forwarded,'examples':len(rows)})
        parent.write(self.parent/'study_manifest.json',{'version':parent.VERSION,
            'design_sha256':parent.sha(self.parent/'design.json'),'bindings':bindings,'jobs':[
                {k:v for k,v in j.items() if k not in ('folder_path','plan','data')} for j in self.jobs]})
        parent.write(self.parent/'review_recovery.json',dict(parent.recovery_review_template(self.parent),reviewed=True))
        self.prior.migrate();job=self.jobs[0];self.parent_job=job
        parent.write(self.parent/'review_baseline.json',{'reviewed':True,'phase':'baseline',
            'design_sha256':parent.sha(self.parent/'design.json'),'source_sha256':self.prior.sources,
            'protected_modal_usd':5.,'study_manifest_sha256':parent.sha(self.parent/'study_manifest.json')})
        dispatch=parent.make_dispatch(job['plan'],job['data'],self.prior.sources,parent.sha(self.parent/'review_baseline.json'))
        ledger=parent.read(self.state/'budget.json');parent._bind_child(ledger,job,self.parent,dispatch)
        self.call_id='fc-INVENTED-v2';launch={'run_id':job['run_id'],'call_id':self.call_id,
            'claim_id':dispatch['claim_id'],'intent_sha256':dispatch['intent_sha256']}
        parent.write(job['folder_path']/'dispatch.json',dispatch);parent.write(job['folder_path']/'launch.json',launch)
        self.result={'run_id':job['run_id'],'call_id':self.call_id,'plan':job['plan'],'dispatch':dispatch,
            'dispatch_sha256':parent.digest(dispatch),'protocol_hash':job['plan']['protocol_hash'],
            'stage':'failed','error_type':'ValueError','official_test_used':False,'evaluation_complete':False,
            'supervised_tokens':0,'optimizer_updates':0,'retained_evaluation_count':0,
            'evaluations':{'baseline':[]},'batches':[],'raw_batches':[],'weighted_losses':[],
            'raw_pending':False,'raw_pending_record':None,'runtime_model_verification':None,
            'adapter_inventory':None,'checkpoint':None,'elapsed_seconds':19.087607,
            'source_verification':{'dependency_versions':parent_worker.DEPENDENCIES,'physical':{
                'packaged_source_hashes_verified':True,'source_hashes':self.prior.sources,
                'source_bundle_sha256':parent.digest(self.prior.sources)}},
            'tokenizer_verification':deepcopy(control.contract.TOKENIZER),
            'mount_verification':{'validation_succeeded':True,'failed_check':None}}
        self.folder=job['folder_path'];parent.write(self.folder/'provider_result.json',self.result)
        terminal=dict(launch,kind='failed',worker_stage='failed',partial_result_sha256=parent.sha(self.folder/'provider_result.json'),
            observed_at_utc=datetime.now(timezone.utc).isoformat())
        parent.write(self.folder/'provider_terminal.json',terminal)
        child=parent._one(ledger,job['run_id']);child.update(status='failed',call_id=self.call_id,
            native_terminal_sha256=parent.sha(self.folder/'provider_terminal.json'),
            terminal_observed_at_utc=terminal['observed_at_utc'])
        parent.write(self.state/'budget.json',ledger)
        self.stack.enter_context(patch.object(parent,'load_jobs',side_effect=AssertionError('Historical teacher replay forbidden')))
        self.stack.enter_context(patch.object(control,'STATE',self.state))
        self.stack.enter_context(patch.object(control,'DEV',self.prior.dev_path))
        self.stack.enter_context(patch.object(control,'development',return_value=self.prior.dev))
        self.stack.enter_context(patch.object(control,'EXPECTED_ORIGINAL_CALL',self.call_id))
        config=deepcopy(layout.CONFIG_FIELDS);official=(json.dumps(config,separators=(',',':'))+'\n').encode()
        previous=(json.dumps(config,indent=2)+'\r\n').encode()
        (self.state/'official_pinned_model_config.raw.json').write_bytes(official)
        (self.state/'pinned_model_config.json').write_bytes(previous)
        self.stack.enter_context(patch.multiple(worker,OFFICIAL_RAW_CONFIG_SHA=control.hashlib.sha256(official).hexdigest(),
            OFFICIAL_RAW_CONFIG_BYTES=len(official)))
        self.stack.enter_context(patch.multiple(control,PRIOR_CONFIG_SHA=control.hashlib.sha256(previous).hexdigest(),PRIOR_CONFIG_BYTES=len(previous)))
        self.sources={name:'e'*64 for name in control.SOURCES}
        for name in ('native_reasoning_control_v3.py','modal_native_reasoning_v3.py'):
            self.sources[name]=control.sha(control.ROOT/name)
        self.stack.enter_context(patch.object(control,'source_inventory',return_value=self.sources))
        reproduction={'model':control.contract.MODEL,'revision':control.contract.REVISION,
            'official_raw_sha256':control.hashlib.sha256(official).hexdigest(),'official_raw_bytes':len(official),
            'prior_windows_copy_sha256':control.PRIOR_CONFIG_SHA,'prior_windows_copy_bytes':len(previous),
            'parsed_configurations_identical':True,'official_test_used':False,'paid_model_calls':0}
        control.write(self.state/'native_v3_config_cpu_reproduction.json',reproduction)
        control.prepare_design(self.collection,self.output,original=self.parent)
        control.write(self.output/'study_manifest.json',{'INVENTED':'unchanged three-arm recipe manifest'})
        control.write(self.output/'review_config_recovery.json',dict(control.funding_review_template(self.output),reviewed=True))
        self.backend=prior.Backend()
    def close(self):self.stack.close();self.prior.close()
    def fund(self):return control.fund_stage_envelope(self.output,backend=self.backend)
    def state_controller(self):
        self.fund();plan={'run_id':self.output.name+'_baseline','arm':'baseline','token_budget':0,'optimizer_updates':0}
        job={'run_id':plan['run_id'],'role':'baseline','plan':plan,'data':{'development':self.prior.dev},
            'folder_path':self.output/'arms'/plan['run_id']}
        control.write(self.output/'review_baseline.json',{'reviewed':True,'phase':'baseline','design_sha256':control.sha(self.output/'design.json'),
            'source_sha256':self.sources,'protected_modal_usd':5.,'study_manifest_sha256':control.sha(self.output/'study_manifest.json')})
        runner=control.Controller(self.output,self.backend);self.stack.enter_context(patch.object(runner,'jobs',return_value=[job]))
        return runner,job


class ConfigFundingTests(unittest.TestCase):
    def setUp(self):self.f=Fixture();self.addCleanup(self.f.close)
    def test_transfer350_plus_new175_is_disclosed_and_conserved_exactly_once(self):
        before=control.read(self.f.state/'budget.json')
        oldchildren=deepcopy(control._prior_children(control.supported_accounting(before),control.verify_design(self.f.output)))
        parent_migration=deepcopy(control._one(before,self.f.parent.name+'-envelope')['native_migration'])
        receipt=self.f.fund();after=control.read(self.f.state/'budget.json')
        self.assertEqual(after['reserved']['modal']-before['reserved']['modal'],1.75)
        self.assertEqual(after['estimated_spend'],before['estimated_spend'])
        self.assertEqual(control._prior_children(after,control.verify_design(self.f.output)),oldchildren)
        self.assertEqual(control._one(after,self.f.parent.name+'-envelope')['native_migration'],parent_migration)
        self.assertEqual(control._one(after,self.f.parent.name+'-envelope')['reserved_usd'],0)
        self.assertEqual(control.validate_stage_funding(self.f.output,after)['reserved_usd'],5.25)
        self.assertTrue(receipt['new_reservation_created']);self.assertEqual(receipt['transferred_unused_usd'],3.5)
        self.assertEqual(receipt['additional_new_reservation_usd'],1.75);self.assertEqual(receipt['total_commitment_increase_usd'],1.75)
        self.assertEqual(receipt['funding_sha256'],control.digest({k:v for k,v in receipt.items() if k!='funding_sha256'}))
        saved=(self.f.state/'budget.json').read_bytes();self.assertEqual(self.f.fund(),receipt)
        self.assertEqual((self.f.state/'budget.json').read_bytes(),saved)
        with self.assertRaises(ValueError):control.allocate_envelope(self.f.output)
    def test_new_allowance_requires_explicit_typed_review_and_protected_five_after_reserve(self):
        review=control.read(self.f.output/'review_config_recovery.json')
        for key,value in (('new_reservation_created',False),('additional_reservation_explicitly_approved',False),
                ('additional_new_reservation_usd',0),('parent_remote_owner_and_artifacts_exist',1)):
            control.write(self.f.output/'review_config_recovery.json',dict(review,**{key:value}))
            with self.subTest(key=key),self.assertRaises(ValueError):self.f.fund()
        control.write(self.f.output/'review_config_recovery.json',review)
        ledger=control.read(self.f.state/'budget.json');ledger['estimated_spend']['modal']=16.26
        billing=control.read(self.f.state/'modal_billing_snapshot.json');billing['metered_cost']='13.26'
        control.write(self.f.state/'modal_billing_snapshot.json',billing)
        control.write(self.f.state/'budget.json',ledger);before=(self.f.state/'budget.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'NEW1.75 plus protected5'):self.f.fund()
        self.assertEqual((self.f.state/'budget.json').read_bytes(),before);self.assertFalse((self.f.output/'funding_intent.json').exists())
        ledger['estimated_spend']['modal']=16.25;billing['metered_cost']='13.25'
        control.write(self.f.state/'modal_billing_snapshot.json',billing);control.write(self.f.state/'budget.json',ledger)
        self.f.fund();saved=control.read(self.f.state/'budget.json')
        self.assertEqual(30-saved['estimated_spend']['modal']-saved['reserved']['modal'],5)
    def test_funding_receipt_write_crash_never_adds_new175_or_transfers_twice(self):
        actual_write=control.write
        def interrupted(path,value,**kwargs):
            if Path(path)==self.f.output/'funding.json':raise PermissionError('INVENTED post-ledger receipt interruption')
            return actual_write(path,value,**kwargs)
        with patch.object(control,'write',side_effect=interrupted),self.assertRaises(PermissionError):self.f.fund()
        after=(self.f.state/'budget.json').read_bytes();self.assertFalse((self.f.output/'funding.json').exists())
        self.f.fund();self.assertEqual((self.f.state/'budget.json').read_bytes(),after)
        self.assertTrue((self.f.output/'funding.json').exists())
    def test_parent_failed_return_is_bound_and_owner_artifact_absence_is_not_claimed(self):
        design=control.verify_design(self.f.output);proof=design['migration_source']
        self.assertTrue(proof['parent_remote_owner_and_artifacts_exist']);self.assertEqual(proof['validated_outputs'],0)
        self.assertNotIn('remote_owner_absent',proof);self.assertNotIn('remote_artifacts_absent',proof)
        self.assertEqual([r['version'] for r in control.failure_chain_for_report(self.f.output)],['v1','v2'])
        for key,value in (('retained_evaluation_count',1),('supervised_tokens',1),('raw_pending',True),('runtime_model_verification',{'fake':True})):
            changed=deepcopy(self.f.result);changed[key]=value;control.write(self.f.folder/'provider_result.json',changed)
            terminal=control.read(self.f.folder/'provider_terminal.json');terminal['partial_result_sha256']=control.sha(self.f.folder/'provider_result.json')
            control.write(self.f.folder/'provider_terminal.json',terminal)
            with self.subTest(key=key),self.assertRaises(ValueError):control._original_failure(self.f.parent)
        control.write(self.f.folder/'provider_result.json',self.f.result)
    def test_config_cpu_proof_preserves_same_semantics_but_pins_official_raw_bytes(self):
        proof=control.make_config_proof();self.assertTrue(proof['semantic_json_equal'])
        self.assertNotEqual(proof['official_raw_sha256'],proof['prior_local_raw_sha256'])
        self.assertFalse(proof['new_runtime_model_load_verified'])
        target=self.f.state/'official_pinned_model_config.raw.json';before=target.read_bytes();target.write_bytes(before+b' ')
        with self.assertRaises(ValueError):control.make_config_proof()
    def test_parent_physical_manifest_inputs_and_sources_without_historical_teacher_replay(self):
        proof=control.verify_design(self.f.output)['migration_source']
        self.assertEqual(set(proof['original_job_files_sha256']),set(control.ROLES))
        for role in control.ROLES:
            folder=next(j['folder_path'] for j in self.f.jobs if j['role']==role)
            for name in ('input.json','plan.json'):
                path=folder/name;before=path.read_bytes();path.write_bytes(before+b' ')
                try:
                    with self.subTest(role=role,name=name),self.assertRaises(ValueError):control.verify_design(self.f.output)
                finally:path.write_bytes(before)
        path=self.f.parent/'study_manifest.json';before=path.read_bytes();manifest=control.read(path)
        manifest['jobs'].reverse();control.write(path,manifest)
        with self.assertRaises(ValueError):control.verify_design(self.f.output)
        path.write_bytes(before)
        changed=dict(self.f.prior.sources,**{'modal_native_reasoning_v2.py':'f'*64})
        with patch.object(parent,'source_inventory',return_value=changed),self.assertRaises(ValueError):control.verify_design(self.f.output)
        # Every Fixture forbids parent.load_jobs; current verification above
        # succeeds using full saved plan/input contracts and physical hashes.
    def test_newfunding_and_activegpu_fail_before_any_dispatch_owner(self):
        runner,job=self.f.state_controller();ledger=control.read(self.f.state/'budget.json')
        billing=control.read(self.f.state/'modal_billing_snapshot.json');billing['metered_cost']='14'
        control.write(self.f.state/'modal_billing_snapshot.json',billing)
        ledger['estimated_spend']['modal']=17.;control.write(self.f.state/'budget.json',ledger)
        with self.assertRaises(ValueError):runner.advance()
        self.assertFalse((job['folder_path']/'dispatch.json').exists());self.assertFalse((job['folder_path']/'controller_owner.json').exists())
        self.assertEqual(self.f.backend.launches,0)
    def test_native_supported_accounting_preserves_audited_superseded_and_rejects_unknown(self):
        self.f.fund();ledger=control.read(self.f.state/'budget.json')
        checked=control.fresh_funding(ledger)
        for name in (self.f.prior.old.name,self.f.parent.name):
            self.assertEqual(control._one(checked,name+'-envelope')['status'],'superseded')
        self.assertFalse(checked['modal_budget_accounting']['issues'])
        checked['jobs'].append({'run_id':'INVENTED-foreign-zero','service':'modal','status':'superseded','reserved_usd':0})
        with self.assertRaises((ValueError,RuntimeError)):control.fresh_funding(checked)
    def test_ambiguous_v3_call_does_not_receive_another_allowance_or_spawn(self):
        runner,job=self.f.state_controller();self.assertEqual(runner.advance()['stage'],'ambiguous_dispatch_requires_reconciliation')
        before=(self.f.state/'budget.json').read_bytes()
        self.assertEqual(runner.advance()['stage'],'ambiguous_dispatch_requires_reconciliation')
        self.assertEqual(self.f.backend.launches,1);self.assertEqual((self.f.state/'budget.json').read_bytes(),before)
    def test_readonly_report_hooks_reconstruct_receipt_without_querying_ledger_or_providers(self):
        receipt=self.f.fund();before=(self.f.state/'budget.json').read_bytes()
        with patch.object(control.Backend,'apps',side_effect=AssertionError('No provider query')):
            self.assertEqual(control.funding_record_for_report(self.f.output,receipt['created_at_utc']),receipt)
            history=control.failure_chain_for_report(self.f.output)
        self.assertEqual(len(history),2);self.assertTrue(all(r['validated_outputs']==0 for r in history))
        self.assertEqual((self.f.state/'budget.json').read_bytes(),before)


if __name__=='__main__':unittest.main()
