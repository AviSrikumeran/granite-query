"""Offline controller escrow, identity and fixed-denominator fixtures.

All data, accounting observations, claims and results are synthetic. Temporary
files live below ignored cloud/runs; no real ledger, dataset or provider changes.
"""
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cloud import native_reasoning_control as control
from cloud import native_reasoning_collection as collection
from cloud import budget_reconcile as budget
from cloud import modal_native_reasoning as worker
from cloud import test_modal_native_reasoning as worker_fixtures


class Backend:
    """Pure invented provider boundary; launch only writes a local fixture ack."""
    def __init__(self, *, acknowledge=False):
        self.acknowledge = acknowledge; self.launches = 0; self.owner = None
        self.answer = {'kind': 'running'}; self.files = {}; self.downloads = []

    def apps(self): return []
    def launch(self, folder):
        self.launches += 1
        if self.acknowledge:
            dispatch = control.read(folder / 'dispatch.json')
            control.write(folder / 'launch.json', dict(run_id=dispatch['run_id'],
                claim_id=dispatch['claim_id'], intent_sha256=dispatch['intent_sha256'],
                call_id='fc-INVENTED-controller'), immutable=True)
        return {'return_code': 0, 'app_id': 'ap-INVENTED'}
    def lookup(self, run_id): return deepcopy(self.owner)
    def poll(self, call_id): return deepcopy(self.answer)
    def download(self, run_id, relative):
        self.downloads.append((run_id, relative))
        return self.files[relative]


