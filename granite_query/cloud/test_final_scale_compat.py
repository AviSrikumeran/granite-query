"""Synthetic metadata and fake CUDA/PEFT boundaries; no model/data downloads."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from cloud import final_scale_compat as api
from cloud import modal_final_compat as worker


def fixture():
    roles={r:sorted(api.REQUIRED.get(r,{'fixture_'+r+'.py'})) for r in api.contract.SOURCE_ROLES}
    roles['contract']=['final_scale_contract.py','final_scale_seal.py']
    roles['receipts']=['final_scale_receipts.py']
    roles['checkpoint_validator']=sorted(set(roles['checkpoint_validator'])|{'valuation_contract.py'})
    sources={name:api.digest('INVENTED source '+name) for names in roles.values() for name in names}
    inventory={'adapter_config.json':'a'*64,'adapter_model.safetensors':'b'*64}
    selected={'model':api.contract.MODEL,'revision':api.contract.REVISION,'checkpoint_id':'invented-checkpoint',
        'adapter_inventory_sha256':api.digest(inventory),'development_evidence_sha256':'c'*64}
    value=api.contract.build_contract(1000,source_hashes=sources,source_roles=roles,selected=selected)
    original=[{'id':f'gsm8k:train:{i:05d}','prompt':f'INVENTED arithmetic question {i}',
        'gold_answer':'7','source_split':'train','reference_solution':'INVENTED REFERENCE'} for i in range(200)]
    raw=b''.join(api.encoded(r) for r in original);dev_sha=api.sha(raw)
    rows=[]
    for original_row in original:
        row={k:original_row[k] for k in ('id','prompt','gold_answer','source_split')}
        row['source_index']=int(row['id'].rsplit(':',1)[1]);row['input_sha256']=api.input_hash(row,api.contract.PREFIX);rows.append(row)
    auth=api.record({'schema_version':1,'role':api.ROLE,'sealed':{'contract':value,'checkpoint':{
        'selected':selected,'adapter_files_sha256':inventory}},'adapter_path':'fixture/adapter',
        'model_config':{'volume_path':'fixture/model/config.json','sha256':api.layout.EVIDENCE['local_config']['sha256'],'bytes':1000},
        'development_source_sha256':dev_sha},'authorization_sha256')
    payload={'schema_version':1,'role':api.ROLE,'official_test_used':False,'training_performed':False,
        'development_source_sha256':dev_sha,'development_source_jsonl':raw.decode(),'development':rows}
    plan=api.record({'schema_version':1,'version':api.VERSION,'role':api.ROLE,'run_id':'fixture-compat','seed':42,**api.FIXED,
        'model':api.contract.MODEL,'revision':api.contract.REVISION,'authorization_sha256':auth['authorization_sha256'],
        'source_bundle_sha256':api.digest(sources),'inference_sha256':api.digest(value['protocol']['inference']),
        'adapter_model_sha256':'b'*64,'adapter_inventory_sha256':selected['adapter_inventory_sha256'],
        'development_source_sha256':dev_sha,'development_ids':[r['id'] for r in rows],'development_rows_sha256':api.digest(rows),
        'source_cohort_plan_sha256':api.COHORT_PLAN_SHA,'teaching_source_sha256':api.TEACHING_SHA,'normalized_teaching_overlap':0,
        'input_volume_path':'final-compat/fixture-compat/development_input.json','input_sha256':api.sha(api.encoded(payload)),
        'input_bytes':len(api.encoded(payload))},'plan_sha256')
    descriptor={'volume_path':plan['input_volume_path'],'sha256':plan['input_sha256'],'bytes':plan['input_bytes'],'plan_sha256':plan['plan_sha256']}
    dispatch=api.record({'role':'development_compatibility_dispatch','reviewed':True,'run_id':plan['run_id'],
        'plan_sha256':plan['plan_sha256'],'authorization_sha256':auth['authorization_sha256'],
        'source_bundle_sha256':plan['source_bundle_sha256'],'reserved_modal_usd':'1.75','protected_final_modal_usd':'12.25',
        'protected_api_modal_usd':'1','official_access_authorized':False,'claim_id':'a'*32},'dispatch_sha256')
    return value,plan,descriptor,auth,dispatch,payload


class FakeRuntime:
    def __init__(self,payload,auth,*,bad_assets=False,bad_model=False,bad_generation=False,bad_raw=False,clock=0,long_first=False):
        self.payload=payload;self.auth=auth;self.events=[];self.clock=clock;self.call_id='fc-invented-compat';self.eos=[100257]
        self.proofs={};self.raw={};self.batches={};self.bad_assets=bad_assets;self.bad_model=bad_model
        self.bad_generation=bad_generation;self.bad_raw=bad_raw;self.long_first=long_first
    def elapsed(self):return self.clock
    def begin(self,*args):self.events.append('begin')
    def select_role(self,role):self.role=role;self.events.append('select-'+role)
    def status(self,*args,**kwargs):pass
    def verify_assets(self,auth):
        self.events.append('verify-'+self.role);self.clock+=1
        if self.bad_assets:raise ValueError('INVENTED artifact failure')
    def load_model(self,auth,role,seed):
        self.events.append('load-'+role);self.clock+=2
        if self.bad_model:raise ValueError('INVENTED PEFT failure')
        p=auth['sealed']['contract']['protocol']
        self.proofs[role]={'peft_load_succeeded':True,'runtime_layout_verified':True,'loaded_adapter_values_verified':True,
            'finite_saved_cpu_values':True,'baseline_adapter_unloaded':role=='base','dependency_versions':api.DEPENDENCIES,
            'source_bundle_sha256':api.digest(p['source_hashes']),'model_config_sha256':api.layout.EVIDENCE['local_config']['sha256'],
            'adapter_inventory_sha256':p['selected']['adapter_inventory_sha256'],'adapter_model_sha256':'b'*64,
            'tensor_count':160,'parameter_count':api.layout.PARAMETER_COUNT}
    def read_input(self,descriptor):
        assert self.events.index('verify-base')<self.events.index('load-base')
        self.events.append('read-input');return self.payload
    def input_counts(self,rows):return [1537 if self.long_first and r['id']==self.payload['development'][0]['id'] else 10 for r in rows]
    def generate(self,rows):
        self.events.append('generate-'+self.role);self.clock+=.5
        if self.bad_generation:raise RuntimeError('INVENTED generation failure')
        return [[77,100257] for _ in rows],.5
    def write_raw(self,start,raw):
        self.events.append('raw-'+self.role)
        if self.bad_raw:raise OSError('INVENTED raw persistence failure')
        self.raw[(self.role,start)]=raw;return api.sha(api.encoded(raw))
    def decode(self,ids):
        assert 'raw-'+self.role in self.events
        self.events.append('decode-'+self.role);return '#### 7'
    def write_batch(self,start,batch):self.batches[(self.role,start)]=batch
    def release_model(self):self.events.append('release-'+self.role)
    def finish(self,result):self.result=result


class CompatTests(unittest.TestCase):
    def run_fixture(self,**options):
        value,plan,descriptor,auth,dispatch,payload=fixture();runtime=FakeRuntime(payload,auth,**options)
        with patch.object(api,'DEVELOPMENT_SHA',plan['development_source_sha256']):
            result=worker.run_compat(plan,descriptor,auth,dispatch,runtime=runtime)
        return value,plan,auth,payload,runtime,result

    def test_complete_independent_roles_actual_subset_and_controller_evidence(self):
        value,plan,auth,payload,runtime,result=self.run_fixture(long_first=True)
        self.assertEqual(result['stage'],'completed');self.assertEqual(len(result['evaluations']['base']),200)
        self.assertEqual(len(result['evaluations']['chosen']),200)
        self.assertLess(runtime.events.index('release-base'),runtime.events.index('load-chosen'))
        self.assertEqual(runtime.events.count('read-input'),1)
        first=result['evaluations']['base'][:8]
        self.assertEqual(first[0]['outcome'],'input_limit');self.assertEqual(first[0]['elapsed_seconds'],0)
        self.assertAlmostEqual(sum(r['elapsed_seconds'] for r in first),.5)
        with patch.object(api,'DEVELOPMENT_SHA',plan['development_source_sha256']):
            evidence=api.validate_result(value,plan,payload,result)
        self.assertTrue(evidence['peft_load_succeeded']);self.assertTrue(evidence['loaded_adapter_values_verified'])
        self.assertEqual(evidence['dependency_versions'],api.DEPENDENCIES)
        self.assertEqual(evidence['adapter_model_sha256'],'b'*64)
        self.assertEqual(evidence['calibration']['load_allowance_seconds'],80)
        self.assertEqual(evidence['calibration']['total_compatibility_worker_seconds'],31)
        self.assertFalse(result['official_test_used']);self.assertFalse(result['training_performed'])

    def test_assets_and_peft_fail_before_input_and_never_emit_evidence(self):
        for option in ({'bad_assets':True},{'bad_model':True}):
            *_,runtime,result=self.run_fixture(**option)
            self.assertNotIn('read-input',runtime.events);self.assertIsNone(result['runtime_evidence'])
            self.assertNotEqual(result['stage'],'completed')

    def test_generation_raw_and_time_failures_preserve_partial_denominator(self):
        *_,runtime,result=self.run_fixture(bad_generation=True,long_first=True)
        self.assertEqual(result['stage'],'failed');self.assertEqual(len(result['evaluations']['base']),8)
        self.assertEqual(sum(r['outcome']=='failed' for r in result['evaluations']['base']),7)
        self.assertEqual(result['evaluations']['chosen'],[]);self.assertIsNone(result['runtime_evidence'])
        *_,runtime,result=self.run_fixture(bad_raw=True)
        self.assertTrue(result['raw_pending']);self.assertFalse(any(e.startswith('decode-') for e in runtime.events))
        *_,runtime,result=self.run_fixture(clock=1601)
        self.assertEqual(result['stage'],'timed_out');self.assertIsNone(result['runtime_evidence'])

    def test_source_bytes_official_ids_and_unreviewed_dispatch_rejected(self):
        value,plan,descriptor,auth,dispatch,payload=fixture()
        with patch.object(api,'DEVELOPMENT_SHA',plan['development_source_sha256']):
            changed=copy.deepcopy(payload);changed['development_source_jsonl']+=' '
            with self.assertRaises(ValueError):api.validate_payload(changed,plan,auth)
            changed=copy.deepcopy(payload);changed['development'][0]['id']='gsm8k:test:00000'
            with self.assertRaises(ValueError):api.validate_payload(changed,plan,auth)
            changed=copy.deepcopy(dispatch);changed['reviewed']=False;changed=api.record({k:v for k,v in changed.items() if k!='dispatch_sha256'},'dispatch_sha256')
            with self.assertRaises(ValueError):api.validate_dispatch(plan,auth,changed)
        with self.assertRaises(ValueError):api.prepare(value,auth['sealed']['checkpoint'],'not-opened','not-created',source_paths={},adapter_volume_path='fixture/adapter',model_config={})

    def test_evidence_requires_observed_versions_and_complete_hashed_batches(self):
        value,plan,auth,payload,runtime,result=self.run_fixture()
        bad=copy.deepcopy(result);bad['batches']['chosen'].pop()
        with patch.object(api,'DEVELOPMENT_SHA',plan['development_source_sha256']),self.assertRaises(ValueError):
            api.validate_result(value,plan,payload,bad)
        proofs=copy.deepcopy(runtime.proofs);proofs['chosen']['loaded_adapter_values_verified']=False
        with self.assertRaises(ValueError):api.make_evidence(value,plan,auth,call_id=runtime.call_id,proofs=proofs,
            calibration=result['runtime_evidence']['calibration'],evaluations=result['evaluations'])
        proofs=copy.deepcopy(runtime.proofs);proofs['chosen']['dependency_versions']={'torch':'invented'}
        with self.assertRaises(ValueError):api.make_evidence(value,plan,auth,call_id=runtime.call_id,proofs=proofs,
            calibration=result['runtime_evidence']['calibration'],evaluations=result['evaluations'])

    def test_calibration_uses_maximum_role_load_not_summed_loads(self):
        value,_,_,_,_,result=self.run_fixture()
        timings=copy.deepcopy(result['runtime_timings'])
        timings['base']['role_wall_seconds']=timings['base']['generation_seconds']+100
        timings['chosen']['role_wall_seconds']=timings['chosen']['generation_seconds']+200
        total=sum(t['role_wall_seconds'] for t in timings.values())
        calibration=api.calibration_record(value,result['evaluations'],timings,total)
        self.assertEqual(calibration['load_allowance_seconds'],215)
        self.assertEqual(calibration['load_io_buffer_seconds'],15)
        self.assertEqual(calibration['total_compatibility_worker_seconds'],total)
    def test_actual_runtime_cpu_finiteness_precedes_peft_boundary(self):
        parent=api.ROOT/'runs/test_final_scale_compat';parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as temporary:
            folder=Path(temporary);adapter=folder/'adapter';adapter.mkdir()
            (folder/'config.json').write_text('{}');(adapter/'adapter_config.json').write_text('{}')
            runtime=worker.Runtime.__new__(worker.Runtime);runtime.config_path=folder/'config.json';runtime.adapter=adapter
            runtime.folder=folder;runtime.proofs={};runtime.dependencies=api.DEPENDENCIES;runtime.raw_dependencies=api.DEPENDENCIES
            runtime.source_proof={'source_bundle_sha256':'d'*64}
            runtime.asset_proof={'model_config_sha256':'e'*64,'adapter_inventory_sha256':'f'*64,'adapter_files_sha256':{'adapter_model.safetensors':'b'*64}}
            events=[]
            def finite(t):events.append('cpu-finite');return SimpleNamespace(all=lambda:True)
            def peft(*args):
                events.append('peft')
                (folder/'runtime_model_verification.json').write_text(json.dumps({'complete_expected_layout_verified':True,'tensor_count':160,
                    'runtime_peft_load_verified':True,'runtime_adapter_values_match_sealed_file':True,'baseline_adapter_unloaded':True}))
            fake_torch=SimpleNamespace(isfinite=finite)
            fake_safe=SimpleNamespace(load_file=lambda *a,**k:{'invented':SimpleNamespace(shape=(8,2))})
            with patch.dict(sys.modules,{'torch':fake_torch,'safetensors.torch':fake_safe}),patch.object(worker.layout,'validate_layout'),patch.object(worker.shared.Runtime,'load_model',side_effect=peft):
                runtime.load_model({},'base',42)
            self.assertLess(events.index('cpu-finite'),events.index('peft'))
            self.assertTrue(runtime.proofs['base']['finite_saved_cpu_values'])

    def test_explicit_prepare_freezes_only_exact_disjoint_train_artifact(self):
        value,_,_,auth,_,payload=fixture()
        parent=api.ROOT/'runs/test_final_scale_compat';parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as temporary:
            root=Path(temporary);cohort=root/'cohort';cohort.mkdir()
            development=payload['development_source_jsonl'].encode('utf-8')
            teaching=[{'id':f'gsm8k:train:{i:05d}','prompt':f'INVENTED separate teaching {i}','gold_answer':'7','source_split':'train'} for i in range(1000,3048)]
            teaching_raw=b''.join(api.encoded(r) for r in teaching)
            source_plan={'official_test_accessed':False,'development_count':200,'teaching_count':2048,
                'development_ids':[r['id'] for r in payload['development']],'teaching_ids':[r['id'] for r in teaching]}
            plan_raw=api.encoded(source_plan)
            (cohort/'development.jsonl').write_bytes(development);(cohort/'candidates.jsonl').write_bytes(teaching_raw);(cohort/'plan.json').write_bytes(plan_raw)
            output=root/'compat-fixture'
            with patch.object(api,'HUMAN',cohort),patch.object(api,'DEVELOPMENT_SHA',api.sha(development)), \
                 patch.object(api,'TEACHING_SHA',api.sha(teaching_raw)),patch.object(api,'COHORT_PLAN_SHA',api.sha(plan_raw)), \
                 patch.object(api.seal,'_source_inventory',return_value=({},{})), \
                 patch.object(api.seal,'begin_access',side_effect=AssertionError('compat must not create a final permit')):
                metadata=api.prepare(value,auth['sealed']['checkpoint'],cohort/'development.jsonl',output,authorized=True,
                    source_paths={},adapter_volume_path='fixture/adapter',model_config=auth['model_config'])
                self.assertEqual(metadata['stage'],'prepared_development_only_not_dispatched')
                self.assertEqual(sorted(p.name for p in output.iterdir()),['authorization.json','input.json','input_descriptor.json','plan.json'])
                self.assertEqual(api.prepare(value,auth['sealed']['checkpoint'],cohort/'development.jsonl',output,authorized=True,
                    source_paths={},adapter_volume_path='fixture/adapter',model_config=auth['model_config']),metadata)
                teaching[0]['prompt']=payload['development'][0]['prompt'];changed=b''.join(api.encoded(r) for r in teaching)
                (cohort/'candidates.jsonl').write_bytes(changed)
                with patch.object(api,'TEACHING_SHA',api.sha(changed)),self.assertRaisesRegex(ValueError,'overlaps'):
                    api.prepare(value,auth['sealed']['checkpoint'],cohort/'development.jsonl',root/'blocked',authorized=True,
                        source_paths={},adapter_volume_path='fixture/adapter',model_config=auth['model_config'])


if __name__=='__main__':unittest.main()
