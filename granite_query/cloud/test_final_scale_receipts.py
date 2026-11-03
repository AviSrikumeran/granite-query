"""Invented metadata/outcomes only; never reads a dataset or provider state."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cloud import final_scale_contract as contract_api
from cloud import final_scale_receipts as receipts


def hash_text(value):
    return hashlib.sha256(value.encode()).hexdigest()


def seal(value, field):
    result = dict(value)
    result[field] = receipts.digest({k: v for k, v in result.items() if k != field})
    return result


def fixture(count=1000, *, chosen=True):
    proposal = contract_api.build_contract(count)
    selected = dict(proposal['protocol']['base'], checkpoint_id='fixture-selected',
        adapter_inventory_sha256=hash_text('fake adapter inventory'),
        development_evidence_sha256=hash_text('fake development evidence')) if chosen else None
    names = ('final_scale_contract.py', 'final_scale_receipts.py', 'fixture_loader.py',
        'fixture_granite.py', 'fixture_teacher.py', 'fixture_checkpoint.py',
        'fixture_image.py', 'fixture_scoring.py', 'fixture_paired.py')
    roles = {role: [name] for role, name in zip(contract_api.SOURCE_ROLES, names)}
    sources = {name: hash_text('INVENTED source '+name) for name in names}
    contract = contract_api.build_contract(count, source_hashes=sources, source_roles=roles, selected=selected)
    ids = contract_api.expected_ids(contract)
    binding = seal({'schema_version': 1, 'role': 'final_eval_only', 'freeze_sha256': contract['freeze_sha256'],
        'source_bundle_sha256': receipts.digest(sources), 'full_source_sha256': hash_text('INVENTED full source bytes'),
        'sample_sha256': hash_text('INVENTED sample bytes '+str(count)),
        'questions': [{'id': identifier, 'source_index': index, 'gold_answer': '7',
            'input_sha256': hash_text('INVENTED model input '+identifier)}
            for identifier, index in zip(ids, contract['protocol']['dataset']['indices'])]}, 'binding_sha256')
    return contract, binding


def identity(contract, binding, checkpoint, shard_id):
    p = contract['protocol']
    return {**{key: binding[key] for key in ('role', 'freeze_sha256', 'source_bundle_sha256',
                'full_source_sha256', 'sample_sha256', 'binding_sha256')},
        'checkpoint': checkpoint, 'checkpoint_sha256': receipts.digest(p['base'] if checkpoint == 'base' else p['selected']),
        'model': p['base']['model'], 'revision': p['base']['revision'], 'shard_id': shard_id}


def outcome(binding, position, checkpoint='base', *, special=False):
    question = binding['questions'][position]
    row = dict(question, global_position=position, outcome='generated',
        response='PRIVATE_FIXTURE_REASONING\n#### 7', truncated=False, generated_tokens=6,
        elapsed_seconds=.01, failure_type=None)
    if special:
        if position == 0:
            row['truncated'] = True
        elif position == 1:
            row.update(outcome='input_limit', response='', generated_tokens=0,
                elapsed_seconds=0, failure_type='input_limit')
        elif position == 2:
            # A failed response ending in the gold number must still be wrong.
            row.update(outcome='failed', failure_type='generation_error')
        elif position == 3 and checkpoint == 'base':
            row['response'] = 'PRIVATE_FIXTURE_WRONG\n#### 9'
    return row


def attempt(contract, binding, checkpoint, shard_id, *, call_id=None, prefix=None,
            parent=None, starts=None, stage='completed', special=False):
    prefix = [] if prefix is None else prefix
    ident = identity(contract, binding, checkpoint, shard_id)
    call_id = call_id or 'fc-fixture-'+checkpoint+'-'+shard_id
    launch = seal(dict(ident, call_id=call_id, parent_call_id=parent,
        prefix_sha256=receipts.digest(prefix)), 'launch_sha256')
    batches = []
    for descriptor in contract_api.batches(contract, shard_id):
        if starts is not None and descriptor['start'] not in starts:
            continue
        rows = [outcome(binding, position, checkpoint, special=special)
            for position in range(descriptor['start'], descriptor['stop'])]
        batches.append(seal(dict(ident, call_id=call_id, launch_sha256=launch['launch_sha256'],
            start=descriptor['start'], stop=descriptor['stop'], count=descriptor['count'], rows=rows,
            question_ids_sha256=descriptor['ids_sha256'], rows_sha256=receipts.digest(rows)), 'batch_sha256'))
    retained = prefix+[row for batch in batches for row in batch['rows']]
    terminal = None if stage is None else seal(dict(ident, call_id=call_id,
        launch_sha256=launch['launch_sha256'], confirmed_terminal=True, stage=stage,
        committed_batches_sha256=receipts.digest([batch['batch_sha256'] for batch in batches]),
        output_prefix_sha256=receipts.digest(retained), retained_count=len(retained)), 'terminal_sha256')
    return {'launch': launch, 'terminal': terminal, 'batches': batches}


def reseal_attempt(value):
    """Update genuine outer checksums so tests target semantic validation."""
    value['launch'] = seal(value['launch'], 'launch_sha256')
    for index, batch in enumerate(value['batches']):
        batch['launch_sha256'] = value['launch']['launch_sha256']
        batch['rows_sha256'] = receipts.digest(batch['rows'])
        value['batches'][index] = seal(batch, 'batch_sha256')
    if value['terminal'] is not None:
        value['terminal']['launch_sha256'] = value['launch']['launch_sha256']
        value['terminal']['committed_batches_sha256'] = receipts.digest([b['batch_sha256'] for b in value['batches']])
        value['terminal'] = seal(value['terminal'], 'terminal_sha256')
    return value


class ScaleReceiptTests(unittest.TestCase):
    def test_pure_metadata_api_does_no_io_and_rejects_incomplete_default_proposal(self):
        contract, binding = fixture()
        with patch('builtins.open', side_effect=AssertionError('No I/O in receipt APIs')):
            self.assertEqual(receipts.validate_binding(contract, binding)['count'], 1000)
            public = receipts.aggregate(contract, binding, {}, paired_resamples=100)
        self.assertIsNone(public['checkpoints']['base']['metrics'])
        proposal = contract_api.build_contract()
        with self.assertRaises(ValueError): receipts.validate_binding(proposal, binding)
        contract, binding = fixture(chosen=False)
        with self.assertRaisesRegex(ValueError, 'chosen checkpoint'):
            receipts.validate_binding(contract, binding)

    def test_full1319_tail7_is_real_unpadded_and_source_ordered(self):
        contract, binding = fixture(1319)
        last = contract['protocol']['shards'][-1]['id']
        value = attempt(contract, binding, 'base', last)
        tail = value['batches'][-1]
        self.assertEqual((tail['start'], tail['stop'], tail['count']), (1312, 1319, 7))
        self.assertEqual(len(receipts.validate_batch(contract, binding, tail)), 7)
        changed = copy.deepcopy(tail)
        changed['rows'].append(copy.deepcopy(changed['rows'][-1])); changed['count'] = 8
        changed['rows_sha256'] = receipts.digest(changed['rows']); changed = seal(changed, 'batch_sha256')
        with self.assertRaises(ValueError): receipts.validate_batch(contract, binding, changed)

    def test_batch_source_model_role_and_input_hashes_fail_closed(self):
        contract, binding = fixture()
        good = attempt(contract, binding, 'base', 'shard000')['batches'][0]
        for field, value in (('role', 'training_eligible'), ('freeze_sha256', '0'*64),
                ('source_bundle_sha256', '0'*64), ('full_source_sha256', '0'*64),
                ('sample_sha256', '0'*64), ('binding_sha256', '0'*64),
                ('checkpoint_sha256', '0'*64), ('model', 'another-model'),
                ('revision', 'another-revision'), ('shard_id', 'shard001')):
            with self.subTest(field=field):
                bad = seal(dict(good, **{field: value}), 'batch_sha256')
                with self.assertRaises(ValueError): receipts.validate_batch(contract, binding, bad)
        bad = copy.deepcopy(good); bad['rows'][0]['input_sha256'] = '0'*64
        bad['rows_sha256'] = receipts.digest(bad['rows']); bad = seal(bad, 'batch_sha256')
        with self.assertRaises(ValueError): receipts.validate_batch(contract, binding, bad)
        bad = copy.deepcopy(good); bad['rows'][0]['response'] = 'tampered after checksum'
        with self.assertRaises(ValueError): receipts.validate_batch(contract, binding, bad)

    def test_sample_binding_has_complete_finite_references_and_frozen_indices(self):
        contract, binding = fixture()
        self.assertEqual(receipts.validate_binding(contract, binding)['count'], 1000)
        for mutation in ('reorder', 'missing', 'duplicate', 'boolindex', 'nanreference', 'role'):
            with self.subTest(mutation=mutation):
                bad = copy.deepcopy(binding)
                if mutation == 'reorder': bad['questions'][0], bad['questions'][1] = bad['questions'][1], bad['questions'][0]
                if mutation == 'missing': bad['questions'].pop()
                if mutation == 'duplicate': bad['questions'][1] = dict(bad['questions'][0])
                if mutation == 'boolindex': bad['questions'][0]['source_index'] = True
                if mutation == 'nanreference': bad['questions'][0]['gold_answer'] = 'NaN'
                if mutation == 'role': bad['role'] = 'training_eligible'
                bad = seal(bad, 'binding_sha256')
                with self.assertRaises(ValueError): receipts.validate_binding(contract, bad)

    def test_terminal_prefix_recovery_appends_only_missing_batches(self):
        contract, binding = fixture()
        first = attempt(contract, binding, 'base', 'shard000', call_id='fc-first', starts=[0, 8], stage='timed_out')
        prefix = receipts.recover_prefix(contract, binding, 'base', 'shard000', [first])
        self.assertEqual(prefix['next_position'], 16); self.assertTrue(prefix['can_resume'])
        remaining = [b['start'] for b in contract_api.batches(contract, 'shard000') if b['start'] >= 16]
        second = attempt(contract, binding, 'base', 'shard000', call_id='fc-second',
            parent='fc-first', prefix=prefix['rows'], starts=remaining)
        completed = receipts.recover_prefix(contract, binding, 'base', 'shard000', [first, second])
        self.assertEqual(completed['retained_count'], 368); self.assertFalse(completed['can_resume'])
        self.assertEqual(completed['rows'][:16], prefix['rows'])
        public = receipts.aggregate(contract, binding, {'base': {'shard000': [first, second]}}, paired_resamples=100)
        self.assertIsNone(public['checkpoints']['base']['metrics'])
        self.assertEqual(public['checkpoints']['base']['retained_count'], 368)

    def test_ambiguous_conflicting_out_of_order_and_cross_shard_recovery_rejected(self):
        contract, binding = fixture()
        first = attempt(contract, binding, 'base', 'shard000', starts=[0, 8], stage='timed_out')
        variants = []
        missing = copy.deepcopy(first); missing['terminal'] = None; variants.append(missing)
        unknown = copy.deepcopy(first); unknown['terminal']['stage'] = 'unknown'; variants.append(reseal_attempt(unknown))
        mismatch = copy.deepcopy(first); mismatch['terminal']['call_id'] = 'fc-other'; variants.append(reseal_attempt(mismatch))
        uncertain = copy.deepcopy(first); uncertain['terminal']['confirmed_terminal'] = False; variants.append(reseal_attempt(uncertain))
        reversed_batches = copy.deepcopy(first); reversed_batches['batches'].reverse(); variants.append(reseal_attempt(reversed_batches))
        duplicate = copy.deepcopy(first); duplicate['batches'].append(copy.deepcopy(duplicate['batches'][-1])); variants.append(reseal_attempt(duplicate))
        hole = copy.deepcopy(first); hole['batches'].pop(0); variants.append(reseal_attempt(hole))
        for number, bad in enumerate(variants):
            with self.subTest(number=number):
                with self.assertRaises(ValueError): receipts.recover_prefix(contract, binding, 'base', 'shard000', [bad])
        with self.assertRaises(ValueError): receipts.recover_prefix(contract, binding, 'base', 'shard001', [first])
        with self.assertRaises(ValueError): receipts.recover_prefix(contract, binding, 'base', 'shard000', [])

    def test_live_unknown_terminal_and_failure_states_never_have_metrics(self):
        contract, binding = fixture()
        empty = receipts.aggregate(contract, binding, {}, paired_resamples=100)
        self.assertIsNone(empty['checkpoints']['base']['metrics']); self.assertIsNone(empty['chosen_vs_base'])
        live = attempt(contract, binding, 'base', 'shard000', starts=[0], stage=None)
        public = receipts.aggregate(contract, binding, {'base': {'shard000': [live]}}, paired_resamples=100)
        self.assertEqual(public['checkpoints']['base']['status'], 'running')
        self.assertIsNone(public['checkpoints']['base']['metrics'])
        failed = attempt(contract, binding, 'base', 'shard000', starts=[], stage='failed')
        public = receipts.aggregate(contract, binding, {'base': {'shard000': [failed]}}, paired_resamples=100)
        self.assertEqual(public['checkpoints']['base']['status'], 'incomplete_terminal')
        self.assertIsNone(public['checkpoints']['base']['metrics'])

    def test_failed_after_full_commit_requires_local_review_without_paid_rerun(self):
        contract, binding = fixture()
        failed = attempt(contract, binding, 'base', 'shard000', stage='failed')
        prefix = receipts.recover_prefix(contract, binding, 'base', 'shard000', [failed])
        self.assertEqual(prefix['retained_count'], 368)
        self.assertEqual(prefix['status'], 'failed'); self.assertFalse(prefix['can_resume'])
        public = receipts.aggregate(contract, binding, {'base': {'shard000': [failed]}}, paired_resamples=100)
        self.assertIsNone(public['checkpoints']['base']['metrics'])
        child = attempt(contract, binding, 'base', 'shard000', call_id='fc-unnecessary-rerun',
            parent=prefix['last_call_id'], prefix=prefix['rows'], starts=[])
        with self.assertRaisesRegex(ValueError, 'no remaining positions'):
            receipts.recover_prefix(contract, binding, 'base', 'shard000', [failed, child])

    def test_whole1000_denominator_keeps_wrong_truncated_input_limit_and_failed(self):
        contract, binding = fixture()
        all_attempts = {checkpoint: {shard['id']: [attempt(contract, binding, checkpoint, shard['id'], special=True)]
            for shard in contract['protocol']['shards']} for checkpoint in ('base', 'chosen')}
        public = receipts.aggregate(contract, binding, all_attempts, paired_resamples=100)
        base, chosen = (public['checkpoints'][key]['metrics'] for key in ('base', 'chosen'))
        self.assertEqual((base['count'], base['numeric_correct'], chosen['numeric_correct']), (1000, 996, 997))
        self.assertEqual((base['failed'], base['input_limit'], base['truncated']), (1, 1, 1))
        self.assertEqual(public['chosen_vs_base']['count'], 1000)
        self.assertEqual((public['chosen_vs_base']['corrected'], public['chosen_vs_base']['regressed']), (1, 0))
        self.assertAlmostEqual(public['chosen_vs_base']['difference_percentage_points'], .1)
        self.assertFalse(public['execution_authorized_by_this_module'])
        exported = json.dumps(public)
        self.assertNotIn('PRIVATE_FIXTURE', exported); self.assertNotIn('gsm8k:test:', exported)
        self.assertNotIn('fc-fixture-', exported)

    def test_complete1319_base_uses_full_denominator_and_real_tail(self):
        contract, binding = fixture(1319)
        by_shard = {s['id']: [attempt(contract, binding, 'base', s['id'])] for s in contract['protocol']['shards']}
        public = receipts.aggregate(contract, binding, {'base': by_shard}, paired_resamples=100)
        self.assertTrue(public['full_test_evaluation'])
        self.assertEqual(public['checkpoints']['base']['metrics']['count'], 1319)
        self.assertEqual(public['checkpoints']['base']['metrics']['numeric_correct'], 1319)
        self.assertIsNone(public['chosen_vs_base'])

    def test_chosen_pending_unknown_checkpoint_and_reused_call_fail_closed(self):
        contract, binding = fixture(chosen=False)
        # Even a base peek is invalid before the selected checkpoint is frozen.
        with self.assertRaises(ValueError): receipts.aggregate(contract, binding, {}, paired_resamples=100)
        with self.assertRaises(ValueError): receipts.aggregate(contract, binding, {'chosen': {'shard000': []}})
        with self.assertRaises(ValueError): receipts.aggregate(contract, binding, {'teacher': {}})
        contract, binding = fixture()
        first = attempt(contract, binding, 'base', 'shard000', call_id='fc-duplicate')
        second = attempt(contract, binding, 'chosen', 'shard000', call_id='fc-duplicate')
        with self.assertRaises(ValueError):
            receipts.aggregate(contract, binding, {'base': {'shard000': [first]}, 'chosen': {'shard000': [second]}})

    def test_terminal_parent_and_global_recovery_allowance_are_enforced(self):
        contract, binding = fixture()
        chains = {}
        for shard_id in ('shard000', 'shard001'):
            shard = next(s for s in contract['protocol']['shards'] if s['id'] == shard_id)
            first = attempt(contract, binding, 'base', shard_id, call_id='fc-old-'+shard_id,
                starts=[shard['start']], stage='failed')
            prefix = receipts.recover_prefix(contract, binding, 'base', shard_id, [first])
            starts = [b['start'] for b in contract_api.batches(contract, shard_id) if b['start'] >= shard['start']+8]
            second = attempt(contract, binding, 'base', shard_id, call_id='fc-new-'+shard_id,
                prefix=prefix['rows'], parent=prefix['last_call_id'], starts=starts)
            chains[shard_id] = [first, second]
        with self.assertRaisesRegex(ValueError, 'Whole bundle'):
            receipts.aggregate(contract, binding, {'base': chains})
        first, second = copy.deepcopy(chains['shard000'])
        first['terminal'] = None
        with self.assertRaises(ValueError): receipts.recover_prefix(contract, binding, 'base', 'shard000', [first, second])
        third = copy.deepcopy(second)
        with self.assertRaisesRegex(ValueError, 'ceiling'):
            receipts.recover_prefix(contract, binding, 'base', 'shard000', chains['shard000']+[third])


if __name__ == '__main__':
    unittest.main()
