"""Pure invented scale-dispatch fixtures; no official data or filesystem I/O."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cloud import final_scale_execution as execute
from cloud import final_scale_contract as contract_api
from cloud import final_scale_loader as loader
from cloud import final_scale_receipts as receipts


def record(value, field):
    return dict(value, **{field: execute.digest(value)})


def fixture(count=1000, *, checkpoint='base', shard_id='shard000'):
    roles = {role: sorted(execute.REQUIRED_SOURCE_ROLES.get(role, {'fixture_'+role+'.py'}))
        for role in contract_api.SOURCE_ROLES}
    sources = {name: execute.digest(name) for names in roles.values() for name in names}
    inventory = {'adapter_config.json': 'a'*64, 'adapter_model.safetensors': 'b'*64}
    selected = {'model': contract_api.MODEL, 'revision': contract_api.REVISION, 'checkpoint_id': 'synthetic-chosen',
        'adapter_inventory_sha256': execute.digest(inventory), 'development_evidence_sha256': 'c'*64}
    contract = contract_api.build_contract(count, source_hashes=sources, source_roles=roles, selected=selected)
    calibration = contract_api.calibration(contract, base_generation_seconds=100, chosen_generation_seconds=100,
        evidence_hashes={'base': 'd'*64, 'chosen': 'e'*64})
    stamp = '2026-11-03T23:00:00+00:00'
    funding = {'observed_at_utc': {'modal': stamp, 'deepseek': stamp},
        'new_paid_work_allowed': {'modal': True, 'deepseek': True}, 'limits_usd': {'modal': '30', 'deepseek': '20'},
        'spent_usd': {'modal': '0', 'deepseek': '0'}, 'reserved_usd': {'modal': '0', 'deepseek': '0'}}
    review = contract_api.review_template(contract)
    review.update(reviewed=True, no_tuning_after_access_acknowledged=True, complete_denominator_acknowledged=True,
        all_source_roles_reviewed=True, calibration_sha256=calibration['calibration_sha256'], funding_snapshot_sha256=execute.digest(funding))
    sealed = record({'schema_version': 1, 'version': 'physical-final-scale-seal-v1',
        'official_test_accessed_by_seal': False, 'paid_work_launched': False, 'contract': contract,
        'checkpoint': {'selected': selected, 'adapter_files_sha256': inventory}, 'owner_sha256': 'f'*64,
        'review': review, 'calibration': calibration, 'funding_snapshot': funding, 'reviewed_as_of_utc': stamp,
        'pricing_sha256': execute.digest(contract['protocol']['pricing'])}, 'seal_sha256')
    permit_identity = {'protocol_family': 'physical-final-scale-seal-v1', 'role': 'final_eval_only',
        'freeze_sha256': contract['freeze_sha256'], 'seal_sha256': sealed['seal_sha256'],
        'owner_sha256': 'f'*64, 'test_access_count': 1, 'destination': 'synthetic-private-destination'}
    permit = record(dict(permit_identity, stage='access_begun_before_source_read', began_at_utc=stamp), 'permit_sha256')
    all_rows = [{'id': f'gsm8k:test:{index:05d}', 'source_index': index, 'prompt': f'INVENTED input {index}',
        'gold_answer': '7', 'source_split': 'test', 'role': 'final_eval_only', 'training_eligible': False}
        for index in contract['protocol']['dataset']['indices']]
    binding_body = {'schema_version': 1, 'role': 'final_eval_only', 'freeze_sha256': contract['freeze_sha256'],
        'source_bundle_sha256': execute.digest(sources), 'full_source_sha256': execute.digest('INVENTED full source'),
        'sample_sha256': execute.digest('INVENTED sample bytes'), 'questions': [{
            'id': row['id'], 'source_index': row['source_index'], 'gold_answer': row['gold_answer'],
            'input_sha256': loader.question_input_hash(row, contract)} for row in all_rows]}
    binding = record(binding_body, 'binding_sha256')
    dataset = record(dict(permit_identity, permit_sha256=permit['permit_sha256'],
        **{key: binding[key] for key in ('full_source_sha256', 'sample_sha256', 'binding_sha256')},
        population_count=1319, sample_count=count, indices_sha256=contract['protocol']['dataset']['indices_sha256'],
        input_hash_convention=loader.INPUT_HASH_CONVENTION), 'receipt_sha256')
    authorization = execute.authorization_bundle(sealed, permit, dataset, adapter_path='fixturebundle/adapter',
        model_config_descriptor={'volume_path': 'fixturebundle/model/config.json', 'sha256': execute.MODEL_CONFIG_SHA256, 'bytes': 1000})
    shard = next(s for s in contract['protocol']['shards'] if s['id'] == shard_id)
    payload = execute.make_payload(authorization, binding, all_rows[shard['start']:shard['stop']], checkpoint=checkpoint, shard_id=shard_id)
    desc = execute.describe_input(payload, authorization, volume_path=f'fixturebundle/inputs/{checkpoint}-{shard_id}-a0.json',
        checkpoint=checkpoint, shard_id=shard_id)
    intent = execute.build_intent(sealed, desc, run_id=f'fixture-{checkpoint}-{shard_id}-a0', checkpoint=checkpoint, shard_id=shard_id)
    return authorization, payload, desc, intent


def raw_batch(intent, launch, payload, start, *, counts=None, failed=False):
    stop = min(start+8, intent['stop']); rows = payload['rows'][start-intent['start']:stop-intent['start']]
    counts = [10]*len(rows) if counts is None else counts
    eligible = sum(n <= 1536 for n in counts)
    value = {key: intent[key] for key in receipts.IDENTITY_FIELDS}
    value.update(call_id=launch['call_id'], launch_sha256=launch['launch_sha256'], start=start, stop=stop,
        count=len(rows), question_ids=[row['id'] for row in rows], input_tokens=counts,
        generated_ids=[] if failed else [[77, 100257] for _ in range(eligible)],
        generation_elapsed_seconds=.5 if eligible else 0, eos_token_ids=[100257], generation_failed=failed)
    return value


class ExecutionTests(unittest.TestCase):
    def test_pure_preflight_and_shared_deterministic_launch(self):
        authorization, payload, desc, intent = fixture()
        with patch('builtins.open', side_effect=AssertionError('Metadata functions must not perform I/O')):
            execute.validate_sealed_metadata(authorization['sealed'])
            execute.validate_inputs(intent, authorization, payload)
            left = execute.launch_receipt(intent, 'fc-provider-known')
            right = execute.launch_receipt(copy.deepcopy(intent), 'fc-provider-known')
        self.assertEqual(left, right)
        self.assertEqual(execute.remote_directory(intent), 'fixturebundle/attempts/'+intent['run_id'])
        self.assertEqual(desc['bytes'], len(execute.payload_bytes(payload)))

    def test_preaccess_missing_roles_and_portable_paths_rejected(self):
        authorization, _, _, _ = fixture()
        sealed = copy.deepcopy(authorization['sealed']); sealed['contract']['protocol']['source_roles']['granite_executor'].remove('modal_final_scale.py')
        with self.assertRaises(ValueError): execute.validate_sealed_metadata(sealed)
        for value in ('../escape', '/absolute', 'bundle/../escape', 'bundle\\file', 'CON/file', 'bundle/file.', 'bundle//file'):
            with self.subTest(path=value), self.assertRaises(ValueError): execute.volume_path(value)

    def test_changed_owner_source_model_payload_or_descriptor_fail_closed(self):
        authorization, payload, desc, intent = fixture()
        for mutate in (lambda a: a['permit'].update(owner_sha256='0'*64),
                lambda a: a['dataset_receipt'].update(sample_sha256='0'*64), lambda a: a.update(adapter_path='../escape')):
            bad = copy.deepcopy(authorization); mutate(bad)
            with self.assertRaises(ValueError): execute.validate_remote_metadata(intent, desc, bad)
        bad = copy.deepcopy(payload); bad['rows'][0]['gold_answer'] = '8'
        with self.assertRaises(ValueError): execute.validate_inputs(intent, authorization, bad)
        bad = copy.deepcopy(desc); bad['bytes'] += 1
        with self.assertRaises(ValueError): execute.validate_remote_metadata(intent, bad, authorization)

    def test_real_tail7_and_actual_eligible_subset_timing(self):
        authorization, payload, _, intent = fixture(1319, shard_id='shard003')
        launch = execute.launch_receipt(intent, 'fc-tail7')
        raw = raw_batch(intent, launch, payload, 1312, counts=[1537]+[1536]*6)
        result = execute.derive_raw_batch(intent, launch, raw, payload['binding'], lambda _: '#### 7')
        self.assertEqual(result['count'], 7)
        self.assertEqual(result['rows'][0]['outcome'], 'input_limit')
        self.assertEqual(sum(row['elapsed_seconds'] for row in result['rows']), .5)
        self.assertEqual(len({row['id'] for row in result['rows']}), 7)
        receipts.validate_batch(authorization['sealed']['contract'], payload['binding'], result)

    def test_raw_tokens_preserved_and_truncation_not_rewritten(self):
        _, payload, _, intent = fixture()
        launch = execute.launch_receipt(intent, 'fc-raw')
        raw = raw_batch(intent, launch, payload, 0)
        raw['generated_ids'][0] = [77]*512; before = copy.deepcopy(raw)
        result = execute.derive_raw_batch(intent, launch, raw, payload['binding'], lambda _: '#### 7')
        self.assertEqual(raw, before); self.assertTrue(result['rows'][0]['truncated'])
        self.assertEqual(result['rows'][0]['generated_tokens'], 512)
        self.assertEqual(result['rows'][1]['generated_tokens'], 2)
        self.assertNotEqual(result['raw_batch_sha256'], result['rows_sha256'])

    def test_failed_attempted_subset_retained_input_limit_separate(self):
        _, payload, _, intent = fixture()
        launch = execute.launch_receipt(intent, 'fc-failed')
        raw = raw_batch(intent, launch, payload, 0, counts=[2000]+[10]*7, failed=True)
        result = execute.derive_raw_batch(intent, launch, raw, payload['binding'], lambda _: self.fail('Failed generation must not decode'))
        self.assertEqual([row['outcome'] for row in result['rows']], ['input_limit']+['failed']*7)
        self.assertEqual(sum(row['elapsed_seconds'] for row in result['rows']), .5)

    def test_raw_mutations_and_unknown_binding_rejected_without_generation(self):
        _, payload, _, intent = fixture(); launch = execute.launch_receipt(intent, 'fc-malformed')
        for field, value in (('input_tokens', [True]*8), ('eos_token_ids', []), ('generated_ids', [[100352]]*8),
                ('question_ids', ['wrong']*8), ('generation_elapsed_seconds', float('inf'))):
            raw = raw_batch(intent, launch, payload, 0); raw[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                execute.derive_raw_batch(intent, launch, raw, payload['binding'], lambda _: '#### 7')

    def test_worker_candidate_never_authorizes_recovery_and_pending_raw_blocks_it(self):
        authorization, payload, _, intent = fixture(); launch = execute.launch_receipt(intent, 'fc-old')
        batch = execute.derive_raw_batch(intent, launch, raw_batch(intent, launch, payload, 0), payload['binding'], lambda _: '#### 7')
        candidate = execute.terminal_receipt(intent, launch, [batch], [], 'failed')
        previous = {'launch': launch, 'terminal': candidate, 'batches': [batch]}
        with self.assertRaises(ValueError): execute.make_payload(authorization, payload['binding'], payload['rows'],
            checkpoint='base', shard_id='shard000', prior_attempts=[previous])
        confirmed = execute.terminal_receipt(intent, launch, [batch], [], 'failed', confirmed_terminal=True)
        previous['terminal'] = confirmed
        resumed = execute.make_payload(authorization, payload['binding'], payload['rows'], checkpoint='base', shard_id='shard000', prior_attempts=[previous])
        desc = execute.describe_input(resumed, authorization, volume_path='fixturebundle/inputs/resume.json', checkpoint='base', shard_id='shard000')
        recovery = {key: desc[key] for key in ('parent_call_id', 'prefix_sha256', 'retained_count')}
        child = execute.build_intent(authorization['sealed'], desc, run_id='fixture-resume', checkpoint='base', shard_id='shard000', recovery=recovery)
        self.assertEqual(execute.validate_inputs(child, authorization, resumed)['prefix_rows'], batch['rows'])
        previous['terminal'] = execute.terminal_receipt(intent, launch, [batch], [], 'failed', confirmed_terminal=True,
            raw_pending=True, raw_pending_start=8, raw_pending_sha256='0'*64)
        with self.assertRaisesRegex(ValueError, 'raw outcomes'):
            execute.make_payload(authorization, payload['binding'], payload['rows'], checkpoint='base', shard_id='shard000', prior_attempts=[previous])

    def test_full_prefix_local_attestation_preserves_failed_terminal_without_new_call(self):
        authorization, payload, _, intent = fixture(1319, shard_id='shard003')
        launch = execute.launch_receipt(intent, 'fc-full-before-return-failure')
        batches = [execute.derive_raw_batch(intent, launch, raw_batch(intent, launch, payload, start),
            payload['binding'], lambda _: '#### 7') for start in range(intent['start'], intent['stop'], 8)]
        terminal = execute.terminal_receipt(intent, launch, batches, [], 'failed', confirmed_terminal=True)
        original = copy.deepcopy(terminal)
        proof = {'call_id': launch['call_id'], 'confirmed_terminal': True, 'kind': 'failed',
            'observed_at_utc': '2026-11-03T23:00:00+00:00'}
        hashes = {str(batch['start']): batch['raw_batch_sha256'] for batch in batches}
        reconciled = execute.reconcile_full_prefix(intent, authorization, payload, launch, batches, terminal,
            provider_terminal_proof=proof, raw_batch_hashes=hashes)
        self.assertEqual(terminal, original)
        self.assertEqual(reconciled['completed_attempt']['terminal']['stage'], 'completed')
        self.assertTrue(reconciled['evidence']['no_generation_replayed'])
        self.assertFalse(reconciled['execution_authorized_by_this_helper'])
        for mutation in (dict(proof, confirmed_terminal=False), dict(proof, call_id='fc-other')):
            with self.assertRaises(ValueError):
                execute.reconcile_full_prefix(intent, authorization, payload, launch, batches, terminal,
                    provider_terminal_proof=mutation, raw_batch_hashes=hashes)
        with self.assertRaises(ValueError):
            execute.reconcile_full_prefix(intent, authorization, payload, launch, batches, terminal,
                provider_terminal_proof=proof, raw_batch_hashes=dict(hashes, orphan='0'*64))
        partial = execute.terminal_receipt(intent, launch, batches[:-1], [], 'failed', confirmed_terminal=True)
        with self.assertRaises(ValueError):
            execute.reconcile_full_prefix(intent, authorization, payload, launch, batches[:-1], partial,
                provider_terminal_proof=proof, raw_batch_hashes={str(b['start']): b['raw_batch_sha256'] for b in batches[:-1]})

    def test_terminal_constructor_rejects_double_counted_or_unbound_prefix(self):
        _, payload, _, intent = fixture(); launch = execute.launch_receipt(intent, 'fc-prefix-error')
        batch = execute.derive_raw_batch(intent, launch, raw_batch(intent, launch, payload, 0), payload['binding'], lambda _: '#### 7')
        with self.assertRaisesRegex(ValueError, 'immutable pre-spawn evidence'):
            execute.terminal_receipt(intent, launch, [], batch['rows'], 'failed')


if __name__ == '__main__': unittest.main()
