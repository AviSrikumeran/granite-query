"""CUDA/provider boundary is entirely mocked; temporary files are synthetic."""
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cloud import modal_final_scale as worker
from cloud import final_scale_execution as execute
from cloud import final_scale_receipts as receipts
from cloud.test_final_scale_execution import fixture


class FakeRuntime:
    def __init__(self, payload, *, asset_failure=False, model_failure=False, generation_failure=False,
            raw_failure=False, clock=0, first_long=False):
        self.payload = payload; self.call_id = 'fc-fake-worker'; self.events = []; self.raw = {}; self.batches = {}
        self.eos = [100257]; self.asset_failure = asset_failure; self.model_failure = model_failure
        self.generation_failure = generation_failure; self.raw_failure = raw_failure; self.clock = clock
        self.first_long = first_long; self.generations = 0
    def elapsed(self): return self.clock
    def begin(self, *args): self.events.append('begin')
    def status(self, stage, **kwargs): self.events.append(stage)
    def verify_assets(self, auth):
        self.events.append('sources_adapter_verified')
        if self.asset_failure: raise ValueError('INVENTED source mismatch')
    def load_model(self, auth, checkpoint, seed):
        self.events.append('peft_verified')
        if self.model_failure: raise ValueError('INVENTED model mismatch')
    def read_input(self, descriptor):
        assert self.events.index('sources_adapter_verified') < self.events.index('peft_verified')
        self.events.append('input_read'); return self.payload
    def input_counts(self, rows): return [1537 if self.first_long and row == self.payload['rows'][0] else 10 for row in rows]
    def generate(self, rows):
        self.events.append('generate'); self.generations += 1; self.clock += .5
        if self.generation_failure: raise RuntimeError('INVENTED CUDA failure')
        return [[77, 100257] for _ in rows], .5
    def write_raw(self, start, value):
        self.events.append('raw_durable'); self.raw[start] = value
        if self.raw_failure: raise OSError('INVENTED raw write failure')
        return __import__('hashlib').sha256(execute.payload_bytes(value)).hexdigest()
    def decode(self, ids):
        assert 'raw_durable' in self.events
        self.events.append('decode'); return '#### 7'
    def write_batch(self, start, value): self.events.append('derived_durable'); self.batches[start] = value
    def finish(self, result): self.result = result


