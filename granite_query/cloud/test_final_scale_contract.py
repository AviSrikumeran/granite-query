"""Synthetic-only contract fixtures. No official source is opened or fetched."""
import copy
from decimal import Decimal
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cloud import final_scale_contract as scale


def full_sources():
    roles = {role: [name] for role, name in zip(scale.SOURCE_ROLES, (
        'final_scale_contract.py', 'final_scale_receipts.py', 'fixture_loader.py',
        'fixture_granite.py', 'fixture_teacher.py', 'fixture_checkpoint.py',
        'fixture_image.py', 'fixture_scoring.py', 'fixture_paired.py'))}
    hashes = {name: hashlib.sha256(('synthetic:'+name).encode()).hexdigest()
              for names in roles.values() for name in names}
    return hashes, roles


def complete_contract(count=1000):
    hashes, roles = full_sources()
    selected = {'model': scale.MODEL, 'revision': scale.REVISION, 'checkpoint_id': 'synthetic-chosen',
        'adapter_inventory_sha256': 'a'*64, 'development_evidence_sha256': 'b'*64}
    return scale.build_contract(count, source_hashes=hashes, source_roles=roles, selected=selected)


def calibration(contract, *, base=500, chosen=400):
    return scale.calibration(contract, base_generation_seconds=base, chosen_generation_seconds=chosen,
        evidence_hashes={'base': 'c'*64, 'chosen': 'd'*64})


def reviewed(contract):
    observation = '2026-11-03T22:59:00+00:00'
    funding = {'observed_at_utc': {'modal': observation, 'deepseek': observation},
        'new_paid_work_allowed': {'modal': True, 'deepseek': True},
        'limits_usd': {'modal': '30', 'deepseek': '20'},
        'spent_usd': {'modal': '0', 'deepseek': '0'},
        'reserved_usd': {'modal': '0', 'deepseek': '0'}}
    measured = calibration(contract)
    record = scale.review_template(contract)
    record.update(reviewed=True, no_tuning_after_access_acknowledged=True,
        complete_denominator_acknowledged=True, all_source_roles_reviewed=True,
        calibration_sha256=measured['calibration_sha256'], funding_snapshot_sha256=scale.digest(funding))
    return record, measured, funding


