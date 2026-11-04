"""Prospective synthetic completed-parent fixtures; no actual plans/providers."""
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from cloud import native_reasoning_batch_control_v4 as control
from cloud import native_reasoning_control_v3 as parent
from cloud import modal_native_reasoning_v3 as parent_worker
from cloud import native_batch_budget_reconcile_v4 as accounting
from cloud import test_native_reasoning_control_v3 as prior
from cloud.test_modal_native_reasoning import Tokenizer


class Fixture:
    def __init__(self,*,correct=True):
        self.prior=prior.Fixture();self.stack=ExitStack();self.root=self.prior.root
        self.parent=self.prior.output;self.output=self.root/'batch32_v4';self.state=self.prior.state
        self.collection=self.prior.collection;self.tokenizer=Tokenizer();self.jobs=[]
        for old in self.prior.jobs:
            plan=deepcopy(old['plan']);plan['run_id']=self.parent.name+'_'+old['role']
            plan['protocol_hash']=parent.digest({k:v for k,v in plan.items() if k!='protocol_hash'})
            folder=self.parent/'arms'/plan['run_id'];parent.write(folder/'plan.json',plan);parent.write(folder/'input.json',old['data'])
            self.jobs.append(dict(old,run_id=plan['run_id'],folder='arms/'+plan['run_id'],folder_path=folder,
                plan=plan,plan_sha256=parent.digest(plan)))
        manifest={'version':parent.VERSION,'design_sha256':parent.sha(self.parent/'design.json'),
            'bindings':self.jobs[0]['data']['bindings'],'jobs':[
                {k:v for k,v in j.items() if k not in ('folder_path','plan','data')} for j in self.jobs]}
        parent.write(self.parent/'study_manifest.json',manifest)
        parent.write(self.parent/'review_config_recovery.json',dict(parent.funding_review_template(self.parent),reviewed=True))
        self.prior.fund();self.job=self.jobs[0];self.folder=self.job['folder_path']
        parent.write(self.parent/'review_baseline.json',{'reviewed':True,'phase':'baseline',
            'design_sha256':parent.sha(self.parent/'design.json'),'source_sha256':self.prior.sources,
            'protected_modal_usd':5.,'study_manifest_sha256':parent.sha(self.parent/'study_manifest.json')})
        dispatch=parent.make_dispatch(self.job['plan'],self.job['data'],self.prior.sources,parent.sha(self.parent/'review_baseline.json'))
        ledger=parent.read(self.state/'budget.json');parent._bind_child(ledger,self.job,self.parent,dispatch)
        self.call_id='fc-INVENTED-v3-completed';launch=dict(run_id=self.job['run_id'],call_id=self.call_id,
            claim_id=dispatch['claim_id'],intent_sha256=dispatch['intent_sha256'])
        parent.write(self.folder/'dispatch.json',dispatch);parent.write(self.folder/'launch.json',launch)
        self.stack.enter_context(patch.object(parent.contract,'tokenizer_identity',return_value=parent.contract.TOKENIZER))
        batches=[];inventory=[];tokens=self.tokenizer.encode('#### 7' if correct else '#### 8')+[100257]
        for start in range(0,200,8):
            questions=self.job['data']['development'][start:start+8]
            counts=[len(self.tokenizer.encode(parent_worker.render_prompt(self.tokenizer,r))) for r in questions]
            raw={'schema_version':1,'version':parent_worker.VERSION,'run_id':self.job['run_id'],
                'protocol_hash':self.job['plan']['protocol_hash'],'input_sha256':dispatch['input_sha256'],
                'intent_sha256':dispatch['intent_sha256'],'call_id':self.call_id,'arm':'baseline',
                'start':start,'stop':start+8,'question_ids':[r['id'] for r in questions],
                'input_tokens':counts,'generation_ids':[r['id'] for r in questions],
                'generation_token_ids':[tokens for r in questions],'eos_ids':[100257],
                'generation_seconds':40.,'generation_failed':False,'error_type':None}
            rawpath=self.folder/'wire'/f'batch{start:04d}.json';rawpath.parent.mkdir(exist_ok=True)
            rawpath.write_bytes(parent_worker.encoded(raw));parent.write(self.folder/'raw'/rawpath.name,raw)
            batch=parent_worker.derive_with_tokenizer(raw,self.job['data'],self.job['plan'],dispatch,self.tokenizer,expected_call_id=self.call_id)
            batches.append(batch);inventory.append({'start':start,'stop':start+8,'sha256':parent.sha(rawpath)})
        rows=[r for b in batches for r in b['rows']]
        result={'stage':'completed','run_id':self.job['run_id'],'call_id':self.call_id,'plan':self.job['plan'],
            'dispatch':dispatch,'dispatch_sha256':parent.digest(dispatch),'protocol_hash':self.job['plan']['protocol_hash'],
            'supervised_tokens':0,'optimizer_updates':0,'official_test_used':False,'evaluation_complete':True,
            'retained_evaluation_count':200,'raw_pending':False,'evaluations':{'baseline':rows},'batches':batches,
            'raw_batches':inventory,'elapsed_seconds':1100.,'outcomes':{'generated':200},
            'runtime_model_verification':{'fresh_base':True,'adapter_loaded':False,'base_geometry_verified':True,
                'model':parent.contract.MODEL,'revision':parent.contract.REVISION,'model_config_sha256':parent_worker.OFFICIAL_RAW_CONFIG_SHA,
                'inference':{'enable_thinking':True,'max_new_tokens':1024,'input_limit':1536,'evaluation_batch_size':8}},
            'source_verification':{'dependency_versions':parent_worker.DEPENDENCIES,'physical':{
                'packaged_source_hashes_verified':True,'source_hashes':self.prior.sources,
                'source_bundle_sha256':parent.digest(self.prior.sources)}},'tokenizer_verification':parent.contract.TOKENIZER}
        metrics=parent.validate_result(self.job,result);result['metrics']={'baseline':metrics}
        proof={'raw_batches_verified':25,'fixed_denominator':200,'metrics':metrics,'dispatch_sha256':parent.digest(dispatch)}
        parent.write(self.folder/'provider_result.json',result);parent.write(self.folder/'result.json',result)
        parent.write(self.folder/'raw_validation.json',proof)
        terminal=dict(launch,kind='completed',result_sha256=parent.sha(self.folder/'result.json'),
            raw_validation_sha256=parent.sha(self.folder/'raw_validation.json'),observed_at_utc=datetime.now(timezone.utc).isoformat())
        parent.write(self.folder/'provider_terminal.json',terminal)
        child=parent._one(ledger,self.job['run_id']);child.update(status='completed',call_id=self.call_id,
            native_terminal_sha256=parent.sha(self.folder/'provider_terminal.json'),terminal_observed_at_utc=terminal['observed_at_utc'])
        parent.write(self.state/'budget.json',ledger)
        runner=parent.Controller(self.parent)
        with patch.object(runner,'jobs',return_value=self.jobs):self.calibration=runner.calibrate()
        self.stack.enter_context(patch.object(control,'STATE',self.state))
        development_source=self.root/'development_source/fixture.json';development_source.parent.mkdir()
        development_source.write_bytes(self.prior.prior.dev_path.read_bytes())
        self.stack.enter_context(patch.object(control,'DEV',development_source))
        self.stack.enter_context(patch.object(control,'development',return_value=self.prior.prior.dev))
        self.stack.enter_context(patch.object(control,'EXPECTED_ORIGINAL_CALL',self.call_id))
        self.stack.enter_context(patch.object(control,'_parent_tokenizer',return_value=self.tokenizer))
        self.sources={name:'e'*64 for name in control.SOURCES}
        self.stack.enter_context(patch.object(control,'source_inventory',return_value=self.sources))
        control.prepare_design(self.collection,self.output,original=self.parent)
        control.write(self.output/'study_manifest.json',{'INVENTED':'no actual paid study prepared'})
        control.write(self.output/'review_batch_runtime.json',dict(control.funding_review_template(self.output),reviewed=True))
        self.backend=prior.prior.Backend()
    def close(self):self.stack.close();self.prior.close()
    def fund(self):return control.fund_stage_envelope(self.output,backend=self.backend)


