"""Synthetic controller fixtures. Never use real budgets, providers or test data."""
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cloud import final_scale_control as control
from cloud import final_scale_execution as execution
from cloud import final_scale_artifacts as artifact_checks
from cloud import final_scale_funding as funding
from cloud import final_scale_seal as seal
from cloud.test_final_scale_execution import fixture, raw_batch, record
from cloud.test_final_scale_funding import ledger as synthetic_ledger

NOW = '2026-11-03T23:00:00+00:00'


class FakeBackend:
    def __init__(self):
        self.refreshes = self.launches = self.stages = self.polls = self.app_checks = 0
        self.tasks = 0
        self.ambiguous = False
        self.stage_error = False
        self.observations = {}

    def refresh(self, state):
        self.refreshes += 1

    def apps(self):
        self.app_checks += 1
        return [{'tasks': self.tasks}]

    def stage(self, folder, bundle):
        self.stages += 1
        execution.validate_remote_metadata(control.read(folder/'intent.json'),
            control.read(folder/'input_descriptor.json'), control.read(folder/'authorization.json'))
        if self.stage_error:
            raise RuntimeError('Synthetic pre-dispatch upload failure')

    def launch(self, folder):
        self.launches += 1
        if not self.ambiguous:
            intent = control.read(folder/'intent.json')
            control.write(folder/'launch.json', execution.launch_receipt(intent, 'fc-controller-fixture-'+str(self.launches)), immutable=True)
        return {'return_code': None if self.ambiguous else 0, 'app_id': 'ap-controller-fixture'}

    def poll(self, folder, call_id):
        self.polls += 1
        return copy.deepcopy(self.observations.get(folder.name, {'kind': 'running'}))


