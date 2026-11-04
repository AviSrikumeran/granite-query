"""Synthetic only: no model, provider, canonical dataset or CUDA reads."""
from contextlib import contextmanager
from copy import deepcopy
from enum import Enum
import hashlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from cloud import modal_native_reasoning as worker
from cloud import native_reasoning_contract as contract


class Tokenizer:
    eos_token = '<|im_end|>'
    eos_token_id = 100257

    def apply_chat_template(self, messages, **kwargs):
        if kwargs.get('enable_thinking') is not True:
            raise AssertionError('Fixture requires shared OPEN thinking mode')
        return 'USER\n'+messages[0]['content']+contract.OPEN_TAIL

    def encode(self, text, **kwargs):
        return [ord(c)+10 for c in text]

    def decode(self, ids, **kwargs):
        return ''.join(self.eos_token if i == self.eos_token_id else chr(i-10) for i in ids)


def bind(data, plan):
    plan['input_sha256'] = contract.digest(data)
    plan['protocol_hash'] = contract.digest({k: v for k, v in plan.items() if k != 'protocol_hash'})
    dispatch = {'version': 'native-reasoning-dispatch-v1', 'claim_id': 'a'*32,
        'run_id': plan['run_id'], 'plan_sha256': contract.digest(plan),
        'input_sha256': contract.digest(data), 'funding_review_sha256': 'b'*64,
        'source_sha256': {name: hashlib.sha256((worker.ROOT/name).read_bytes()).hexdigest()
            for name in worker.REQUIRED_SOURCES}}
    dispatch['intent_sha256'] = contract.digest(dispatch)
    return dispatch


@contextmanager
def fixture(arm='baseline', *, lengths=None):
    """Patch only canonical development fingerprints to invented200 questions."""
    dev = [{'id': f'gsm8k:train:{5000+i:05d}', 'prompt': f'INVENTED held out arithmetic {i}',
        'gold_answer': '7', 'source_split': 'train'} for i in range(200)]
    with patch.multiple(contract, DEVELOPMENT_IDS_SHA256=contract.digest([r['id'] for r in dev]),
            DEVELOPMENT_PROJECTION_SHA256=contract.digest(dev)):
        data = {'development': dev, 'arm': None, 'bindings': {
            'collection_plan_sha256': '1'*64, 'eligible_pairs_sha256': '2'*64,
            'teacher_receipt_inventory_sha256': '3'*64}}
        tokenizer = Tokenizer()
        if arm != 'baseline':
            training = []
            for i, length in enumerate(lengths or [1536, 512]*8):
                reasoning = 'Arithmetic evidence.' if arm == 'thinking' else ''
                overhead = len((reasoning+'\n' if reasoning else '')+'</think>\n')+1
                content = 'x'*(length-overhead-len('#### 7'))+'#### 7'
                row = {'id': f'gsm8k:train:{i:05d}', 'prompt': f'INVENTED teaching {i}',
                    'gold_answer': '7', 'source_split': 'train', 'finish_reason': 'stop',
                    'truncated': False, 'verified_final_answer': True}
                training.append(contract.encode_target(row, arm, reasoning, content, tokenizer))
            training = contract.select_whole_targets(training)
            data['arm'] = {'arm': arm, 'token_budget': 16384, 'tokens_per_update': 1024,
                'optimizer_updates': 16, 'tokenizer': dict(contract.TOKENIZER),
                'training': training, 'updates': contract.exposure_windows(training)}
        plan = dict(contract.protocol(), run_id='INVENTED_native_'+arm, arm=arm,
            mode='evaluate_base' if arm == 'baseline' else 'train_evaluate',
            token_budget=0 if arm == 'baseline' else 16384,
            optimizer_updates=0 if arm == 'baseline' else 16,
            bindings_sha256=contract.digest(data['bindings']))
        dispatch = bind(data, plan)
        yield data, plan, dispatch, tokenizer