class BatchControllerTests(unittest.TestCase):
    def setUp(self):self.f=Fixture();self.addCleanup(self.f.close)
    def test_completed_parent_full_raw_and_calibration_are_required(self):
        proof=control.verify_design(self.f.output)['parent_completed']
        self.assertTrue(proof['parent_completed']);self.assertTrue(proof['runtime_infeasible'])
        self.assertEqual(proof['validated_outputs'],200)
        raw=self.f.folder/'wire/batch0192.json';before=raw.read_bytes();raw.write_bytes(before+b' ')
        with self.assertRaises(ValueError):control.verify_design(self.f.output)
        raw.write_bytes(before)
        original=control.read(self.f.parent/'calibration.json')
        for mutation in ({'pair_runtime_feasible':True},{'baseline_generation_seconds':999.}):
            control.write(self.f.parent/'calibration.json',dict(original,**mutation))
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):control.verify_design(self.f.output)
        control.write(self.f.parent/'calibration.json',original)
    def test_exact_funding_preserves_success_and_all_historical_allowances(self):
        before=control.supported_accounting(control.read(self.f.state/'budget.json'))
        children=deepcopy(control._prior_children(before,control.verify_design(self.f.output)))
        receipt=self.f.fund();after=control.read(self.f.state/'budget.json')
        self.assertEqual(after['reserved']['modal']-before['reserved']['modal'],1.75)
        self.assertEqual(control._prior_children(after,control.verify_design(self.f.output)),children)
        self.assertEqual(children[-1]['status'],'completed');self.assertEqual(receipt['parent_validated_outputs'],200)
        self.assertNotIn('parent_failed_child_run_id',receipt)
        self.assertEqual(receipt['transferred_unused_usd'],3.5);self.assertEqual(receipt['additional_new_reservation_usd'],1.75)
        self.assertEqual(len(after['native_transfer_accounting']['verified_superseded_ids']),3)
        self.assertEqual(control.validate_stage_funding(self.f.output,after)['reserved_usd'],5.25)
        frozen=(self.f.state/'budget.json').read_bytes();self.assertEqual(self.f.fund(),receipt)
        self.assertEqual((self.f.state/'budget.json').read_bytes(),frozen)
    def test_atomic_ledger_commit_receipt_crash_is_idempotent(self):
        actual=control.write
        def interrupted(path,value,**kwargs):
            if Path(path)==self.f.output/'funding.json':raise PermissionError('INVENTED postcommit failure')
            return actual(path,value,**kwargs)
        with patch.object(control,'write',side_effect=interrupted),self.assertRaises(PermissionError):self.f.fund()
        frozen=(self.f.state/'budget.json').read_bytes();self.f.fund()
        self.assertEqual((self.f.state/'budget.json').read_bytes(),frozen)
    def test_unknown_active_or_underprotected_funding_stops_before_intent(self):
        self.f.backend.tasks=1
        with self.assertRaises(ValueError):self.f.fund()
        self.f.backend.tasks=0
        ledger=control.read(self.f.state/'budget.json');ledger['jobs'].append({
            'run_id':'INVENTED-unknown','service':'modal','status':'unknown','reserved_usd':0})
        control.write(self.f.state/'budget.json',ledger)
        with self.assertRaises((ValueError,RuntimeError)):self.f.fund()
        self.assertFalse((self.f.output/'funding_intent.json').exists())
    def test_default_inspection_is_unpaid_and_does_not_open_provider_or_test(self):
        before=(self.f.state/'budget.json').read_bytes()
        with patch.object(control.Backend,'apps',side_effect=AssertionError('No provider')):
            self.assertEqual(control.inspect(self.f.root/'unprepared')['stage'],'unprepared')
            self.assertEqual(control.inspect(self.f.output)['stage'],'plans_prepared')
        self.assertEqual((self.f.state/'budget.json').read_bytes(),before)
    def test_typed_review_and_completed_history_cannot_be_relabelled(self):
        review=control.read(self.f.output/'review_batch_runtime.json')
        control.write(self.f.output/'review_batch_runtime.json',dict(review,parent_validated_outputs=True))
        with self.assertRaises(ValueError):self.f.fund()
        control.write(self.f.output/'review_batch_runtime.json',review)
        ledger=control.read(self.f.state/'budget.json');parent._one(ledger,self.f.job['run_id'])['status']='failed'
        control.write(self.f.state/'budget.json',ledger)
        with self.assertRaises(ValueError):self.f.fund()
    def test_seven_physical_raw_batches_with_optional_unmeasured_memory_and_exact_tail(self):
        from cloud import modal_native_reasoning_batch_v4 as worker
        data=self.f.job['data'];plan=dict(control.contract.protocol(),run_id=self.f.output.name+'_baseline',arm='baseline',
            mode='evaluate_base',token_budget=0,optimizer_updates=0,input_sha256=control.digest(data),
            bindings_sha256=control.digest(data['bindings']))
        plan['protocol_hash']=control.digest(plan)
        dispatch=control.make_dispatch(plan,data,self.f.sources,'b'*64)
        job={'role':'baseline','run_id':plan['run_id'],'plan':plan,'data':data,'folder_path':self.f.output/'arms'/plan['run_id']}
        inventory=[];batches=[];download={};timings=[];call_id='fc-INVENTED-batch32'
        for start,stop in control.contract.evaluation_batches():
            questions=data['development'][start:stop]
            raw={'schema_version':1,'version':worker.VERSION,'run_id':job['run_id'],'protocol_hash':plan['protocol_hash'],
                'input_sha256':dispatch['input_sha256'],'intent_sha256':dispatch['intent_sha256'],'call_id':call_id,'arm':'baseline',
                'start':start,'stop':stop,'question_ids':[r['id'] for r in questions],
                'input_tokens':[len(self.f.tokenizer.encode(worker.render_prompt(self.f.tokenizer,r))) for r in questions],
                'generation_ids':[r['id'] for r in questions],
                'generation_token_ids':[self.f.tokenizer.encode('#### 7')+[100257] for r in questions],
                'eos_ids':[100257],'generation_seconds':10.,'generation_failed':False,'error_type':None,
                'cuda_memory':None,'cuda_memory_error':'RuntimeError'}
            batch=worker.derive_batch(raw,data,plan,dispatch,self.f.tokenizer.decode);batches.append(batch)
            download[f'raw/batch{start:04d}.json']=worker.encoded(raw)
            download[f'batches/batch{start:04d}.json']=worker.encoded(batch)
            inventory.append({'start':start,'stop':stop,'sha256':control.hashlib.sha256(worker.encoded(raw)).hexdigest()})
            timings.append({'start':start,'stop':stop,'cuda_memory':None,'cuda_memory_error':'RuntimeError'})
        result={'stage':'completed','run_id':job['run_id'],'call_id':call_id,'plan':plan,'dispatch':dispatch,
            'supervised_tokens':0,'optimizer_updates':0,'official_test_used':False,'evaluation_complete':True,
            'retained_evaluation_count':200,'raw_pending':False,'elapsed_seconds':100.,'batches':batches,
            'evaluations':{'baseline':[r for b in batches for r in b['rows']]},'raw_batches':inventory,'batch_timings':timings,
            'cuda_memory':worker.aggregate_cuda_memory(batches),'tokenizer_verification':control.contract.TOKENIZER,
            'source_verification':{'dependency_versions':worker.DEPENDENCIES,'physical':{'packaged_source_hashes_verified':True,
                'source_hashes':self.f.sources,'source_bundle_sha256':control.digest(self.f.sources)}},
            'runtime_model_verification':{'fresh_base':True,'adapter_loaded':False,'base_geometry_verified':True,
                'model':control.contract.MODEL,'revision':control.contract.REVISION,'model_config_sha256':worker.OFFICIAL_RAW_CONFIG_SHA,
                'inference':{'enable_thinking':True,'max_new_tokens':control.contract.protocol()['max_new_tokens'],'input_limit':1536,'evaluation_batch_size':32}}}
        result['metrics']={'baseline':control.validate_result(job,result)}
        backend=SimpleNamespace(download=lambda run,relative:download[relative])
        proof=control.verify_raw_result(job,result,dispatch,backend,decode=self.f.tokenizer.decode)
        self.assertEqual(proof['raw_batches_verified'],7);self.assertEqual(proof['fixed_denominator'],200)
        self.assertIsNone(result['cuda_memory']['peak_allocated_bytes'])
        wrong=deepcopy(result);wrong['raw_batches'][-1]['stop']=199
        with self.assertRaises(ValueError):control.verify_raw_result(job,wrong,dispatch,backend,decode=self.f.tokenizer.decode)
        boundary=deepcopy(result);boundary['evaluations']['baseline'][0]['generated_tokens']=2048
        control.validate_result(job,boundary)
        boundary['evaluations']['baseline'][0]['generated_tokens']=2049
        with self.assertRaises(ValueError):control.validate_result(job,boundary)
        self.assertEqual(plan['max_new_tokens'],2048);self.assertEqual(plan['tokens_per_update'],1024)


class AccuracyIndependenceTests(unittest.TestCase):
    def test_zero_accuracy_parent_still_qualifies_by_execution_and_runtime_only(self):
        fixture=Fixture(correct=False)
        try:
            proof=control.verify_design(fixture.output)['parent_completed']
            self.assertEqual(control.read(fixture.folder/'result.json')['metrics']['baseline']['numeric_correct'],0)
            self.assertTrue(proof['runtime_infeasible']);self.assertEqual(proof['validated_outputs'],200)
        finally:fixture.close()


if __name__=='__main__':unittest.main()