class ControllerTests(unittest.TestCase):
    def setUp(self):
        actual_root = Path(control.__file__).resolve().parent
        parent = actual_root/'runs/test_final_scale_control'
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.temp.name).resolve()
        self.assertTrue(self.root.is_relative_to((actual_root/'runs').resolve()))
        self.state = self.root/'state'
        self.output = self.root/'fixturebundle'
        self.input = self.root/'inputs'
        self.physical_seal = self.root/'physical-seal'
        self.registry = self.root/'global/final_test_access.json'
        for path in (self.state, self.output, self.physical_seal, self.root/'chosen/adapter'):
            path.mkdir(parents=True)
        self.patches = [patch.object(control, 'PRIVATE', self.root), patch.object(control, 'STATE', self.state),
            patch.object(control, 'ROOT', self.root), patch.object(seal, 'ACCESS', self.registry)]
        for item in self.patches:
            item.start()
        self.authorization, self.payload, _, _ = fixture()
        original = self.authorization['sealed']
        self.owner = '0'*64
        body = {key: copy.deepcopy(value) for key, value in original.items() if key != 'seal_sha256'}
        body['owner_sha256'] = control.digest(self.owner)
        body['access_registry_path'] = str(self.registry)
        body['checkpoint'].update(run_path=str(self.root/'chosen'), adapter_path=str(self.root/'chosen/adapter'))
        self.sealed = record(body, 'seal_sha256')
        identity = seal._permit_identity(self.sealed, str(self.input))
        self.permit = seal._hash_record(dict(identity, stage='access_begun_before_source_read', began_at_utc=NOW), 'permit_sha256')
        dataset = {key: copy.deepcopy(value) for key, value in self.authorization['dataset_receipt'].items() if key != 'receipt_sha256'}
        dataset.update(identity, permit_sha256=self.permit['permit_sha256'])
        self.dataset = record(dataset, 'receipt_sha256')
        self.authorization = execution.authorization_bundle(self.sealed, self.permit, self.dataset,
            adapter_path='fixturebundle/adapter', model_config_descriptor={
                'volume_path': 'fixturebundle/model_config.json', 'sha256': execution.MODEL_CONFIG_SHA256, 'bytes': 1000})
        self.config = self.root/'config.json'
        self.config.write_bytes(b'{"synthetic_model_config":true}')
        self.bundle = {'schema_version': 1, 'version': control.VERSION, 'bundle_id': self.output.name,
            'seal_folder': str(self.physical_seal), 'input_folder': str(self.input),
            'seal_sha256': self.sealed['seal_sha256'], 'freeze_sha256': self.sealed['contract']['freeze_sha256'],
            'review': {}, 'model_config_path': str(self.config), 'model_config_sha256': execution.MODEL_CONFIG_SHA256,
            'stage': 'prepared_metadata_only_not_funded'}
        control.write(self.output/'bundle.json', self.bundle, immutable=True)
        control.write(self.physical_seal/'access_owner.json', {'owner_token': self.owner, 'seal_sha256': self.sealed['seal_sha256']})
        control.write(self.state/'budget.json', synthetic_ledger())
        self.backend = FakeBackend()
        self.runner = control.Controller(self.output, state=self.state, backend=self.backend, clock=lambda: NOW,
            decoder=lambda ids: '#### 7')
        self.runner.load = Mock(return_value=(self.bundle, self.sealed))
        verify = patch.object(seal, 'verify', return_value=self.sealed)
        verify.start(); self.patches.append(verify)

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def attempt(self, *, checkpoint='base', shard_id='shard000'):
        source_payload = fixture(checkpoint=checkpoint, shard_id=shard_id)[1]
        payload = execution.make_payload(self.authorization, source_payload['binding'], source_payload['rows'],
            checkpoint=checkpoint, shard_id=shard_id)
        run_id = 'fixturebundle-'+checkpoint+'-'+shard_id+'-a0'
        desc = execution.describe_input(payload, self.authorization,
            volume_path='fixturebundle/inputs/'+run_id+'.json', checkpoint=checkpoint, shard_id=shard_id)
        intent = execution.build_intent(self.sealed, desc, run_id=run_id, checkpoint=checkpoint, shard_id=shard_id)
        folder = self.output/'attempts'/run_id
        folder.mkdir(parents=True)
        for name, value in (('intent.json', intent), ('input_descriptor.json', desc), ('authorization.json', self.authorization)):
            control.write(folder/name, value, immutable=True)
        control.write_bytes(folder/'payload.json', execution.payload_bytes(payload))
        return folder, intent, payload

    def allocate(self):
        return self.runner.allocate(authorized=True)

    def launched(self):
        folder, intent, payload = self.attempt()
        self.allocate()
        self.assertEqual(self.runner.advance(authorized=True)['stage'], 'spawned')
        launch = control.read(folder/'launch.json')
        return folder, intent, payload, launch

    def outcomes(self, folder, intent, payload, launch, *, complete=False):
        starts = range(intent['start'], intent['stop'], 8) if complete else [intent['start']]
        for start in starts:
            raw = raw_batch(intent, launch, payload, start)
            batch = execution.derive_raw_batch(intent, launch, raw, payload['binding'], lambda ids: '#### 7')
            name = f'batch{start:04d}.json'
            control.write_bytes(folder/'raw'/name, execution.payload_bytes(raw))
            control.write(folder/'batches'/name, batch, immutable=True)

    def terminal_observation(self, folder, launch, *, kind='failed', stage=None):
        value = {'kind': kind, 'provider_call_id': launch['call_id'], 'observed_at_utc': NOW,
            'result': {'stage': stage or ('completed' if kind == 'completed' else kind)}}
        self.backend.observations[folder.name] = value
        return value

    def loaded(self):
        """Reconstruct only the invented execution fixture's complete sample."""
        rows = [{'id': question['id'], 'source_index': question['source_index'],
            'prompt': f"INVENTED input {question['source_index']}", 'gold_answer': question['gold_answer'],
            'source_split': 'test', 'role': 'final_eval_only', 'training_eligible': False}
            for question in self.payload['binding']['questions']]
        return {'binding': copy.deepcopy(self.payload['binding']), 'rows': rows}

    def failed_parent(self):
        folder, intent, payload, launch = self.launched()
        self.outcomes(folder, intent, payload, launch)
        self.terminal_observation(folder, launch)
        self.runner.poll()
        control.write(self.output/'authorization.json', self.authorization, immutable=True)
        return folder, intent, payload, launch

    def recovery_review(self, folder):
        attempt = self.runner._attempt(folder)
        intent = control.read(folder/'intent.json'); payload = control.read(folder/'payload.json')
        prefix = control.receipts.recover_prefix(self.sealed['contract'], payload['binding'],
            intent['checkpoint'], intent['shard_id'], [attempt])
        review = {'reviewed': True, 'controller_sha256': control.sha(control.__file__),
            'freeze_sha256': self.sealed['contract']['freeze_sha256'], 'seal_sha256': self.sealed['seal_sha256'],
            'parent_call_id': attempt['launch']['call_id'],
            'parent_terminal_sha256': attempt['terminal']['terminal_sha256'],
            'prefix_sha256': prefix['prefix_sha256'],
            'remaining_questions': prefix['expected_count']-prefix['retained_count'],
            'deterministic_failure_reconciled': True}
        path = self.output/'review-recovery.json'
        control.write(path, review)
        return path, review

    def settlement_report(self, *, paired='completed', teacher='completed', unknown=0):
        return {'count': 1000, 'paired_status': paired, 'teacher': {'status': teacher,
            'recorded_peak_token_estimate_usd': '0.20', 'unknown_usage_attempts': unknown}}

    def test_default_inspection_reads_metadata_without_content_or_providers(self):
        folder, _, _ = self.attempt()
        (folder/'payload.json').write_bytes(b'PRIVATE_INVENTED_QUESTION_DO_NOT_READ')
        with patch.object(control.loader, 'prepare', side_effect=AssertionError('No final source access')), \
             patch.object(control.loader, 'load_prepared', side_effect=AssertionError('No final payload read')):
            result = self.runner.inspect()
            stdout = io.StringIO()
            with patch.object(sys, 'argv', ['controller', '--output', str(self.output)]), patch('sys.stdout', stdout):
                control.main()
        self.assertFalse(result['official_test_accessed_by_inspection'])
        self.assertNotIn('PRIVATE_INVENTED', json.dumps(result)+stdout.getvalue())
        self.assertEqual((self.backend.refreshes, self.backend.polls, self.backend.launches), (0, 0, 0))
        self.assertFalse(self.registry.exists())

    def test_paid_and_content_actions_need_explicit_authorization(self):
        for method in (self.runner.allocate, self.runner.prepare_inputs, self.runner.advance,
                self.runner.derive_raw, self.runner.report, self.runner.finalize):
            with self.subTest(method=method.__name__), self.assertRaises(ValueError):
                method()
        self.assertEqual((self.backend.refreshes, self.backend.launches, self.backend.stages), (0, 0, 0))

    def test_allocation_rebinds_only_fresh_funding_and_cannot_repeat(self):
        historical = copy.deepcopy(self.sealed['review'])
        before = control.read(self.state/'budget.json')
        self.allocate()
        saved = control.read(self.output/'allocation_review.json')
        expected = dict(historical, funding_snapshot_sha256=control.digest(funding.snapshot(before, as_of_utc=NOW)))
        self.assertEqual(saved, expected)
        self.assertEqual(self.sealed['review'], historical)
        ledger = control.read(self.state/'budget.json')
        self.assertEqual(ledger['reserved'], {'modal': 12.25, 'deepseek': 5.0})
        with self.assertRaises(ValueError):
            self.allocate()
        self.assertEqual(control.read(self.state/'budget.json'), ledger)
        self.assertFalse(self.registry.exists())

    def test_underfunded_allocation_has_no_claim_permit_or_ledger_mutation(self):
        ledger = control.read(self.state/'budget.json')
        ledger['estimated_spend']['modal'] = 20
        ledger['modal_budget_accounting']['estimated_spend_usd'] = 20
        control.write(self.state/'budget.json', ledger)
        before = (self.state/'budget.json').read_bytes()
        with self.assertRaises(ValueError):
            self.allocate()
        self.assertEqual((self.state/'budget.json').read_bytes(), before)
        self.assertFalse(self.registry.exists())
        self.assertFalse((self.output/'allocation_review.json').exists())

    def test_source_and_adapter_preflight_fail_before_any_loader_access(self):
        self.allocate()
        for failed in ('source', 'adapter'):
            with patch.object(artifact_checks, 'verify_packaged_sources',
                    side_effect=ValueError('Synthetic changed source') if failed == 'source' else None), \
                 patch.object(artifact_checks, 'verify_adapter',
                    side_effect=ValueError('Synthetic changed adapter') if failed == 'adapter' else None), \
                 patch.object(control.loader, 'prepare', side_effect=AssertionError('Loader must stay unopened')):
                with self.subTest(failed=failed), self.assertRaises(ValueError):
                    self.runner.prepare_inputs(authorized=True)
        self.assertFalse(self.registry.exists())
        self.assertFalse((self.output/'funded_access_review.json').exists())

    def test_fresh_first_access_preserves_real_reservations_and_exact_caps(self):
        self.allocate()
        before = (self.state/'budget.json').read_bytes()
        permit = self.runner._begin_funded_access(self.bundle, self.sealed)
        self.assertEqual((self.state/'budget.json').read_bytes(), before)
        record = control.read(self.output/'funded_access_review.json')
        self.assertFalse(record['ledger_reservations_released'])
        self.assertEqual(record['actual_committed_funding_snapshot']['reserved_usd'], {'modal': '12.25', 'deepseek': '5.0'})
        expected = dict(self.sealed['review'], funding_snapshot_sha256=control.digest(record['planning_snapshot_before_own_allocation']))
        self.assertEqual(record['review'], expected)
        self.assertEqual(permit['seal_sha256'], self.sealed['seal_sha256'])
        self.assertEqual(self.runner._begin_funded_access(self.bundle, self.sealed), permit)

    def test_stale_first_access_or_missing_teacher_keeps_global_source_closed(self):
        self.allocate()
        ledger = control.read(self.state/'budget.json')
        saved = copy.deepcopy(ledger)
        for failure in ('stale', 'teacher'):
            value = copy.deepcopy(saved)
            if failure == 'stale':
                value['modal_observation']['queried_at_utc'] = '2026-11-03T22:00:00+00:00'
            else:
                value['jobs'] = [job for job in value['jobs'] if job.get('service') != 'deepseek']
            control.write(self.state/'budget.json', value)
            with self.subTest(failure=failure), self.assertRaises(ValueError):
                self.runner._begin_funded_access(self.bundle, self.sealed)
            self.assertFalse(self.registry.exists())

    def test_one_launch_running_call_blocks_duplicate_dispatch(self):
        folder, _, _, _ = self.launched()
        result = self.runner.advance(authorized=True)
        self.assertEqual(result['stage'], 'monitoring')
        self.assertEqual(self.backend.launches, 1)
        ledger = control.read(self.state/'budget.json')
        self.assertEqual(len([j for j in ledger['jobs'] if j.get('checkpoint')]), 1)
        self.assertEqual(ledger['reserved']['modal'], 12.25)
        self.assertTrue((folder/'dispatch_claim.json').exists())

    def test_changed_payload_blocks_before_claim_or_escrow_transfer(self):
        folder, _, _ = self.attempt(); self.allocate()
        before = (self.state/'budget.json').read_bytes()
        payload = control.read(folder/'payload.json')
        payload['rows'][0]['gold_answer'] = '8'
        (folder/'payload.json').write_bytes(execution.payload_bytes(payload))
        with self.assertRaises(ValueError):
            self.runner.advance(authorized=True)
        self.assertEqual((self.state/'budget.json').read_bytes(), before)
        self.assertFalse((folder/'dispatch_claim.json').exists())
        self.assertFalse((folder/'dispatch_started.json').exists())
        self.assertEqual((self.backend.stages, self.backend.launches), (0, 0))

    def test_outside_gpu_work_blocks_access_and_dispatch_without_claim(self):
        folder, _, _ = self.attempt(); self.allocate(); self.backend.tasks = 1
        before = (self.state/'budget.json').read_bytes()
        with patch.object(control.loader, 'prepare', side_effect=AssertionError('Busy GPU must precede source access')):
            with self.assertRaisesRegex(ValueError, 'GPU work'):
                self.runner.prepare_inputs(authorized=True)
        self.assertEqual(self.runner.advance(authorized=True)['stage'], 'outside_gpu_work_active')
        self.assertEqual((self.state/'budget.json').read_bytes(), before)
        self.assertFalse(self.registry.exists())
        self.assertFalse((folder/'dispatch_claim.json').exists())
        self.assertEqual((self.backend.stages, self.backend.launches), (0, 0))

    def test_claim_write_survives_ledger_commit_crash_without_dispatch(self):
        folder, _, _ = self.attempt(); self.allocate()
        before = (self.state/'budget.json').read_bytes()
        original = control.write
        def interrupted(path, value, **kwargs):
            if Path(path) == self.state/'budget.json':
                raise RuntimeError('Synthetic transfer commit interruption')
            return original(path, value, **kwargs)
        with patch.object(control, 'write', side_effect=interrupted):
            with self.assertRaisesRegex(RuntimeError, 'transfer commit'):
                self.runner.advance(authorized=True)
        self.assertTrue((folder/'dispatch_claim.json').exists())
        self.assertEqual((self.state/'budget.json').read_bytes(), before)
        self.assertFalse((folder/'dispatch_started.json').exists())
        self.assertIn('requires_reconciliation', self.runner.advance(authorized=True)['stage'])
        self.assertEqual((self.state/'budget.json').read_bytes(), before)
        self.assertEqual((self.backend.stages, self.backend.launches), (0, 0))

    def test_ambiguous_launch_and_pre_dispatch_failure_never_retry_or_retransfer(self):
        self.attempt(); self.allocate(); self.backend.ambiguous = True
        self.assertEqual(self.runner.advance(authorized=True)['stage'], 'ambiguous_dispatch')
        before = control.read(self.state/'budget.json')
        self.assertEqual(self.runner.advance(authorized=True)['stage'], 'action_required')
        self.assertEqual(self.backend.launches, 1)
        self.assertEqual(control.read(self.state/'budget.json'), before)

    def test_upload_failure_keeps_bound_claim_and_blocks_new_launch(self):
        folder, _, _ = self.attempt(); self.allocate(); self.backend.stage_error = True
        with self.assertRaises(RuntimeError):
            self.runner.advance(authorized=True)
        before = control.read(self.state/'budget.json')
        self.assertTrue((folder/'dispatch_claim.json').exists())
        self.assertFalse((folder/'dispatch_started.json').exists())
        result = self.runner.advance(authorized=True)
        self.assertIn('requires_reconciliation', result['stage'])
        self.assertEqual((self.backend.launches, self.backend.stages), (0, 1))
        self.assertEqual(control.read(self.state/'budget.json'), before)

    def test_provider_terminal_is_persisted_before_canonical_receipt(self):
        folder, intent, payload, launch = self.launched()
        self.outcomes(folder, intent, payload, launch)
        observed = self.terminal_observation(folder, launch)
        original = control.write
        def audited(path, value, **kwargs):
            if Path(path).name == 'terminal.json':
                self.assertEqual(control.read(folder/'provider_observation.json'), observed)
            return original(path, value, **kwargs)
        with patch.object(control, 'write', side_effect=audited):
            self.runner.poll()
        terminal = control.read(folder/'terminal.json')
        self.assertTrue(terminal['confirmed_terminal'])
        self.assertEqual(terminal['call_id'], launch['call_id'])
        self.assertEqual(terminal['retained_count'], 8)

    def test_orphan_raw_bytes_are_preserved_and_prevent_a_fake_terminal(self):
        folder, intent, payload, launch = self.launched()
        raw = raw_batch(intent, launch, payload, 0)
        path = folder/'raw/batch0000.json'
        control.write_bytes(path, execution.payload_bytes(raw))
        self.terminal_observation(folder, launch)
        before = path.read_bytes()
        result = self.runner.poll()
        self.assertEqual(result['stage'], 'action_required')
        self.assertTrue((folder/'provider_observation.json').exists())
        self.assertFalse((folder/'terminal.json').exists())
        self.assertEqual(path.read_bytes(), before)

    def test_raw_byte_or_derived_response_changes_cannot_confirm_completion(self):
        folder, intent, payload, launch = self.launched()
        self.outcomes(folder, intent, payload, launch)
        self.terminal_observation(folder, launch)
        raw_path = folder/'raw/batch0000.json'
        raw_bytes = raw_path.read_bytes()
        raw_path.write_bytes(raw_bytes+b' ')
        with self.assertRaisesRegex(ValueError, 'Raw file byte hash'):
            self.runner.poll()
        raw_path.write_bytes(raw_bytes)
        path = folder/'batches/batch0000.json'
        changed = control.read(path)
        changed['rows'][0]['response'] = '#### 8'
        control.write(path, changed)
        with self.assertRaisesRegex(ValueError, 'Derived response'):
            self.runner.poll()
        self.assertFalse((folder/'terminal.json').exists())

    def test_terminal_ledger_write_crash_resumes_from_original_observation(self):
        folder, intent, payload, launch = self.launched()
        self.outcomes(folder, intent, payload, launch)
        observation = self.terminal_observation(folder, launch)
        original = self.runner.edit_budget
        self.runner.edit_budget = Mock(side_effect=RuntimeError('Synthetic ledger-write interruption'))
        with self.assertRaises(RuntimeError):
            self.runner.poll()
        self.assertTrue((folder/'terminal.json').exists())
        self.assertEqual(control.read(folder/'provider_observation.json'), observation)
        polls = self.backend.polls
        self.runner.edit_budget = original
        self.backend.poll = Mock(side_effect=AssertionError('Saved provider evidence must be reused'))
        self.runner.poll()
        job = next(j for j in control.read(self.state/'budget.json')['jobs'] if j['run_id'] == intent['run_id'])
        self.assertEqual(job['status'], 'failed')
        self.assertEqual(job['call_id'], launch['call_id'])
        self.assertEqual(self.backend.polls, polls)
        self.assertEqual(self.backend.launches, 1)

    def test_recovery_requires_exact_engineering_review_before_private_loader(self):
        folder, _, _, _ = self.failed_parent()
        path, original = self.recovery_review(folder)
        for key, value in (('controller_sha256', '0'*64), ('parent_terminal_sha256', '0'*64),
                ('prefix_sha256', '0'*64), ('remaining_questions', 359),
                ('deterministic_failure_reconciled', False)):
            control.write(path, dict(original, **{key: value}))
            with self.subTest(key=key), patch.object(control.loader, 'load_prepared',
                    side_effect=AssertionError('Unreviewed recovery must not read private sample')):
                with self.assertRaises(ValueError):
                    self.runner.prepare_recovery('base', 'shard000', review_path=path, authorized=True)
        self.assertEqual(len(list(self.output.glob('attempts/*/intent.json'))), 1)
        self.assertEqual(self.backend.launches, 1)

    def test_recovery_requires_provider_termination_and_matching_call(self):
        folder, _, _, _ = self.failed_parent()
        path, _ = self.recovery_review(folder)
        proof_path = folder/'provider_observation.json'; original = control.read(proof_path)
        for proof in (None, dict(original, kind='running'), dict(original, provider_call_id='fc-other-call')):
            if proof is None:
                proof_path.unlink()
            else:
                control.write(proof_path, proof)
            with self.subTest(proof=proof), patch.object(control.loader, 'load_prepared',
                    side_effect=AssertionError('Unconfirmed provider must not authorize sample read')):
                with self.assertRaises(ValueError):
                    self.runner.prepare_recovery('base', 'shard000', review_path=path, authorized=True)
        self.assertEqual(len(list(self.output.glob('attempts/*/intent.json'))), 1)

    def test_recovery_rejects_original_raw_bytes_changed_after_terminal(self):
        folder, _, _, _ = self.failed_parent()
        path, _ = self.recovery_review(folder)
        raw = folder/'raw/batch0000.json'; raw.write_bytes(raw.read_bytes()+b' ')
        with patch.object(control.loader, 'load_prepared',
                side_effect=AssertionError('Changed original tokens must block recovery')):
            with self.assertRaises(ValueError):
                self.runner.prepare_recovery('base', 'shard000', review_path=path, authorized=True)

    def test_recovery_requires_unpaid_raw_derivation_and_explicit_authorization(self):
        folder, _, _, _ = self.failed_parent()
        path, _ = self.recovery_review(folder)
        with self.assertRaises(ValueError):
            self.runner.prepare_recovery('base', 'shard000', review_path=path)
        (folder/'batches/batch0000.json').unlink()
        with patch.object(control.loader, 'load_prepared', side_effect=AssertionError('Original raw must be derived first')):
            with self.assertRaises(ValueError):
                self.runner.prepare_recovery('base', 'shard000', review_path=path, authorized=True)
        self.assertEqual(self.backend.launches, 1)

    def test_returned_pending_raw_is_derived_without_provider_or_regeneration(self):
        folder, intent, payload, launch = self.launched()
        control.write(self.output/'authorization.json', self.authorization, immutable=True)
        raw = raw_batch(intent, launch, payload, 0)
        worker = execution.terminal_receipt(intent, launch, [], [], 'failed', raw_pending=True,
            raw_pending_start=0, raw_pending_sha256=hashlib.sha256(execution.payload_bytes(raw)).hexdigest())
        observed = self.terminal_observation(folder, launch, kind='completed', stage='failed')
        observed['result'].update(raw_pending=True, raw_pending_record=raw, worker_terminal=worker)
        self.assertEqual(self.runner.poll()['stage'], 'action_required')
        self.assertFalse((folder/'terminal.json').exists())
        self.backend.poll = Mock(side_effect=AssertionError('Original provider observation must be reused'))
        self.runner.derive_raw(authorized=True)
        self.assertEqual((folder/'raw/batch0000.json').read_bytes(), execution.payload_bytes(raw))
        terminal = control.read(folder/'terminal.json')
        self.assertEqual(terminal['retained_count'], 8)
        proof = control.read(folder/'raw_derivation_attestation.json')
        self.assertFalse(proof['new_generation_or_provider_request'])
        self.assertEqual(proof['provider_observation_sha256'], control.digest(observed))
        path, _ = self.recovery_review(folder)
        control.write(folder/'raw_derivation_attestation.json', dict(proof, provider_observation_sha256='0'*64))
        with patch.object(control.loader, 'load_prepared', side_effect=AssertionError('Forged raw attestation blocks recovery')):
            with self.assertRaises(ValueError):
                self.runner.prepare_recovery('base', 'shard000', review_path=path, authorized=True)
        self.assertEqual(self.backend.launches, 1)

    def test_reviewed_recovery_preserves_prefix_and_uses_only_one_global_slot(self):
        folder, _, _, launch = self.failed_parent()
        path, review = self.recovery_review(folder)
        before = {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob('*') if p.is_file()}
        parent = self.runner._attempt(folder)
        with patch.object(control.loader, 'load_prepared', return_value=self.loaded()):
            result = self.runner.prepare_recovery('base', 'shard000', review_path=path, authorized=True)
        child = self.output/'attempts'/result['run_id']
        payload = control.read(child/'payload.json'); intent = control.read(child/'intent.json')
        self.assertEqual(payload['prior_attempts'], [parent])
        self.assertEqual(intent['input_descriptor']['retained_count'], 8)
        self.assertEqual(intent['input_descriptor']['parent_call_id'], launch['call_id'])
        self.assertEqual(control.read(child/'recovery_review.json'), review)
        self.assertEqual(before, {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob('*') if p.is_file()})
        self.assertEqual(self.backend.launches, 1)
        self.assertEqual(self.runner.advance(authorized=True)['stage'], 'spawned')
        ledger = control.read(self.state/'budget.json')
        self.assertEqual(sum(bool(j.get('is_recovery')) for j in ledger['jobs']), 1)
        self.assertEqual(ledger['reserved']['modal'], 12.25)
        with patch.object(control.loader, 'load_prepared', side_effect=AssertionError('Global recovery is exhausted')):
            with self.assertRaisesRegex(ValueError, 'recovery.*used'):
                self.runner.prepare_recovery('chosen', 'shard001', review_path=path, authorized=True)
        self.assertEqual(self.backend.launches, 2)

    def test_completed_or_running_parent_cannot_prepare_paid_replay(self):
        folder, intent, payload, launch = self.launched()
        control.write(self.output/'authorization.json', self.authorization, immutable=True)
        path = self.output/'not-approved-review.json'; control.write(path, {})
        with patch.object(control.loader, 'load_prepared', side_effect=AssertionError('Parent is not a recovery candidate')):
            with self.assertRaises(ValueError):
                self.runner.prepare_recovery('base', 'shard000', review_path=path, authorized=True)
        self.outcomes(folder, intent, payload, launch, complete=True)
        self.terminal_observation(folder, launch, kind='completed')
        self.runner.poll()
        with patch.object(control.loader, 'load_prepared', side_effect=AssertionError('Completed shard must never replay')):
            with self.assertRaises(ValueError):
                self.runner.prepare_recovery('base', 'shard000', review_path=path, authorized=True)
        self.assertEqual(self.backend.launches, 1)

    def test_private_report_retains_partial_denominator_without_accuracy_or_text(self):
        self.failed_parent()
        with patch.object(control.loader, 'load_prepared', return_value=self.loaded()):
            result = self.runner.report(authorized=True)
        self.assertEqual(result['count'], 1000)
        self.assertEqual(result['paired_status'], 'unavailable')
        self.assertEqual(result['checkpoints']['base']['retained_count'], 8)
        self.assertIsNone(result['checkpoints']['base']['metrics'])
        self.assertIsNone(result['chosen_vs_base'])
        self.assertNotIn('INVENTED input', json.dumps(result))
        self.assertNotIn('#### 7', json.dumps(result))
        self.assertEqual(self.backend.launches, 1)

    def test_finalize_partial_or_unknown_teacher_usage_cannot_release_liabilities(self):
        self.allocate(); before = (self.state/'budget.json').read_bytes()
        reports = [self.settlement_report(paired='unavailable'), self.settlement_report(teacher='partial'),
            self.settlement_report(unknown=1)]
        for result in reports:
            with self.subTest(result=result), patch.object(self.runner, 'report', return_value=result):
                with self.assertRaises(ValueError):
                    self.runner.finalize(authorized=True)
            self.assertEqual((self.state/'budget.json').read_bytes(), before)
            self.assertFalse((self.output/'completed.json').exists())

    def test_finalize_running_or_outside_gpu_work_cannot_release_liabilities(self):
        self.allocate(); before = (self.state/'budget.json').read_bytes()
        with patch.object(self.runner, 'poll', return_value={'running': ['fc-unknown'], 'blocked': []}), \
             patch.object(self.runner, 'report', side_effect=AssertionError('Still running')):
            with self.assertRaises(ValueError):
                self.runner.finalize(authorized=True)
        self.backend.tasks = 1
        with patch.object(self.runner, 'report', return_value=self.settlement_report()):
            with self.assertRaisesRegex(ValueError, 'GPU work'):
                self.runner.finalize(authorized=True)
        self.assertEqual((self.state/'budget.json').read_bytes(), before)
        self.assertFalse((self.output/'completed.json').exists())

    def test_finalize_releases_only_unused_escrow_preserving_other_liabilities(self):
        folder, _, _, _ = self.failed_parent()
        ledger = control.read(self.state/'budget.json')
        ledger['jobs'].extend([
            {'run_id': 'external-gpu-liability', 'service': 'modal', 'status': 'collection_pending', 'reserved_usd': 2.0},
            {'run_id': 'external-teacher-liability', 'service': 'deepseek', 'status': 'ambiguous', 'reserved_usd': 1.0}])
        ledger['reserved']['modal'] += 2.; ledger['reserved']['deepseek'] += 1.
        control.write(self.state/'budget.json', ledger)
        child_before = next(j for j in ledger['jobs'] if j.get('checkpoint') == 'base')
        external_before = [j for j in ledger['jobs'] if j['run_id'].startswith('external-')]
        with patch.object(self.runner, 'poll', return_value={'running': [], 'blocked': []}), \
             patch.object(self.runner, 'report', return_value=self.settlement_report()):
            result = self.runner.finalize(authorized=True)
        self.assertEqual(result['stage'], 'final_bundle_completed')
        after = control.read(self.state/'budget.json')
        escrow = next(j for j in after['jobs'] if j['run_id'] == 'fixturebundle-modal-escrow')
        self.assertEqual(escrow['released_unused_usd'], 10.5)
        self.assertEqual(escrow['reserved_usd'], 0.)
        self.assertEqual(next(j for j in after['jobs'] if j.get('checkpoint') == 'base'), child_before)
        self.assertEqual([j for j in after['jobs'] if j['run_id'].startswith('external-')], external_before)
        self.assertEqual(after['reserved']['modal'], 3.75)
        self.assertEqual(after['reserved']['deepseek'], 1.)
        self.assertTrue((self.output/'completed.json').exists())

    def test_finalization_is_idempotent_after_completion_without_provider_refresh(self):
        self.allocate()
        with patch.object(self.runner, 'report', return_value=self.settlement_report()):
            self.runner.finalize(authorized=True)
        before = (self.state/'budget.json').read_bytes()
        self.backend.refresh = Mock(side_effect=AssertionError('Completion must not refresh paid providers'))
        with patch.object(self.runner, 'report', return_value=self.settlement_report()):
            result = self.runner.finalize(authorized=True)
        self.assertEqual(result['stage'], 'final_bundle_already_completed')
        self.assertEqual((self.state/'budget.json').read_bytes(), before)

    def test_finalize_completion_write_crash_resumes_without_releasing_twice(self):
        self.allocate()
        original = control.write
        def interrupted(path, value, **kwargs):
            if Path(path) == self.output/'completed.json':
                raise RuntimeError('Synthetic completion-receipt interruption')
            return original(path, value, **kwargs)
        with patch.object(self.runner, 'report', return_value=self.settlement_report()), \
             patch.object(control, 'write', side_effect=interrupted):
            with self.assertRaisesRegex(RuntimeError, 'completion-receipt'):
                self.runner.finalize(authorized=True)
        self.assertFalse((self.output/'completed.json').exists())
        after_commit = (self.state/'budget.json').read_bytes()
        with patch.object(self.runner, 'report', return_value=self.settlement_report()):
            result = self.runner.finalize(authorized=True)
        self.assertEqual(result['stage'], 'final_bundle_completed')
        self.assertTrue((self.output/'completed.json').exists())
        self.assertEqual((self.state/'budget.json').read_bytes(), after_commit)