class ScaleContractTests(unittest.TestCase):
    def approve(self, contract, record, measured, funding):
        return scale.validate_review(contract, record,
            actual_source_hashes=contract['protocol']['source_hashes'], calibration_record=measured,
            funding_snapshot=funding, as_of_utc='2026-11-03T23:00:00+00:00',
            actual_pricing_sha256=scale.digest(contract['protocol']['pricing']))

    def test_contract_creation_has_no_io_or_execution_side_effect(self):
        with patch('builtins.open', side_effect=AssertionError('No source access allowed')):
            contract = scale.build_contract()
            scale.validate(contract)
            ids = scale.expected_ids(contract)
            record = scale.review_template(contract)
        self.assertEqual(len(ids), 1000)
        self.assertEqual(contract['stage'], 'contract_only_not_authorized')
        self.assertFalse(contract['official_test_accessed'])
        self.assertFalse(contract['execution_ready'])
        self.assertIsNone(contract['protocol']['selected'])
        self.assertFalse(record['reviewed'])
        with self.assertRaises(ValueError):
            scale.validate_sources(contract, {}, complete=True)

    def test_seeded1000_is_reproducible_and_full_is_census(self):
        first = scale.build_contract(1000)
        self.assertEqual(first, scale.build_contract(1000))
        different = scale.build_contract(1000, seed=123)
        self.assertNotEqual(first['protocol']['dataset']['indices'], different['protocol']['dataset']['indices'])
        indices = first['protocol']['dataset']['indices']
        self.assertEqual(indices, sorted(set(indices)))
        self.assertEqual(len(indices), 1000)
        self.assertTrue(all(0 <= index < 1319 for index in indices))
        whole = scale.build_contract(1319)
        self.assertEqual(whole['protocol']['dataset']['indices'], list(range(1319)))
        self.assertTrue(whole['protocol']['dataset']['full_test_evaluation'])

    def test_disjoint_global_shards_and_legitimate_tail7(self):
        for count, sizes in ((1000, [368, 368, 264]), (1319, [368, 368, 368, 215])):
            with self.subTest(count=count):
                contract = scale.build_contract(count)
                shards = contract['protocol']['shards']
                self.assertEqual([s['stop']-s['start'] for s in shards], sizes)
                self.assertEqual([i for s in shards for i in s['indices']], contract['protocol']['dataset']['indices'])
                covered = []
                batch_sizes = []
                for shard in shards:
                    expected = scale.expected_ids(contract, shard['id'])
                    self.assertEqual(scale.digest(expected), shard['question_ids_sha256'])
                    for batch in scale.batches(contract, shard['id']):
                        covered.extend(range(batch['start'], batch['stop']))
                        batch_sizes.append(batch['count'])
                        self.assertEqual(batch['stop']-batch['start'], batch['count'])
                self.assertEqual(covered, list(range(count)))
                self.assertEqual(batch_sizes[-1], 7 if count == 1319 else 8)
                self.assertTrue(all(n == 8 for n in batch_sizes[:-1]))

    def test_bad_targets_booleans_seed_and_shard_bounds_rejected(self):
        for count in (True, 256, 999, 1001, 1318, 1320, '1000', 1000.0):
            with self.subTest(count=count), self.assertRaises(ValueError):
                scale.build_contract(count)
        for size in (True, 0, 7, 367, 376, '368'):
            with self.subTest(size=size), self.assertRaises(ValueError):
                scale.build_contract(1000, max_shard_questions=size)
        for seed in (True, -1, 2**32, '42'):
            with self.subTest(seed=seed), self.assertRaises(ValueError):
                scale.build_contract(1000, seed=seed)

    def test_rehashed_policy_source_and_coverage_tampering_rejected(self):
        mutations = (
            lambda p: p['dataset'].update(repository='other/source'),
            lambda p: p['shards'][1].update(start=0),
            lambda p: p['shards'][-1]['batch_counts'].__setitem__(-1, 8),
            lambda p: p['policies'].update(filter_failures=True),
            lambda p: p['inference'].update(max_new_tokens=4096),
            lambda p: p['bounds'].update(modal_compute_bundle_usd='0.01'),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                contract = scale.build_contract(1319)
                mutate(contract['protocol'])
                contract['freeze_sha256'] = scale.digest(contract['protocol'])
                with self.assertRaises(ValueError):
                    scale.validate(contract)

    def test_total_resource_and_token_bounds_include_recovery(self):
        for count, compute, teacher in ((1000, '10.50', '5'), (1319, '14.00', '7')):
            contract = scale.build_contract(count)
            bounds = contract['protocol']['bounds']
            self.assertEqual(Decimal(bounds['modal_compute_bundle_usd']), Decimal(compute))
            self.assertEqual(Decimal(bounds['teacher_reservation_usd']), Decimal(teacher))
            self.assertGreaterEqual(Decimal(bounds['gpu_call_reservation_usd']), Decimal(bounds['per_gpu_call_resource_bound_usd']))
            self.assertGreaterEqual(Decimal(bounds['modal_bundle_including_recovery_usd']),
                Decimal(bounds['all_gpu_call_resource_bound_including_recovery_usd']))
            self.assertGreaterEqual(Decimal(bounds['teacher_reservation_usd']), Decimal(bounds['teacher_peak_token_bound_usd']))
            self.assertEqual(bounds['teacher_input_tokens_bound'], 2000*count)
            self.assertEqual(bounds['all_roles_output_tokens_bound'], 3*512*count)
            self.assertEqual(contract['protocol']['policies']['complete_denominator'], count)
            self.assertFalse(contract['protocol']['policies']['filter_failures'])
            self.assertEqual(contract['protocol']['model_roles']['teacher']['max_attempts'], count)

    def test_source_bundle_and_selected_identity_gates(self):
        contract = complete_contract()
        sources = contract['protocol']['source_hashes']
        self.assertEqual(scale.validate_sources(contract, sources), scale.digest(sources))
        changed = dict(sources, **{'fixture_image.py': 'e'*64})
        with self.assertRaises(ValueError):
            scale.validate_sources(contract, changed)
        record, measured, funding = reviewed(contract)
        record['selected_sha256'] = '0'*64
        with self.assertRaises(ValueError):
            self.approve(contract, record, measured, funding)
        for bad in ('../private.py', 'fixture..py', 'secret.txt'):
            with self.subTest(name=bad), self.assertRaises(ValueError):
                scale.build_contract(source_hashes={bad: 'a'*64})

    def test_whole_review_is_explicit_and_never_execution_authorization(self):
        contract = complete_contract(1319)
        record, measured, funding = reviewed(contract)
        result = self.approve(contract, record, measured, funding)
        self.assertEqual(result['stage'], 'review_record_validated_not_execution_authorized')
        self.assertFalse(result['official_test_accessed'])
        self.assertFalse(result['paid_work_launched'])
        record['reviewed'] = False
        with self.assertRaises(ValueError):
            self.approve(contract, record, measured, funding)

    def test_calibration200_must_fit_before_review(self):
        contract = complete_contract()
        record, _, funding = reviewed(contract)
        infeasible = calibration(contract, base=1000)
        self.assertFalse(infeasible['runtime_feasible'])
        record['calibration_sha256'] = infeasible['calibration_sha256']
        with self.assertRaises(ValueError):
            self.approve(contract, record, infeasible, funding)
        measured = calibration(contract)
        measured['development_count'] = 64
        with self.assertRaises(ValueError):
            scale.validate_calibration(contract, measured)
        for seconds in (True, 0, -1, float('nan'), float('inf')):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                calibration(contract, base=seconds)

    def test_underfunded_recovery_stale_and_increased_ceiling_refused(self):
        contract = complete_contract(1319)
        mutations = (
            lambda f: f['spent_usd'].update(modal='10'),
            lambda f: f['reserved_usd'].update(modal='10'),
            lambda f: f['spent_usd'].update(deepseek='14'),
            lambda f: f['limits_usd'].update(modal='31'),
            lambda f: f['observed_at_utc'].update(modal='2026-11-03T22:00:00+00:00'),
            lambda f: f['observed_at_utc'].update(modal='2026-11-03T23:01:00+00:00'),
            lambda f: f['new_paid_work_allowed'].update(deepseek=False),
        )
        for mutate in mutations:
            record, measured, funding = reviewed(contract)
            mutate(funding)
            record['funding_snapshot_sha256'] = scale.digest(funding)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                self.approve(contract, record, measured, funding)
        record, measured, funding = reviewed(contract)
        record['budget_envelope']['modal_recovery_allowance_usd'] = '0'
        with self.assertRaises(ValueError):
            self.approve(contract, record, measured, funding)

    def test_protected5_cannot_silently_be_reallocated(self):
        contract = complete_contract()
        record, measured, funding = reviewed(contract)
        record['budget_envelope']['additional_protected_modal_usd'] = '0'
        with self.assertRaises(ValueError):
            self.approve(contract, record, measured, funding)
        record['final_stage_protected5_allocation_reviewed'] = True
        self.assertEqual(self.approve(contract, record, measured, funding)['question_count'], 1000)
        record['final_stage_protected5_allocation_reviewed'] = 1
        with self.assertRaises(ValueError):
            self.approve(contract, record, measured, funding)

    def test_unknown_pending_sources_cannot_be_approved(self):
        contract = scale.build_contract()
        record = scale.review_template(contract)
        record['reviewed'] = True
        with self.assertRaises(ValueError):
            scale.validate_sources(contract, {}, complete=True)
        self.assertIsNone(contract['protocol']['selected'])


if __name__ == '__main__':
    unittest.main()
