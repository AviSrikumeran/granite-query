"""Prospective batch32 fixtures; no GPU, provider, funding or dataset access."""
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import hashlib
import math
import sys
import unittest
from unittest.mock import Mock, patch

from cloud import native_reasoning_batch_contract_v4 as contract
from cloud import native_reasoning_contract as original
from cloud import modal_native_reasoning_batch_v4 as worker
from cloud import test_modal_native_reasoning as old


@contextmanager
def fixture(role='baseline'):
    with patch.object(old, 'worker', worker), old.fixture(role) as (data, prior, _, tokenizer):
        plan = dict(prior, **contract.protocol())
        dispatch = old.bind(data, plan)
        yield data, plan, dispatch, tokenizer


def memory(count, padded=30, index=1):
    return {'measurement_available': True, 'scope': worker.CUDA_MEMORY_SCOPE,
        'generation_count': count, 'padded_input_tokens': padded,
        'peak_allocated_bytes': 10_000_000_000 + index * 1024,
        'peak_reserved_bytes': 12_000_000_000 + index * 1024,
        'device_total_memory_bytes': 80 * 1024**3}


class Runtime(old.FakeRuntime):
    def __init__(self, tokenizer, *, missing_memory=False, **kwargs):
        super().__init__(tokenizer, **kwargs)
        self.missing_memory = missing_memory; self.last_memory = None; self.subset_sizes = []
    def generate(self, rows):
        self.subset_sizes.append(len(rows)); self.last_memory = memory(len(rows), index=len(self.subset_sizes))
        return super().generate(rows)
    def generation_memory(self): return None if self.missing_memory else deepcopy(self.last_memory)
    def generation_memory_diagnostic(self): return 'InventedTelemetryError' if self.missing_memory else None