class ImmutableVolumeUploadTests(unittest.TestCase):
    def setUp(self):
        parent=Path(control.__file__).resolve().parent/'runs/test_final_scale_upload'
        parent.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=parent);self.root=Path(self.temp.name)
        self.patch=patch.object(control,'PRIVATE',self.root);self.patch.start()
        self.source=self.root/'payload.json';self.source.write_bytes(b'{"synthetic":true}\n')

    def tearDown(self):
        self.patch.stop();self.temp.cleanup()

    class Volume:
        def __init__(self,files):self.files=dict(files);self.uploads=0;self.pending=[];self.force=None
        def read_file(self,path):
            if path not in self.files:raise FileNotFoundError(path)
            return iter([self.files[path]])
        def batch_upload(self,*,force):self.force=force;self.uploads+=1;return self
        def __enter__(self):return self
        def put_file(self,source,remote):self.pending.append((source,remote))
        def __exit__(self,kind,value,tb):
            if kind:return False
            if any(remote in self.files for _,remote in self.pending):raise FileExistsError('Concurrent creator')
            for source,remote in self.pending:self.files[remote]=Path(source).read_bytes()

    def test_new_staging_is_idempotent_and_never_forces_overwrite(self):
        volume=self.Volume({});files=[(self.source,'fixturebundle/inputs/payload.json')]
        control.upload_immutable(volume,files)
        self.assertFalse(volume.force);self.assertEqual(volume.uploads,1)
        self.assertEqual(volume.files[files[0][1]],self.source.read_bytes())
        control.upload_immutable(volume,files)
        self.assertEqual(volume.uploads,1)

    def test_conflicting_existing_remote_bytes_are_preserved(self):
        remote='fixturebundle/inputs/payload.json';volume=self.Volume({remote:b'original artifact'})
        with self.assertRaises(ValueError):control.upload_immutable(volume,[(self.source,remote)])
        self.assertEqual(volume.files[remote],b'original artifact');self.assertEqual(volume.uploads,0)

    def test_ambiguous_read_never_retries_or_writes(self):
        volume=self.Volume({});volume.read_file=Mock(side_effect=TimeoutError('synthetic transport'))
        with self.assertRaises(TimeoutError):control.upload_immutable(volume,[(self.source,'fixturebundle/inputs/payload.json')])
        self.assertEqual(volume.read_file.call_count,1);self.assertEqual(volume.uploads,0)

    def test_decoder_uses_the_existing_pinned_project_cache_without_download(self):
        runner=control.Controller(self.root/'unprepared',state=self.root/'state')
        tokenizer=Mock();tokenizer.decode.return_value='#### 7'
        with patch('transformers.AutoTokenizer.from_pretrained',return_value=tokenizer) as load:
            self.assertEqual(runner.decode([7]),'#### 7');self.assertEqual(runner.decode([8]),'#### 7')
        load.assert_called_once_with(control.contract_api.MODEL,revision=control.contract_api.REVISION,
            cache_dir=control.ROOT/'runs/tokenizer_cache',local_files_only=True)


if __name__ == '__main__':
    unittest.main()