class ModalFinalTests(unittest.TestCase):
    def test_source_adapter_and_peft_failure_happen_before_input_reads(self):
        auth, payload, desc, intent = fixture()
        for options in ({'asset_failure': True}, {'model_failure': True}):
            runtime = FakeRuntime(payload, **options)
            result = worker.run_shard(intent, desc, auth, runtime=runtime)
            self.assertNotIn('input_read', runtime.events); self.assertEqual(runtime.generations, 0)
            self.assertTrue(result['pre_input_failure']); self.assertIsNone(result['worker_terminal'])

    def test_complete_tail7_no_padding_and_raw_durable_before_decoder(self):
        auth, payload, desc, intent = fixture(1319, checkpoint='chosen', shard_id='shard003')
        runtime = FakeRuntime(payload, first_long=True)
        result = worker.run_shard(intent, desc, auth, runtime=runtime)
        self.assertEqual(result['stage'], 'completed'); self.assertFalse(result['worker_terminal']['confirmed_terminal'])
        self.assertEqual(result['launch'], execute.launch_receipt(intent, runtime.call_id))
        last = result['batches'][-1]
        self.assertEqual(last['count'], 7); self.assertEqual(len({r['id'] for r in last['rows']}), 7)
        rows = [r for batch in result['batches'] for r in batch['rows']]
        self.assertEqual(len(rows), 215); self.assertEqual(rows[0]['outcome'], 'input_limit')
        self.assertEqual(runtime.events.count('raw_durable'), runtime.events.count('derived_durable'))
        terminal = execute.terminal_receipt(intent, result['launch'], result['batches'], [], 'completed', confirmed_terminal=True)
        receipts.recover_prefix(auth['sealed']['contract'], payload['binding'], 'chosen', 'shard003',
            [{'launch': result['launch'], 'terminal': terminal, 'batches': result['batches']}])

    def test_generation_failure_retains_attempted_subset_then_stops_without_inventing_remaining(self):
        auth, payload, desc, intent = fixture()
        runtime = FakeRuntime(payload, generation_failure=True, first_long=True)
        result = worker.run_shard(intent, desc, auth, runtime=runtime)
        self.assertEqual(result['stage'], 'failed'); self.assertEqual(runtime.generations, 1)
        self.assertEqual(result['worker_terminal']['retained_count'], 8)
        rows = result['batches'][0]['rows']
        self.assertEqual(rows[0]['outcome'], 'input_limit'); self.assertEqual(sum(r['outcome'] == 'failed' for r in rows), 7)
        self.assertEqual(len(result['batches']), 1); self.assertFalse(result['raw_pending'])

    def test_runtime_guard_preserves_missing_prefix_without_fake_failed_outcomes(self):
        auth, payload, desc, intent = fixture()
        runtime = FakeRuntime(payload, clock=1601)
        result = worker.run_shard(intent, desc, auth, runtime=runtime)
        self.assertEqual(result['stage'], 'timed_out'); self.assertEqual(runtime.generations, 0)
        self.assertEqual(result['batches'], []); self.assertEqual(result['worker_terminal']['retained_count'], 0)

    def test_pending_raw_is_preserved_and_can_be_derived_without_another_generation(self):
        auth, payload, desc, intent = fixture()
        runtime = FakeRuntime(payload, raw_failure=True)
        result = worker.run_shard(intent, desc, auth, runtime=runtime)
        self.assertTrue(result['raw_pending']); self.assertTrue(result['worker_terminal']['raw_pending'])
        self.assertEqual(result['batches'], []); self.assertEqual(runtime.generations, 1)
        derived = execute.derive_raw_batch(intent, result['launch'], result['raw_pending_record'], payload['binding'], lambda _: '#### 7')
        self.assertEqual(len(derived['rows']), 8); self.assertEqual(runtime.generations, 1)

    def test_dispatch_requires_fresh_matching_claim_and_funded_spawning_child(self):
        auth, _, desc, intent = fixture(); claim = execute.dispatch_claim(intent, 'a'*32)
        started = {'stage': 'dispatch_started', 'run_id': intent['run_id'], 'intent_sha256': intent['intent_sha256'], 'claim_sha256': claim['claim_sha256']}
        job = dict(run_id=intent['run_id'], service='modal', status='spawning', reserved_usd=1.75,
            **{key: intent[key] for key in ('intent_sha256', 'freeze_sha256', 'seal_sha256', 'bundle_id')}, claim_sha256=claim['claim_sha256'])
        ledger = {'limits': {'modal': 30, 'deepseek': 20}, 'jobs': [job]}
        with patch('cloud.comparison_control.require_fresh_modal_budget') as freshness:
            self.assertTrue(worker.validate_dispatch(intent, desc, auth, claim, started, ledger, launch_lock_present=True))
            freshness.assert_called_once_with(ledger)
            with self.assertRaises(ValueError): worker.validate_dispatch(intent, desc, auth, claim, started, ledger, launch_lock_present=False)
            job['status'] = 'completed'
            with self.assertRaises(ValueError): worker.validate_dispatch(intent, desc, auth, claim, started, ledger, launch_lock_present=True)

    def test_cli_ambiguous_spawn_marker_blocks_a_second_transmission(self):
        auth, _, desc, intent = fixture(); claim = execute.dispatch_claim(intent, 'a'*32)
        parent = worker.ROOT/'runs/local_check_tmp'; parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as temporary:
            folder = Path(temporary)/intent['run_id']; folder.mkdir(); calls = []
            def ambiguous(*args): calls.append(1); raise TimeoutError('INVENTED lost acknowledgement')
            with self.assertRaises(TimeoutError): worker._spawn_once(folder, intent, desc, auth, claim, spawn=ambiguous)
            self.assertTrue((folder/'cli_spawn_started.json').exists()); self.assertFalse((folder/'launch.json').exists())
            with self.assertRaises(ValueError): worker._spawn_once(folder, intent, desc, auth, claim, spawn=ambiguous)
            self.assertEqual(len(calls), 1)

    def test_cli_saves_exact_shared_launch_after_one_mocked_transmission(self):
        auth, _, desc, intent = fixture(); claim = execute.dispatch_claim(intent, 'b'*32)
        parent = worker.ROOT/'runs/local_check_tmp'; parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as temporary:
            folder = Path(temporary)/intent['run_id']; folder.mkdir(); calls = []
            def spawned(*args): calls.append(args); return SimpleNamespace(object_id='fc-provider-returned')
            result = worker._spawn_once(folder, intent, desc, auth, claim, spawn=spawned)
            self.assertEqual(result, execute.launch_receipt(intent, 'fc-provider-returned'))
            self.assertEqual(__import__('json').loads((folder/'launch.json').read_text(encoding='utf-8')), result)
            with self.assertRaises(ValueError): worker._spawn_once(folder, intent, desc, auth, claim, spawn=spawned)
            self.assertEqual(len(calls), 1)


if __name__ == '__main__': unittest.main()