class FakeRuntime:
    def __init__(self, tokenizer, *, source_failure=False, raw_failure=False,
            decode_failure=False, generation_failure=False, first_long=False,
            stop_after_batches=None, train_guard_after_windows=None):
        self.tokenizer = tokenizer; self.call_id = 'fc-INVENTED-native'
        self.events = []; self.clock = 0.; self.sources = source_failure
        self.raw_failure = raw_failure; self.decode_failure = decode_failure
        self.generation_failure = generation_failure; self.first_long = first_long
        self.stop_after_batches = stop_after_batches; self.train_guard_after_windows = train_guard_after_windows
        self.raw = {}; self.batches = {}; self.windows = []; self.steps = 0; self.saves = []
        self.source_proof = {'fixture_only': True}; self.generations = 0

    def elapsed(self): return self.clock
    def begin(self, data, plan, dispatch): self.plan = plan; self.events.append('begin')
    def status(self, stage, **details): self.events.append(stage)
    def verify_sources(self, dispatch):
        if self.sources: raise ValueError('INVENTED source mismatch')
    def load_tokenizer(self, plan): self.events.append('tokenizer_loaded'); return self.tokenizer
    def record_tokenizer(self, identity): self.events.append('tokenizer_verified')
    def load_model(self, plan): self.events.append('model_loaded'); self.clock += 2
    def begin_update(self): self.events.append('zero_grad')
    def backward_window(self, row, window):
        labels = contract.window_labels(row, window)
        assert sum(i != -100 for i in labels) == window['supervised_tokens']
        assert labels[:row['prefix_tokens']] == [-100]*row['prefix_tokens']
        self.windows.append((row['id'], deepcopy(window)))
        if self.train_guard_after_windows is not None and len(self.windows) >= self.train_guard_after_windows:
            self.clock = 1401
        return 1. if int(row['id'].split(':')[-1]) % 2 else 3.
    def step_update(self): self.steps += 1
    def save_training(self, completed, history, **kwargs):
        self.saves.append((completed, deepcopy(kwargs)))
        return {'updates': completed, 'supervised_tokens': completed*1024,
            'physical_observation': {'fixture_only': True}, 'adapter_files_sha256': {}}
    def prepare_evaluation(self, checkpoint):
        self.events.append('reload_verified'); return {'fixture_only': True}
    def input_counts(self, rows):
        return [1537 if self.first_long and r['id'].endswith('05000') else 30 for r in rows]
    def generate(self, rows):
        self.events.append('generate'); self.generations += 1; self.clock += 1
        if self.generation_failure: raise RuntimeError('INVENTED generation failure')
        return [[77, 100257, 100257] for _ in rows], 1.
    def write_raw(self, start, raw):
        self.events.append('raw_durable'); self.raw[start] = deepcopy(raw)
        if self.raw_failure: raise OSError('INVENTED uncertain local raw commit')
        return hashlib.sha256(worker.encoded(raw)).hexdigest()
    def decode(self, ids):
        assert 'raw_durable' in self.events
        if self.decode_failure: raise ValueError('INVENTED decode failure')
        self.events.append('decode'); return '#### 7'
    def write_batch(self, start, batch):
        self.events.append('derived_durable'); self.batches[start] = deepcopy(batch)
        if self.stop_after_batches is not None and len(self.batches) >= self.stop_after_batches:
            self.clock = 1601
    def finish(self, result): self.result = result


