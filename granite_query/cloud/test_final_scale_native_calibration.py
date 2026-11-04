"""Invented paired400 provider/raw bytes; no data/provider/model operations."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cloud import final_scale_native_calibration as bridge
from cloud import final_scale_compat as compat
from cloud import test_final_scale_compat as fixtures
from cloud import modal_final_compat as worker


class Tokenizer:
    chat_template = 'INVENTED tokenizer template'
    backend_tokenizer = SimpleNamespace(to_str=lambda:'INVENTED tokenizer backend')
    eos_token = '<|im_end|>'; eos_token_id = 100257
    def apply_chat_template(self,messages,**kwargs):
        if kwargs != {'tokenize':False,'add_generation_prompt':True,'enable_thinking':False}:
            raise AssertionError('Wrong inference recipe')
        return 'INVENTED rendered '+messages[0]['content']
    def encode(self,text,**kwargs):
        if kwargs != {'add_special_tokens':False}: raise AssertionError('Special-token recipe differs')
        return [1]*10
    def decode(self,ids,**kwargs): return '#### 7'


def bundle(*,source_paths=None,long_first=False):
    required = dict(compat.REQUIRED)
    required['checkpoint_validator'] = set(required['checkpoint_validator'])|{'final_scale_native_calibration.py'}
    with patch.object(compat,'REQUIRED',required):
        value,plan,descriptor,auth,dispatch,payload = fixtures.fixture()
    if source_paths is not None:
        hashes = {name:bridge.sha(path.read_bytes()) for name,path in source_paths.items()}
        value = compat.contract.build_contract(1000,source_hashes=hashes,
            source_roles=value['protocol']['source_roles'],selected=value['protocol']['selected'])
        auth = compat.record({**{k:v for k,v in auth.items() if k!='authorization_sha256'},
            'sealed':{**auth['sealed'],'contract':value}},'authorization_sha256')
        plan = compat.record({**{k:v for k,v in plan.items() if k!='plan_sha256'},
            'authorization_sha256':auth['authorization_sha256'],
            'source_bundle_sha256':compat.digest(hashes),
            'inference_sha256':compat.digest(value['protocol']['inference'])},'plan_sha256')
        descriptor = dict(descriptor,plan_sha256=plan['plan_sha256'])
        dispatch = compat.record({**{k:v for k,v in dispatch.items() if k!='dispatch_sha256'},
            'authorization_sha256':auth['authorization_sha256'],'plan_sha256':plan['plan_sha256'],
            'source_bundle_sha256':plan['source_bundle_sha256']},'dispatch_sha256')
    runtime = fixtures.FakeRuntime(payload,auth,long_first=long_first)
    with patch.object(compat,'DEVELOPMENT_SHA',plan['development_source_sha256']):
        result = worker.run_compat(plan,descriptor,auth,dispatch,runtime=runtime)
    original = compat.encoded(result)
    launch = {'run_id':plan['run_id'],'call_id':runtime.call_id,'plan_sha256':plan['plan_sha256'],
        'dispatch_sha256':dispatch['dispatch_sha256'],'claim_id':dispatch['claim_id']}
    terminal = dict(launch,kind='completed',confirmed_terminal=True,result_sha256=bridge.sha(original),
        observed_at_utc='2026-11-04T03:00:00+00:00')
    inputs = {'plan':plan,'payload':payload,'input_descriptor':descriptor,'authorization':auth,
        'dispatch':dispatch,'launch':launch,'provider_terminal':terminal,'provider_result_bytes':original,
        'raw_batches':{role:{start:compat.encoded(runtime.raw[role,start]) for start in range(0,200,8)}
            for role in bridge.ROLES},'tokenizer':Tokenizer()}
    return value,inputs


class NativeCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.bits = {'chat_template_sha256':bridge.sha(Tokenizer.chat_template.encode()),
            'backend_sha256':bridge.sha(Tokenizer.backend_tokenizer.to_str().encode()),
            'eos_token':'<|im_end|>','eos_token_id':100257}
        self.patch = patch.object(bridge,'TOKENIZER_BITS',self.bits); self.patch.start();self.addCleanup(self.patch.stop)
        self.value,self.inputs = bundle()
        self.development_patch = patch.object(compat,'DEVELOPMENT_SHA',self.inputs['plan']['development_source_sha256'])
        self.development_patch.start();self.addCleanup(self.development_patch.stop)

    def validate(self,inputs=None,value=None):
        return bridge.validate_bundle(self.value if value is None else value,**(self.inputs if inputs is None else inputs))

    def changed_result(self,mutate):
        inputs = deepcopy(self.inputs); result = bridge.parse(inputs['provider_result_bytes']);mutate(result)
        inputs['provider_result_bytes'] = compat.encoded(result)
        inputs['provider_terminal']['result_sha256'] = bridge.sha(inputs['provider_result_bytes'])
        return inputs

    def test_one_original400_result_is_replayed_purely_without_provider_wrappers(self):
        with patch('builtins.open',side_effect=AssertionError('Pure validator must not open paths')), \
             patch.object(Path,'read_bytes',side_effect=AssertionError('Pure validator must not inspect actual files')):
            result = self.validate()
        self.assertEqual(result['role'],'native_paired400_development_calibration')
        hashes = result['calibration_candidate']['evidence_hashes']
        self.assertEqual(hashes,{'base':bridge.sha(self.inputs['provider_result_bytes']),
            'chosen':bridge.sha(self.inputs['provider_result_bytes'])})
        self.assertEqual([result['per_role'][role]['count'] for role in bridge.ROLES],[200,200])
        self.assertFalse(result['old_per_role_physical_seal_format_compatible'])
        self.assertFalse(result['final_access_authorized']);self.assertFalse(result['funded_entrypoint_verified'])
        self.assertNotIn('INVENTED arithmetic question',json.dumps(result))
        self.assertNotIn('#### 7',json.dumps(result))
        self.assertEqual(result['bridge_sha256'],bridge.digest({k:v for k,v in result.items() if k!='bridge_sha256'}))

    def test_provider_terminal_call_claim_plan_result_and_confirmation_must_all_match(self):
        for key,value in (('call_id','fc-other'),('claim_id','b'*32),('plan_sha256','0'*64),
                ('dispatch_sha256','0'*64),('result_sha256','0'*64),('confirmed_terminal',False),('kind','running')):
            inputs = deepcopy(self.inputs);inputs['provider_terminal'][key] = value
            with self.subTest(key=key),self.assertRaises(ValueError):self.validate(inputs)

    def test_raw_bytes_counts_token_outputs_and_decoding_cannot_be_substituted(self):
        for kind in ('wire_space','input_counts','token_ids','raw_call'):
            inputs = deepcopy(self.inputs);original = inputs['raw_batches']['base'][0]
            if kind=='wire_space':inputs['raw_batches']['base'][0] = original+b' '
            else:
                raw = bridge.parse(original)
                if kind=='input_counts':raw['input_tokens'][0] = 11
                if kind=='token_ids':raw['generated_ids'][0] = [78,100257]
                if kind=='raw_call':raw['call_id'] = 'fc-other'
                inputs['raw_batches']['base'][0] = compat.encoded(raw)
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.validate(inputs)
        inputs = deepcopy(self.inputs);inputs['tokenizer'].decode = lambda *a,**k:'#### 8'
        with self.assertRaises(ValueError):self.validate(inputs)

    def test_partial_pending_input_limit_or_missing_role_does_not_become_calibration(self):
        for mutate in (lambda r:r.update(raw_pending=True),lambda r:r['batches']['chosen'].pop(),
                lambda r:r['evaluations']['chosen'].pop(),lambda r:r.update(stage='timed_out')):
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):self.validate(self.changed_result(mutate))
        inputs = deepcopy(self.inputs);inputs['raw_batches']['base'].pop(0)
        with self.assertRaises(ValueError):self.validate(inputs)
        value,inputs = bundle(long_first=True)
        with self.assertRaises(ValueError):bridge.validate_bundle(value,**inputs)

    def test_deep_runtime_proof_and_observed_timing_are_revalidated(self):
        def bad_proof(result):
            e = result['runtime_evidence'];e['proofs_by_role']['chosen']['loaded_adapter_values_verified'] = False
            result['runtime_evidence'] = compat.record({k:v for k,v in e.items() if k!='evidence_sha256'},'evidence_sha256')
        with self.assertRaises(ValueError):self.validate(self.changed_result(bad_proof))
        with self.assertRaises(ValueError):
            self.validate(self.changed_result(lambda r:r['runtime_timings']['chosen'].update(generation_seconds=99)))
        with self.assertRaises(ValueError):
            self.validate(self.changed_result(lambda r:r.update(elapsed_seconds=1)))

    def test_wrong_original_input_source_adapter_or_inference_binding_fails(self):
        inputs = deepcopy(self.inputs);inputs['payload']['development'][0]['gold_answer'] = '8'
        with self.assertRaises(ValueError):self.validate(inputs)
        for key in ('source_bundle_sha256','adapter_inventory_sha256','inference_sha256'):
            inputs = deepcopy(self.inputs);p = inputs['plan'];p[key] = '0'*64
            inputs['plan'] = compat.record({k:v for k,v in p.items() if k!='plan_sha256'},'plan_sha256')
            with self.subTest(key=key),self.assertRaises(ValueError):self.validate(inputs)

    def test_parser_rejects_all_tree_nonfinite_surrogate_duplicate_or_recursion_poisoning(self):
        for raw in (b'{"x":NaN}',b'{"x":1e400}',b'{"x":"\\ud800"}',b'{"x":1,"x":2}',b'['*2000+b'0'+b']'*2000):
            with self.subTest(raw=raw[:30]),self.assertRaises(ValueError):bridge.parse(raw)
        inputs = deepcopy(self.inputs);inputs['provider_result_bytes'] = b'{"x":"\\ud800"}'
        with self.assertRaises(ValueError):self.validate(inputs)

    def test_bridge_source_role_and_actual_tokenizer_bits_are_required(self):
        value = deepcopy(self.value)
        value['protocol']['source_roles']['checkpoint_validator'].remove('final_scale_native_calibration.py')
        with self.assertRaises(ValueError):self.validate(value=value)
        with patch.object(bridge,'TOKENIZER_BITS',dict(self.bits,backend_sha256='0'*64)),self.assertRaises(ValueError):self.validate()

    def test_readonly_physical_bridge_binds_exact_source_paths_and_original_native_files(self):
        parent = compat.ROOT/'runs/test_final_scale_native_calibration';parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as temporary:
            folder = Path(temporary);sources_dir = folder/'fixture_sources';sources_dir.mkdir()
            paths = {}
            for name in self.value['protocol']['source_hashes']:
                actual = compat.ROOT/name
                if not actual.exists():actual = sources_dir/name;actual.write_text('INVENTED fixture source\n')
                paths[name] = actual
            value,inputs = bundle(source_paths=paths)
            for name,key in (('plan','plan'),('input','payload'),('input_descriptor','input_descriptor'),
                    ('authorization','authorization'),('dispatch','dispatch'),('launch','launch'),('provider_terminal','provider_terminal')):
                (folder/(name+'.json')).write_bytes(compat.encoded(inputs[key]))
            (folder/'provider_result.json').write_bytes(inputs['provider_result_bytes'])
            for role in bridge.ROLES:
                directory = folder/'roles'/role/'raw';directory.mkdir(parents=True)
                for start,raw in inputs['raw_batches'][role].items():(directory/f'batch{start:04d}.json').write_bytes(raw)
            before = {str(path.relative_to(folder)):bridge.sha(path.read_bytes()) for path in folder.rglob('*') if path.is_file()}
            result = bridge.inspect_bundle(folder,tokenizer=Tokenizer(),source_paths=paths)
            after = {str(path.relative_to(folder)):bridge.sha(path.read_bytes()) for path in folder.rglob('*') if path.is_file()}
            self.assertEqual(before,after);self.assertTrue(result['physical_source_files_verified'])
            self.assertFalse(result['provider_status_queried']);self.assertFalse(result['files_written'])
            self.assertFalse(any(path.name in ('candidates.jsonl','development.jsonl','requests.jsonl') for path in folder.rglob('*')))
            missing = dict(paths);missing.pop('final_scale_native_calibration.py')
            with self.assertRaises(ValueError):bridge.inspect_bundle(folder,tokenizer=Tokenizer(),source_paths=missing)
            # An identical historical/copied source has the approved hash but
            # cannot stand in for the implementation actually doing replay.
            for module in (compat,compat.execution,compat.layout):
                alternate = sources_dir/Path(module.__file__).name
                alternate.write_bytes(Path(module.__file__).read_bytes())
                copied = dict(paths,**{alternate.name:alternate})
                with self.subTest(module=alternate.name),self.assertRaisesRegex(ValueError,'exact loaded bridge and compatibility'):
                    bridge.inspect_bundle(folder,tokenizer=Tokenizer(),source_paths=copied)

    def test_native_study_note_is_prospective_and_does_not_mandate_another_paid400_call(self):
        note = bridge.native_study_adaptation_note()
        self.assertFalse(note['native_study_requires_another_paid400_call'])
        self.assertFalse(note['actual_results_asserted']);self.assertFalse(note['implemented_by_this_module'])
        self.assertIn('1024',note['inference_warning']);self.assertIn('512',note['inference_warning'])


if __name__=='__main__':unittest.main()