class NativeControllerTests(unittest.TestCase):
    def setUp(self):
        parent = control.PRIVATE / 'local_check_tmp'
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state, self.output, self.collection = (self.root / name for name in ('state', 'study', 'collection'))
        self.state.mkdir(); self.collection.mkdir()
        self.sources = {name: 'a' * 64 for name in worker.REQUIRED_SOURCES}
        self.sources['native_reasoning_control.py'] = 'b' * 64
        self.dev = [{'id': f'gsm8k:train:{index + 10000:05d}', 'prompt': f'Invented development {index}',
                     'gold_answer': '7', 'source_split': 'train'} for index in range(200)]
        self.devpath = self.root / 'synthetic_development.json'
        control.write(self.devpath, self.dev)
        control.write(self.collection / 'plan.json', {'fixture': True})
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(control, 'STATE', self.state))
        self.stack.enter_context(patch.object(control, 'DEV', self.devpath))
        self.stack.enter_context(patch.multiple(control.contract,
            DEVELOPMENT_SOURCE_SHA256=control.sha(self.devpath),
            DEVELOPMENT_PROJECTION_SHA256=control.digest(self.dev),
            DEVELOPMENT_IDS_SHA256=control.digest([row['id'] for row in self.dev])))
        self.stack.enter_context(patch.object(control, 'development', side_effect=lambda: deepcopy(self.dev)))
        self.stack.enter_context(patch.object(control, 'source_inventory', side_effect=lambda: dict(self.sources)))
        self.stack.enter_context(patch.object(collection, 'validate_run', return_value=({'fixture': True}, [], [])))
        control.prepare_design(self.collection, self.output)
        self.write_review()

    def write_review(self, phase='study'):
        value = {'reviewed': True, 'phase': phase,
            'design_sha256': control.sha(self.output / 'design.json'),
            'source_sha256': dict(self.sources), 'protected_modal_usd': 5.0}
        control.write(self.output / f'review_{phase}.json', value)
        return value

    def ledger(self, *, observed=9, jobs=None, age_seconds=0):
        now = datetime.now(timezone.utc)
        original = {'limits': {'modal': 30, 'deepseek': 20},
            'estimated_spend': {'modal': 0, 'deepseek': 0},
            'reserved': {'modal': 0, 'deepseek': 0}, 'jobs': deepcopy(jobs or [])}
        snapshot = {'queried_at_utc': (now - timedelta(seconds=age_seconds)).isoformat(),
            'start_utc': (now - timedelta(days=1)).isoformat(),
            'metered_cost': str(observed), 'billed_cost': '0',
            'source': 'Invented supported-observation fixture'}
        return budget.reconcile(original, snapshot, now=now, lag_buffer_usd=3)

    def save_ledger(self, ledger):
        control.write(self.state / 'budget.json', ledger)

    def dispatch(self, role='baseline'):
        plan = {'run_id': self.output.name + '_' + role, 'arm': role}
        data = {'fixture': 'No actual development data'}
        return plan, data, control.make_dispatch(plan, data, self.sources, 'c' * 64, 'd' * 32)

    def test_envelope_reserves_once_and_requires_exact_source_and_design_review(self):
        original = self.ledger(jobs=[{'run_id': 'unrelated_planned', 'service': 'modal',
            'status': 'reserved', 'reserved_usd': 4}])
        self.save_ledger(original)
        first = control.allocate_envelope(self.output)
        after = control.read(self.state / 'budget.json')
        self.assertEqual(first['reserved_usd'], 7)
        self.assertEqual(after['reserved']['modal'], original['reserved']['modal'] + 7)
        self.assertEqual(after['estimated_spend'], original['estimated_spend'])
        self.assertEqual(control.allocate_envelope(self.output), first)
        self.assertEqual(control.read(self.state / 'budget.json'), after)
        self.assertFalse((self.state / 'budget_reconcile.lock').exists())
        review = control.read(self.output / 'review_study.json')
        review['design_sha256'] = '0' * 64
        control.write(self.output / 'review_study.json', review)
        with self.assertRaises(ValueError):
            control.allocate_envelope(self.output)
        self.write_review()
        self.sources['native_reasoning_control.py'] = 'e' * 64
        with self.assertRaises(ValueError):
            control.verify_design(self.output)

    def test_protected_five_dollars_and_fresh_supported_accounting_fail_closed(self):
        # 15 observed + 3 collection buffer + 7 envelope leaves exactly 5.
        self.save_ledger(self.ledger(observed=15))
        control.allocate_envelope(self.output)
        saved = control.read(self.state / 'budget.json')
        self.assertEqual(30 - saved['estimated_spend']['modal'] - saved['reserved']['modal'], 5)
        # A fresh independent output is required to test a new reservation.
        for ledger in (self.ledger(observed=15.01), self.ledger(age_seconds=3600),
                self.ledger(jobs=[{'run_id': 'ambiguous_status', 'service': 'modal',
                    'status': 'unrecognized_provider_state', 'reserved_usd': 1}])):
            self.save_ledger(ledger)
            before = (self.state / 'budget.json').read_bytes()
            with self.subTest(ledger=ledger['modal_budget_accounting']), self.assertRaises((ValueError, RuntimeError)):
                control.allocate_envelope(self.output)
            self.assertEqual((self.state / 'budget.json').read_bytes(), before)
        absent = self.ledger()
        absent.pop('modal_budget_accounting'); absent.pop('modal_observation')
        self.save_ledger(absent)
        with self.assertRaises((ValueError, RuntimeError)):
            control.allocate_envelope(self.output)

    def test_child_transfer_conserves_total_liability_and_never_double_binds(self):
        self.save_ledger(self.ledger())
        control.allocate_envelope(self.output)
        ledger = control.read(self.state / 'budget.json')
        original_total = ledger['reserved']['modal']
        envelope = ledger['jobs'][0]
        plan, _, dispatch = self.dispatch()
        job = {'run_id': plan['run_id'], 'plan': plan, 'role': 'baseline'}
        control._bind_child(ledger, job, self.output, dispatch)
        self.assertEqual(ledger['reserved']['modal'], original_total)
        self.assertEqual(sum(item['reserved_usd'] for item in ledger['jobs']), original_total)
        self.assertEqual(envelope['reserved_usd'], 5.25)
        child = ledger['jobs'][-1]
        self.assertEqual(child['reserved_usd'], 1.75)
        self.assertEqual(child['native_envelope_parent'], envelope['run_id'])
        self.assertEqual(child['native_claim_id'], dispatch['claim_id'])
        self.assertEqual(child['native_intent_sha256'], dispatch['intent_sha256'])
        before = deepcopy(ledger)
        with self.assertRaises(ValueError):
            control._bind_child(ledger, job, self.output, dispatch)
        self.assertEqual(ledger, before)

    def test_child_refuses_other_active_unknown_state_and_lost_protection(self):
        self.save_ledger(self.ledger()); control.allocate_envelope(self.output)
        original = control.read(self.state / 'budget.json')
        plan, _, dispatch = self.dispatch()
        job = {'run_id': plan['run_id'], 'plan': plan, 'role': 'baseline'}
        for status in ('spawning', 'spawned', 'running', 'queued', 'unknown'):
            ledger = deepcopy(original)
            ledger['jobs'].append({'run_id': 'foreign_compute', 'service': 'modal', 'status': status, 'reserved_usd': 1})
            ledger['reserved']['modal'] += 1
            before = deepcopy(ledger)
            with self.subTest(status=status), self.assertRaises((ValueError, RuntimeError)):
                control._bind_child(ledger, job, self.output, dispatch)
            self.assertEqual(ledger, before)
        ledger = deepcopy(original); ledger['estimated_spend']['modal'] = 18.01
        before = deepcopy(ledger)
        with self.assertRaises(ValueError):
            control._bind_child(ledger, job, self.output, dispatch)
        self.assertEqual(ledger, before)

    def test_dispatch_and_immutable_claim_hashes_bind_exact_inputs(self):
        plan, data, dispatch = self.dispatch()
        self.assertEqual(dispatch['plan_sha256'], control.digest(plan))
        self.assertEqual(dispatch['input_sha256'], control.digest(data))
        self.assertEqual(dispatch['intent_sha256'], control.digest({key: value for key, value in dispatch.items() if key != 'intent_sha256'}))
        changed = control.make_dispatch(plan, {'fixture': 'altered'}, self.sources, 'c' * 64, 'd' * 32)
        self.assertNotEqual(changed['intent_sha256'], dispatch['intent_sha256'])
        claim = self.output / 'arms' / plan['run_id'] / 'dispatch_intent.json'
        control.write(claim, dispatch, immutable=True)
        original = claim.read_bytes()
        control.write(claim, dispatch, immutable=True)
        with self.assertRaises(ValueError):
            control.write(claim, changed, immutable=True)
        self.assertEqual(claim.read_bytes(), original)

    def test_dispatch_consumer_rejects_forged_claim_inputs_sources_and_intent(self):
        plan, data, _ = self.dispatch()
        sources = {name: 'a' * 64 for name in worker.REQUIRED_SOURCES}
        dispatch = control.make_dispatch(plan, data, sources, 'b' * 64, 'c' * 32)
        self.assertTrue(worker.validate_dispatch(data, plan, dispatch))
        for mutation in ('claim', 'input', 'plan', 'source_missing', 'source_path', 'review', 'intent'):
            altered = deepcopy(dispatch)
            if mutation == 'claim': altered['claim_id'] = 'c' * 31
            elif mutation == 'input': altered['input_sha256'] = 'd' * 64
            elif mutation == 'plan': altered['plan_sha256'] = 'd' * 64
            elif mutation == 'source_missing': altered['source_sha256'].pop('native_reasoning_contract.py')
            elif mutation == 'source_path': altered['source_sha256']['../outside.py'] = 'd' * 64
            elif mutation == 'review': altered['funding_review_sha256'] = 'invalid'
            elif mutation == 'intent': altered['intent_sha256'] = 'd' * 64
            # Rehash all attacks except the intent attack: reject bad semantics,
            # rather than only noticing a stale enclosing digest.
            if mutation != 'intent':
                altered['intent_sha256'] = control.digest({key: value for key, value in altered.items() if key != 'intent_sha256'})
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                worker.validate_dispatch(data, plan, altered)

    def test_four_call_escrow_capacity_includes_recovery_without_new_money(self):
        self.save_ledger(self.ledger()); control.allocate_envelope(self.output)
        ledger = control.read(self.state / 'budget.json')
        for role in ('baseline', 'concise', 'thinking', 'thinking_recovery1'):
            plan, _, dispatch = self.dispatch(role)
            control._bind_child(ledger, {'run_id': plan['run_id'], 'plan': plan, 'role': role}, self.output, dispatch)
            self.assertEqual(ledger['reserved']['modal'], 7)
            self.assertEqual(sum(item['reserved_usd'] for item in ledger['jobs']), 7)
            # Simulated terminal observation retains its full billing liability.
            ledger['jobs'][-1]['status'] = 'completed'
        self.assertEqual(ledger['jobs'][0]['reserved_usd'], 0)
        self.assertEqual(len(ledger['jobs'][0]['dispatches']), 4)
        plan, _, dispatch = self.dispatch('unauthorized_fifth')
        before = deepcopy(ledger)
        with self.assertRaises(ValueError):
            control._bind_child(ledger, {'run_id': plan['run_id'], 'plan': plan}, self.output, dispatch)
        self.assertEqual(ledger, before)

    def test_teacher_original_receipt_inventory_changes_on_any_original_byte(self):
        identifier = 'gsm8k:train:00000::concise'
        original = collection.attempt_paths(self.collection, identifier)[1]
        original.parent.mkdir()
        original.write_bytes(b'{"invented_original":true}')
        plan = {'plan_sha256': 'a' * 64}
        control.write(self.collection / 'reviewed_for_collection.json', {'invented_review': True})
        control.write(self.collection / 'collection_session.json', {'plan_sha256': 'a' * 64,
            'review_sha256': 'b' * 64, 'reservation_id': 'invented_teacher'})
        with patch.object(collection, 'validate_run', return_value=(plan, [], [{'id': identifier}])), \
                patch.object(collection, 'validate_review', return_value='b' * 64):
            before = control.receipt_inventory(self.collection)
            original.write_bytes(b'{"invented_original":false}')
            self.assertNotEqual(control.receipt_inventory(self.collection), before)
            original.unlink()
            self.assertNotEqual(control.receipt_inventory(self.collection), before)

    def raw_fixture(self):
        context = worker_fixtures.fixture()
        data, plan, dispatch, tokenizer = self.stack.enter_context(context)
        runtime = worker_fixtures.FakeRuntime(tokenizer, first_long=True)
        with patch.object(control.contract, 'tokenizer_identity', return_value=dict(control.contract.TOKENIZER)):
            result = worker.run_native(data, plan, dispatch, runtime=runtime)
        result['source_verification'] = {'dependency_versions': dict(worker.DEPENDENCIES)}
        result['runtime_model_verification'] = {'fresh_base': True, 'adapter_loaded': False, 'base_geometry_verified': True}
        folder = self.output / 'raw_fixture'
        job = {'role': 'baseline', 'run_id': plan['run_id'], 'plan': plan,
            'data': data, 'folder_path': folder}
        backend = Backend()
        backend.files.update({f'raw/batch{start:04d}.json': worker.encoded(value) for start, value in runtime.raw.items()})
        backend.files.update({f'batches/batch{start:04d}.json': worker.encoded(value) for start, value in runtime.batches.items()})
        return job, result, dispatch, backend

    def test_physical_raw_replay_retains_all200_and_rejects_tampered_tokens_rows_or_hashes(self):
        job, result, dispatch, backend = self.raw_fixture()
        proof = control.verify_raw_result(job, result, dispatch, backend, decode=lambda ids: '#### 7')
        self.assertEqual((proof['raw_batches_verified'], proof['fixed_denominator']), (25, 200))
        self.assertEqual(proof['metrics']['numeric_correct'], 199)
        self.assertEqual(len(backend.downloads), 50)
        for relative in backend.files:
            if relative.startswith('raw/'):
                self.assertEqual((job['folder_path'] / 'wire' / Path(relative).name).read_bytes(), backend.files[relative])
        for mutation in ('wirehash', 'savedrow', 'call', 'missing', 'metrics', 'resultrow', 'noncanonical'):
            altered, fake = deepcopy(result), Backend()
            fake.files = deepcopy(backend.files)
            if mutation == 'wirehash': fake.files['raw/batch0000.json'] += b' '
            elif mutation == 'savedrow':
                value = json.loads(fake.files['batches/batch0000.json'])
                value['rows'][1]['response'] = '#### 99'
                fake.files['batches/batch0000.json'] = worker.encoded(value)
            elif mutation == 'call': altered['call_id'] = 'fc-another-provider-call'
            elif mutation == 'missing': altered['raw_batches'].pop()
            elif mutation == 'metrics': altered['metrics']['baseline']['numeric_correct'] = 200
            elif mutation == 'resultrow': altered['evaluations']['baseline'].pop()
            elif mutation == 'noncanonical':
                fake.files['raw/batch0000.json'] += b' '
                altered['raw_batches'][0]['sha256'] = control.contract.sha(fake.files['raw/batch0000.json'])
            with self.subTest(mutation=mutation), self.assertRaises((ValueError, KeyError)):
                control.verify_raw_result(job, altered, dispatch, fake, decode=lambda ids: '#### 7')

    def state_fixture(self, backend):
        self.save_ledger(self.ledger()); control.allocate_envelope(self.output)
        plan = {'run_id': self.output.name + '_baseline', 'arm': 'baseline', 'token_budget': 0, 'optimizer_updates': 0}
        job = {'role': 'baseline', 'run_id': plan['run_id'], 'plan': plan,
            'data': {'development': deepcopy(self.dev)}, 'folder_path': self.output / 'arms' / plan['run_id']}
        control.write(self.output / 'study_manifest.json', {'invented': 'three-role loading tested separately'})
        review = self.write_review('baseline')
        review['study_manifest_sha256'] = control.sha(self.output / 'study_manifest.json')
        control.write(self.output / 'review_baseline.json', review)
        controller = control.Controller(self.output, backend)
        self.stack.enter_context(patch.object(controller, 'jobs', return_value=[job]))
        return controller, job

    def test_ambiguous_launch_cannot_spawn_again_and_owner_recovery_binds_claim(self):
        backend = Backend()
        controller, job = self.state_fixture(backend)
        first = controller.advance()
        self.assertEqual(first['stage'], 'ambiguous_dispatch_requires_reconciliation')
        self.assertEqual(backend.launches, 1)
        before = (self.state / 'budget.json').read_bytes()
        second = controller.advance()
        self.assertEqual(second['stage'], 'ambiguous_dispatch_requires_reconciliation')
        self.assertEqual(backend.launches, 1)
        self.assertEqual((self.state / 'budget.json').read_bytes(), before)
        dispatch = control.read(job['folder_path'] / 'dispatch.json')
        backend.owner = {'claim_id': '0' * 32, 'intent_sha256': dispatch['intent_sha256'], 'call_id': 'fc-INVENTED-controller'}
        with self.assertRaises(ValueError): controller.recover_dispatches()
        self.assertFalse((job['folder_path'] / 'launch.json').exists())
        backend.owner['claim_id'] = dispatch['claim_id']
        self.assertEqual(controller.recover_dispatches()['recovered'], [job['run_id']])
        self.assertEqual(controller.advance()['stage'], 'running')
        self.assertEqual(backend.launches, 1)

    def test_completed_call_needs_raw200_validation_before_terminal_and_budget_status(self):
        backend = Backend(acknowledge=True)
        controller, job = self.state_fixture(backend)
        self.assertEqual(controller.advance()['stage'], 'native_call_spawned')
        _, result = self.result_fixture()
        result.update(run_id=job['run_id'], plan=job['plan'], call_id='fc-INVENTED-controller')
        backend.answer = {'kind': 'completed', 'result': result}
        with patch.object(control, 'verify_raw_result', side_effect=ValueError('INVENTED missing raw receipts')):
            with self.assertRaises(ValueError): controller.poll()
        self.assertFalse((job['folder_path'] / 'provider_terminal.json').exists())
        entry = next(item for item in control.read(self.state / 'budget.json')['jobs'] if item['run_id'] == job['run_id'])
        self.assertEqual(entry['status'], 'spawned')
        self.assertEqual(entry['reserved_usd'], 1.75)
        now = datetime.now(timezone.utc)
        control.write(self.state / 'modal_billing_snapshot.json', {
            'queried_at_utc': now.isoformat(), 'start_utc': (now - timedelta(days=1)).isoformat(),
            'metered_cost': '9', 'billed_cost': '0', 'source': 'Invented supported-observation fixture'})
        control.write(self.state / 'modal_app_status_snapshot.json', {'apps': [
            {'app_id': 'ap-INVENTED', 'state': 'stopped', 'tasks': 0, 'stopped_at': now.isoformat()}]})
        with patch.object(control, 'verify_raw_result', return_value={'raw_batches_verified': 25, 'fixed_denominator': 200}):
            answer = controller.poll()
        self.assertEqual(answer['changes'], [{'run_id': job['run_id'], 'stage': 'completed'}])
        saved = control.read(self.state / 'budget.json')
        entry = next(item for item in saved['jobs'] if item['run_id'] == job['run_id'])
        self.assertEqual(entry['status'], 'completed')
        self.assertEqual(entry['reserved_usd'], 1.75)
        self.assertEqual(entry['budget_liability']['kind'], 'terminal_usage_pending_collection')
        self.assertEqual(saved['reserved']['modal'], 7)
        self.assertEqual(backend.launches, 1)
        control.write(job['folder_path'] / 'raw_validation.json', {'raw_batches_verified': 24, 'fixed_denominator': 192})
        with self.assertRaises(ValueError): controller.poll()

    def test_terminal_written_before_ledger_crash_recovers_without_launch_or_liability_release(self):
        backend = Backend(acknowledge=True)
        controller, job = self.state_fixture(backend)
        controller.advance()
        _, result = self.result_fixture()
        result.update(run_id=job['run_id'], plan=job['plan'], call_id='fc-INVENTED-controller')
        backend.answer = {'kind': 'completed', 'result': result}
        now = datetime.now(timezone.utc)
        control.write(self.state / 'modal_billing_snapshot.json', {
            'queried_at_utc': now.isoformat(), 'start_utc': (now - timedelta(days=1)).isoformat(),
            'metered_cost': '9', 'billed_cost': '0', 'source': 'Invented supported-observation fixture'})
        control.write(self.state / 'modal_app_status_snapshot.json', {'apps': [
            {'app_id': 'ap-INVENTED', 'state': 'stopped', 'tasks': 0, 'stopped_at': now.isoformat()}]})
        original_write = control.write
        def interrupted(path, value, **kwargs):
            if Path(path) == self.state / 'budget.json' and (job['folder_path'] / 'provider_terminal.json').exists():
                raise PermissionError('INVENTED process crash before ledger commit')
            return original_write(path, value, **kwargs)
        with patch.object(control, 'verify_raw_result', return_value={'raw_batches_verified': 25, 'fixed_denominator': 200}), \
                patch.object(control, 'write', side_effect=interrupted):
            with self.assertRaises(PermissionError): controller.poll()
        self.assertTrue((job['folder_path'] / 'provider_terminal.json').exists())
        saved = control.read(self.state / 'budget.json')
        entry = next(item for item in saved['jobs'] if item['run_id'] == job['run_id'])
        self.assertEqual(entry['status'], 'spawned')
        controller.poll()
        saved = control.read(self.state / 'budget.json')
        entry = next(item for item in saved['jobs'] if item['run_id'] == job['run_id'])
        self.assertEqual(entry['status'], 'completed')
        self.assertEqual(entry['budget_liability']['kind'], 'terminal_usage_pending_collection')
        self.assertEqual(saved['reserved']['modal'], 7)
        self.assertEqual(backend.launches, 1)

    def result_fixture(self):
        plan = {'token_budget': 0, 'optimizer_updates': 0}
        job = {'role': 'baseline', 'run_id': 'synthetic_baseline', 'plan': plan, 'data': {'development': self.dev}}
        rows = [{'id': row['id'], 'gold_answer': row['gold_answer'], 'response': '#### 7',
            'truncated': False, 'generated_tokens': 10, 'elapsed_seconds': 0.25}
            for row in self.dev]
        # A capped, failed and input-limit outcome remain in the denominator.
        rows[0].update(response='#### 7', truncated=True, generated_tokens=1024)
        rows[1].update(response='', truncated=True, generated_tokens=0, failed=True)
        rows[2].update(response='', truncated=True, generated_tokens=0, input_limit=True)
        result = {'stage': 'completed', 'run_id': job['run_id'], 'plan': plan,
            'supervised_tokens': 0, 'optimizer_updates': 0, 'official_test_used': False,
            'evaluation_complete': True, 'retained_evaluation_count': 200, 'raw_pending': False,
            'elapsed_seconds': 100, 'evaluations': {'baseline': rows}}
        return job, result

    def test_fixed200_denominator_retains_cap_failures_and_checks_payload(self):
        job, result = self.result_fixture()
        metrics = control.validate_result(job, result)
        self.assertEqual(metrics['count'], 200)
        self.assertEqual(metrics['numeric_correct'], 197)
        self.assertEqual(metrics['truncated'], 3)
        for mutation in ('drop', 'duplicate', 'reorder', 'gold', 'tokens', 'bool', 'elapsed', 'official', 'budget', 'incomplete', 'pending'):
            altered = deepcopy(result)
            rows = altered['evaluations']['baseline']
            if mutation == 'drop': rows.pop()
            elif mutation == 'duplicate': rows[-1] = deepcopy(rows[0])
            elif mutation == 'reorder': rows.reverse()
            elif mutation == 'gold': rows[3]['gold_answer'] = '8'
            elif mutation == 'tokens': rows[3]['generated_tokens'] = 1025
            elif mutation == 'bool': rows[3]['generated_tokens'] = True
            elif mutation == 'elapsed': altered['elapsed_seconds'] = float('nan')
            elif mutation == 'official': altered['official_test_used'] = True
            elif mutation == 'budget': altered['supervised_tokens'] = 1
            elif mutation == 'incomplete': altered['evaluation_complete'] = False
            elif mutation == 'pending': altered['raw_pending'] = True
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                control.validate_result(job, altered)


if __name__ == '__main__':
    unittest.main()