class NativeWorkerTests(unittest.TestCase):
    def run_fixture(self, data, plan, dispatch, runtime):
        with patch.object(contract, 'tokenizer_identity', return_value=dict(contract.TOKENIZER)):
            return worker.run_native(data, plan, dispatch, runtime=runtime)

    def test_resources_hard_bounds_and_no_retry(self):
        self.assertEqual(worker.RESOURCES, {'gpu': 'A100-80GB', 'cpu': (4, 4),
            'memory': (32768, 32768), 'timeout': 1800, 'startup_timeout': 120,
            'retries': 0, 'max_containers': 1, 'min_containers': 0,
            'buffer_containers': 0, 'scaledown_window': 2})

    def test_dispatch_rejects_tampered_plan_input_source_or_funding(self):
        with fixture() as (data, plan, dispatch, _):
            worker.validate_dispatch(data, plan, dispatch)
            for field, value in [('plan_sha256', '0'*64), ('input_sha256', '0'*64),
                    ('funding_review_sha256', 'not-a-hash')]:
                changed = deepcopy(dispatch); changed[field] = value
                changed['intent_sha256'] = contract.digest({k: v for k, v in changed.items() if k != 'intent_sha256'})
                with self.assertRaises(ValueError): worker.validate_dispatch(data, plan, changed)
            changed = deepcopy(dispatch); changed['source_sha256']['../escape.py'] = '0'*64
            changed['intent_sha256'] = contract.digest({k: v for k, v in changed.items() if k != 'intent_sha256'})
            with self.assertRaises(ValueError): worker.validate_dispatch(data, plan, changed)

    def test_real_packaged_source_bytes_verified_and_tampering_rejected(self):
        with fixture() as (_, _, dispatch, _):
            proof = worker.verify_sources(dispatch['source_sha256'])
            self.assertTrue(proof['packaged_source_hashes_verified'])
            changed = dict(dispatch['source_sha256']); changed['modal_native_reasoning.py'] = '0'*64
            with self.assertRaises(ValueError): worker.verify_sources(changed)

    def test_source_failure_before_tokenizer_or_model(self):
        with fixture() as (data, plan, dispatch, tokenizer):
            runtime = FakeRuntime(tokenizer, source_failure=True)
            result = self.run_fixture(data, plan, dispatch, runtime)
            self.assertEqual(result['stage'], 'failed'); self.assertIsNone(result['metrics'])
            self.assertNotIn('tokenizer_loaded', runtime.events); self.assertNotIn('model_loaded', runtime.events)

    def test_reencoding_rejects_coherently_rehashed_wrong_prefix_before_model(self):
        with fixture('thinking') as (data, plan, dispatch, tokenizer):
            row = data['arm']['training'][0]; row['input_ids'][0] += 1
            row['prefix_ids_sha256'] = contract.digest(row['input_ids'][:row['prefix_tokens']])
            dispatch = bind(data, plan)
            runtime = FakeRuntime(tokenizer)
            result = self.run_fixture(data, plan, dispatch, runtime)
            self.assertEqual(result['stage'], 'failed'); self.assertNotIn('model_loaded', runtime.events)

    def test_complete_training_exact_windows_steps_full_evaluation_and_no_padding(self):
        with fixture('thinking') as (data, plan, dispatch, tokenizer):
            runtime = FakeRuntime(tokenizer, first_long=True)
            result = self.run_fixture(data, plan, dispatch, runtime)
            self.assertEqual((result['supervised_tokens'], result['optimizer_updates'], runtime.steps), (16384, 16, 16))
            self.assertEqual(sum(w['supervised_tokens'] for _, w in runtime.windows), 16384)
            self.assertEqual(result['weighted_losses'], [sum((1. if int(w['id'].split(':')[-1]) % 2 else 3.)*w['loss_weight']
                for w in u['microbatches']) for u in data['arm']['updates']])
            rows = result['evaluations']['thinking']
            self.assertEqual(len(rows), 200); self.assertTrue(result['evaluation_complete'])
            self.assertEqual(result['metrics']['thinking']['count'], 200)
            self.assertEqual(result['metrics']['thinking']['numeric_correct'], 199)
            self.assertEqual(rows[0]['outcome'], 'input_limit'); self.assertEqual(rows[0]['generated_tokens'], 0)
            self.assertEqual(len(result['raw_batches']), 25); self.assertEqual(rows[-1]['id'], data['development'][-1]['id'])
            self.assertFalse(result['worker_terminal']['confirmed_terminal'])
            self.assertEqual([n for n, _ in runtime.saves], [4, 8, 12, 16])
            self.assertTrue(runtime.saves[-1][1]['final'])

    def test_actual_loss_backward_is_scaled_by_supervised_tokens(self):
        with fixture('concise') as (data, _, _, _):
            row = data['arm']['training'][0]
            window = dict(data['arm']['updates'][0]['microbatches'][0])
            seen = []
            class Loss:
                def __mul__(self, weight):
                    self.weight = weight; return self
                def backward(self): seen.append(self.weight)
                def detach(self): return 3.
            loss = Loss()
            fake_torch = SimpleNamespace(tensor=lambda x, **kw: x, isfinite=lambda x: True)
            runtime = object.__new__(worker.Runtime)
            runtime.model = Mock(return_value=SimpleNamespace(loss=loss))
            with patch.dict(sys.modules, torch=fake_torch):
                result = runtime.backward_window(row, window)
            self.assertEqual(result, 3.); self.assertEqual(seen, [window['supervised_tokens']/1024])
            labels = runtime.model.call_args.kwargs['labels'][0]
            self.assertEqual(sum(i != -100 for i in labels), window['supervised_tokens'])

    def test_training_guard_discards_unstepped_window_and_preserves_checkpoint(self):
        with fixture('concise', lengths=[512]*32) as (data, plan, dispatch, tokenizer):
            runtime = FakeRuntime(tokenizer, train_guard_after_windows=1)
            result = self.run_fixture(data, plan, dispatch, runtime)
            self.assertEqual(result['stage'], 'timed_out'); self.assertEqual(runtime.steps, 0)
            self.assertEqual(result['supervised_tokens'], 0); self.assertTrue(result['incomplete_update_discarded'])
            self.assertEqual(runtime.generations, 0); self.assertIsNone(result['metrics'])

    def test_evaluation_guard_retains_prefix_without_full_denominator_metric(self):
        with fixture() as (data, plan, dispatch, tokenizer):
            runtime = FakeRuntime(tokenizer, stop_after_batches=1)
            result = self.run_fixture(data, plan, dispatch, runtime)
            self.assertEqual(result['stage'], 'timed_out'); self.assertEqual(result['retained_evaluation_count'], 8)
            self.assertFalse(result['evaluation_complete']); self.assertIsNone(result['metrics'])
            self.assertEqual(runtime.generations, 1)

    def test_generation_failure_retains_attempted_subset_only_then_stops(self):
        with fixture() as (data, plan, dispatch, tokenizer):
            runtime = FakeRuntime(tokenizer, generation_failure=True, first_long=True)
            result = self.run_fixture(data, plan, dispatch, runtime)
            self.assertEqual(result['stage'], 'failed'); self.assertEqual(runtime.generations, 1)
            self.assertEqual(result['outcomes'], {'input_limit': 1, 'failed': 7})
            self.assertEqual(result['retained_evaluation_count'], 8); self.assertIsNone(result['metrics'])

    def test_raw_or_decode_failure_never_causes_second_generation(self):
        with fixture() as (data, plan, dispatch, tokenizer):
            for options in ({'raw_failure': True}, {'decode_failure': True}):
                runtime = FakeRuntime(tokenizer, **options)
                result = self.run_fixture(data, plan, dispatch, runtime)
                self.assertTrue(result['raw_pending']); self.assertEqual(runtime.generations, 1)
                self.assertEqual(result['retained_evaluation_count'], 0)
                raw = result['raw_pending_record']
                derived = worker.derive_batch(raw, data, plan, dispatch, lambda ids: '#### 7')
                self.assertEqual(len(derived['rows']), 8); self.assertEqual(runtime.generations, 1)
                if options.get('decode_failure'):
                    self.assertEqual(len(result['raw_batches']), 1)

    def test_raw_reordering_conflict_or_out_of_bound_tokens_rejected(self):
        with fixture() as (data, plan, dispatch, tokenizer):
            runtime = FakeRuntime(tokenizer, stop_after_batches=1)
            self.run_fixture(data, plan, dispatch, runtime); raw = runtime.raw[0]
            for mutate in (lambda r: r['question_ids'].reverse(),
                    lambda r: r['generation_token_ids'][0].append(100352),
                    lambda r: r.update(arm='thinking')):
                changed = deepcopy(raw); mutate(changed)
                with self.assertRaises(ValueError): worker.derive_batch(changed, data, plan, dispatch, lambda ids: '#### 7')

    def test_full_local_replay_checks_real_prompt_counts_and_provider_call(self):
        with fixture() as (data, plan, dispatch, tokenizer):
            runtime = FakeRuntime(tokenizer, stop_after_batches=1)
            self.run_fixture(data, plan, dispatch, runtime); raw = deepcopy(runtime.raw[0])
            raw['input_tokens'] = [len(tokenizer.encode(worker.render_prompt(tokenizer, row)))
                for row in data['development'][:8]]
            with patch.object(contract, 'tokenizer_identity', return_value=dict(contract.TOKENIZER)):
                result = worker.derive_with_tokenizer(raw, data, plan, dispatch, tokenizer,
                    expected_call_id=runtime.call_id)
                self.assertEqual(len(result['rows']), 8)
                with self.assertRaises(ValueError): worker.derive_with_tokenizer(raw, data, plan,
                    dispatch, tokenizer, expected_call_id='fc-INVENTED-other')
                raw['input_tokens'][0] += 1
                with self.assertRaises(ValueError): worker.derive_with_tokenizer(raw, data, plan,
                    dispatch, tokenizer, expected_call_id=runtime.call_id)

    def test_duplicate_owner_or_existing_artifacts_block_execution(self):
        parent = worker.ROOT/'runs/local_check_tmp'; parent.mkdir(parents=True, exist_ok=True)
        with fixture() as (data, plan, dispatch, _), tempfile.TemporaryDirectory(dir=parent) as temporary:
            runtime = object.__new__(worker.Runtime); runtime.root = Path(temporary); runtime.call_id = 'fc-INVENTED-owner'
            with patch.object(worker.state, 'put', return_value=False):
                with self.assertRaises(ValueError): runtime.begin(data, plan, dispatch)
            self.assertFalse((runtime.root/plan['run_id']).exists())
            (runtime.root/plan['run_id']).mkdir()
            with patch.object(worker.state, 'put') as put:
                with self.assertRaises(ValueError): runtime.begin(data, plan, dispatch)
                put.assert_not_called()

    def test_runtime_enum_metadata_normalized_without_weakening_layout(self):
        class Kind(str, Enum): LORA = 'LORA'
        value = {'base_model_name_or_path': contract.MODEL, 'peft_type': Kind.LORA,
            'r': 8, 'lora_alpha': 16, 'lora_dropout': 0., 'bias': 'none',
            'task_type': 'CAUSAL_LM', 'target_modules': {'q_proj', 'v_proj'}}
        normalized = worker.runtime_adapter_config(value)
        self.assertIs(type(normalized['peft_type']), str)
        normalized['r'] = 16
        with self.assertRaises(ValueError): worker.runtime_adapter_config(normalized)


if __name__ == '__main__': unittest.main()