class Batch32Tests(unittest.TestCase):
    def execute(self, data, plan, dispatch, runtime):
        with patch.object(original, 'tokenizer_identity', return_value=dict(contract.TOKENIZER)):
            return worker.run_native(data, plan, dispatch, runtime=runtime)

    def test_protocol_only_changes_batch_version_and_exact_tail_partition(self):
        before = deepcopy(original.protocol())
        current = contract.protocol()
        for key, value in before.items():
            if key not in ('version', 'evaluation_batch_size', 'max_new_tokens'): self.assertEqual(current[key], value)
        self.assertEqual(current['evaluation_batch_size'], 32)
        self.assertEqual(current['evaluation_batch_count'], 7)
        self.assertEqual(current['max_new_tokens'],2048)
        self.assertLessEqual(current['input_limit']+current['max_new_tokens'],current['context_limit'])
        self.assertEqual(current['tokens_per_update'],1024)
        self.assertEqual(before['max_new_tokens'],1024)
        self.assertEqual(contract.evaluation_batches(), [(0,32),(32,64),(64,96),(96,128),(128,160),(160,192),(192,200)])
        self.assertEqual(original.protocol(), before)
        with self.assertRaises(ValueError): contract.evaluation_batches(199)
        with fixture('thinking') as (data, plan, dispatch, _):
            frozen = deepcopy((data, plan))
            rows = contract.validate_bundle(data, plan)
            self.assertEqual(sum(row['supervised_tokens'] for row in rows.values()), 16384)
            self.assertEqual((data, plan), frozen)
            altered = deepcopy(plan); altered['evaluation_batch_size'] = 8
            altered['protocol_hash'] = contract.digest({k:v for k,v in altered.items() if k != 'protocol_hash'})
            with self.assertRaises(ValueError): contract.validate_bundle(data, altered)
            data['development'].reverse(); old.bind(data, plan)
            with self.assertRaises(ValueError): contract.validate_bundle(data, plan)

    def test_full200_seven_batches_tail8_and_real_subset_latency_denominator(self):
        with fixture() as (data, plan, dispatch, tokenizer):
            runtime = Runtime(tokenizer, first_long=True)
            result = self.execute(data, plan, dispatch, runtime)
            self.assertEqual(result['stage'], 'completed'); self.assertTrue(result['evaluation_complete'])
            self.assertEqual(runtime.subset_sizes, [31,32,32,32,32,32,8])
            self.assertEqual(len(result['raw_batches']), 7)
            self.assertEqual([(b['start'], b['stop']) for b in result['raw_batches']], contract.evaluation_batches())
            rows = result['evaluations']['baseline']
            self.assertEqual([row['id'] for row in rows], [row['id'] for row in data['development']])
            self.assertEqual(result['metrics']['baseline']['count'], 200)
            self.assertEqual(result['metrics']['baseline']['numeric_correct'], 199)
            self.assertEqual(rows[0]['outcome'], 'input_limit')
            self.assertEqual(rows[1]['elapsed_seconds'], 1/31)
            self.assertEqual(rows[-1]['elapsed_seconds'], 1/8)
            self.assertAlmostEqual(result['metrics']['baseline']['latency_seconds_total'], 7)
            self.assertEqual(result['cuda_memory']['measured_generation_batches'], 7)
            self.assertEqual(result['cuda_memory']['peak_allocated_bytes'], memory(8,index=7)['peak_allocated_bytes'])
            self.assertEqual(result['cuda_memory']['peak_reserved_bytes'], memory(8,index=7)['peak_reserved_bytes'])
            self.assertEqual([b['cuda_memory']['generation_count'] for b in result['batch_timings']], runtime.subset_sizes)
            self.assertLess(runtime.events.index('raw_durable'), runtime.events.index('decode'))

    def test_training_exposure_and_updates_are_unchanged_with_new_evaluation(self):
        with fixture('thinking') as (data, plan, dispatch, tokenizer):
            runtime = Runtime(tokenizer)
            result = self.execute(data, plan, dispatch, runtime)
            self.assertEqual((runtime.steps, result['optimizer_updates'], result['supervised_tokens']), (16,16,16384))
            self.assertEqual(sum(window['supervised_tokens'] for _,window in runtime.windows), 16384)
            self.assertEqual([n for n,_ in runtime.saves], [4,8,12,16])
            self.assertEqual(len(result['raw_batches']), 7)
            self.assertEqual(result['metrics']['thinking']['count'], 200)

    def test_tail_replay_uses_exact_pinned_prompt_counts_and_call(self):
        with fixture() as (data, plan, dispatch, tokenizer):
            questions = data['development'][192:200]
            counts = [len(tokenizer.encode(worker.render_prompt(tokenizer, row), add_special_tokens=False)) for row in questions]
            raw = {'schema_version': 1, 'version': worker.VERSION, 'run_id': plan['run_id'],
                'protocol_hash': plan['protocol_hash'], 'input_sha256': dispatch['input_sha256'],
                'intent_sha256': dispatch['intent_sha256'], 'call_id': 'fc-INVENTED-batch32', 'arm': 'baseline',
                'start': 192, 'stop': 200, 'question_ids': [r['id'] for r in questions], 'input_tokens': counts,
                'generation_ids': [r['id'] for r in questions],
                'generation_token_ids': [tokenizer.encode('#### 7')+[100257] for _ in questions],
                'eos_ids': [100257], 'generation_seconds': 2., 'generation_failed': False, 'error_type': None,
                'cuda_memory': memory(8,max(counts)), 'cuda_memory_error': None}
            with patch.object(original, 'tokenizer_identity', return_value=dict(contract.TOKENIZER)):
                value = worker.derive_with_tokenizer(raw,data,plan,dispatch,tokenizer,expected_call_id=raw['call_id'])
                self.assertEqual(len(value['rows']),8)
                for changes in ({'start':193}, {'stop':199}, {'call_id':'fc-FOREIGN'}, {'input_tokens':[1]*8}):
                    with self.subTest(changes=changes), self.assertRaises(ValueError):
                        worker.derive_with_tokenizer(dict(raw,**changes),data,plan,dispatch,tokenizer,expected_call_id=raw['call_id'])

    def test_optional_memory_missing_preserves_complete_answers_and_actual_inference_failure_still_fails(self):
        with fixture() as (data,plan,dispatch,tokenizer):
            runtime = Runtime(tokenizer, missing_memory=True)
            result = self.execute(data,plan,dispatch,runtime)
            self.assertEqual(result['stage'],'completed'); self.assertFalse(result['raw_pending'])
            self.assertEqual(runtime.subset_sizes,[32]*6+[8]); self.assertEqual(len(runtime.raw),7)
            self.assertEqual(len(runtime.raw[0]['generation_token_ids']),32)
            self.assertIsNone(runtime.raw[0]['cuda_memory'])
            self.assertEqual(runtime.raw[0]['cuda_memory_error'],'InventedTelemetryError')
            self.assertEqual(result['metrics']['baseline']['count'],200)
            self.assertEqual(result['metrics']['baseline']['numeric_correct'],200)
            self.assertEqual(result['cuda_memory']['measured_generation_batches'],0)
            self.assertIsNone(result['cuda_memory']['peak_allocated_bytes'])
        with fixture() as (data,plan,dispatch,tokenizer):
            runtime = Runtime(tokenizer,generation_failure=True,missing_memory=True)
            result = self.execute(data,plan,dispatch,runtime)
            self.assertEqual(result['stage'],'failed'); self.assertEqual(result['retained_evaluation_count'],32)
            self.assertEqual(len(result['raw_batches']),1); self.assertIsNone(result['metrics'])
            self.assertEqual(result['cuda_memory']['measured_generation_batches'],0)
            self.assertIsNone(result['cuda_memory']['peak_allocated_bytes'])

    def test_cuda_memory_counter_geometry_and_types_are_strict(self):
        good = memory(2,50)
        self.assertEqual(worker.validate_cuda_memory(good,[50,40],generation_failed=False),good)
        self.assertIsNone(worker.validate_cuda_memory(None,[1537],generation_failed=False))
        for changes in ({'generation_count':1},{'padded_input_tokens':49},{'peak_allocated_bytes':0},
                {'peak_reserved_bytes':1},{'device_total_memory_bytes':1},{'peak_allocated_bytes':True}, {'scope':'invented'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                worker.validate_cuda_memory(dict(good,**changes),[50,40],generation_failed=False)
        self.assertIsNone(worker.validate_cuda_memory(None,[50],generation_failed=False))

    def test_2048_ceiling_first_eos_and_padded_tail_are_exact(self):
        with fixture() as (data,plan,dispatch,_):
            questions = data['development'][:32]
            tokens = [[77,100257,100257] for _ in questions]
            tokens[0] = [77]*2048
            tokens[1] = [77]*2047+[100257]
            tokens[2] = [77]*1023+[100257]+[100257]*1024
            tokens[3] = [100257]*2048
            raw = {'schema_version':1,'version':worker.VERSION,'run_id':plan['run_id'],
                'protocol_hash':plan['protocol_hash'],'input_sha256':dispatch['input_sha256'],
                'intent_sha256':dispatch['intent_sha256'],'call_id':'fc-INVENTED-eos2048','arm':'baseline',
                'start':0,'stop':32,'question_ids':[row['id'] for row in questions], 'input_tokens':[30]*32,
                'generation_ids':[row['id'] for row in questions],'generation_token_ids':tokens,
                'eos_ids':[100257],'generation_seconds':2.,'generation_failed':False,'error_type':None,
                'cuda_memory':None,'cuda_memory_error':'InventedTelemetryError'}
            batch = worker.derive_batch(raw,data,plan,dispatch,lambda ids:'visible' if 77 in ids else '')
            self.assertTrue(batch['rows'][0]['truncated']); self.assertEqual(batch['rows'][0]['generated_tokens'],2048)
            self.assertFalse(batch['rows'][1]['truncated']); self.assertEqual(batch['rows'][1]['generated_tokens'],2048)
            self.assertFalse(batch['rows'][2]['truncated']); self.assertEqual(batch['rows'][2]['generated_tokens'],1024)
            self.assertFalse(batch['rows'][3]['truncated']); self.assertEqual(batch['rows'][3]['generated_tokens'],1)
            self.assertEqual(batch['rows'][3]['response'],'')
            changed = deepcopy(raw); changed['generation_token_ids'][0].append(77)
            with self.assertRaises(ValueError): worker.derive_batch(changed,data,plan,dispatch,lambda ids:'visible')

    def test_resources_official_config_and_source_closure_stay_bounded(self):
        self.assertEqual(worker.OFFICIAL_RAW_CONFIG_BYTES,905)
        self.assertEqual(worker.OFFICIAL_RAW_CONFIG_SHA,'e4f44b9c6924a283f1d1d36057a89f1a04404bf1561fc2c0b64cf98180e72915')
        self.assertEqual(worker.RESOURCES,{'gpu':'A100-80GB','cpu':(4,4),'memory':(32768,32768),
            'timeout':1800,'startup_timeout':120,'retries':0,'max_containers':1,'min_containers':0,
            'buffer_containers':0,'scaledown_window':2})
        with fixture() as (_,_,dispatch,_):
            proof = worker.verify_sources(dispatch['source_sha256'])
            self.assertTrue(proof['packaged_source_hashes_verified'])
            altered = dict(dispatch['source_sha256']); altered.pop('native_reasoning_contract.py')
            with self.assertRaises(ValueError): worker.verify_sources(altered)

    def test_actual_runtime_measures_cuda_but_counter_reset_or_read_failure_is_optional(self):
        for failure in (None, 'reset', 'read'):
            events = []
            class Inputs(dict):
                def to(self, device): return self
            class GeneratedRow:
                def __getitem__(self, span):
                    self_outer.assertEqual(span.start, 9)
                    return SimpleNamespace(tolist=lambda:[77,100257])
            self_outer = self
            inputs = Inputs(input_ids=SimpleNamespace(shape=(2,9)), attention_mask='invented')
            def reset():
                events.append('reset')
                if failure == 'reset': raise RuntimeError('Invented optional stats reset failure')
            def allocated():
                events.append('read')
                if failure == 'read': raise RuntimeError('Invented optional stats read failure')
                return 10_000_000_000
            cuda = SimpleNamespace(synchronize=lambda:events.append('sync'),reset_peak_memory_stats=reset,
                max_memory_allocated=allocated,max_memory_reserved=lambda:12_000_000_000,
                current_device=lambda:0,get_device_properties=lambda device:SimpleNamespace(total_memory=80*1024**3))
            torch = SimpleNamespace(cuda=cuda,no_grad=lambda:nullcontext())
            runtime = object.__new__(worker.Runtime)
            runtime.tokenizer = Mock(return_value=inputs); runtime.render = lambda row:'invented prompt'
            runtime.model = Mock()
            def generate(**kwargs):
                events.append('generate')
                self.assertEqual(kwargs['max_new_tokens'],2048); self.assertFalse(kwargs['do_sample'])
                return [GeneratedRow(),GeneratedRow()]
            runtime.model.generate.side_effect = generate
            with patch.dict(sys.modules,torch=torch), patch.object(worker,'record_caught_error') as diagnostic:
                tokens, seconds = runtime.generate([{'id':'invented1'},{'id':'invented2'}])
            self.assertEqual(tokens,[[77,100257],[77,100257]])
            self.assertGreaterEqual(seconds,0); self.assertEqual(events.count('generate'),1)
            if failure is None:
                self.assertEqual(runtime.generation_memory()['peak_allocated_bytes'],10_000_000_000)
                self.assertEqual(runtime.generation_memory()['generation_count'],2)
                self.assertIsNone(runtime.generation_memory_diagnostic()); diagnostic.assert_not_called()
            else:
                self.assertIsNone(runtime.generation_memory())
                self.assertEqual(runtime.generation_memory_diagnostic(),'RuntimeError')
                diagnostic.assert_called_once()
                if failure == 'reset': self.assertNotIn('read',events)


if __name__=='__main__': unittest.main()
