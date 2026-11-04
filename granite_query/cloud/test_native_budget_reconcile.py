"""Pure invented receipt DAG/accounting fixtures; no provider or ledger writes."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cloud import native_budget_reconcile as account


NOW = datetime(2026, 11, 4, 3, 0, tzinfo=timezone.utc)


def seal(record, key):
    record[key] = account.digest({k: value for k, value in record.items() if k != key})
    return record


def failed_child(name, parent, design, digit):
    return {'run_id': name, 'service': 'modal', 'status': 'failed', 'reserved_usd': 1.75,
        'native_envelope_parent': parent, 'native_design_sha256': design,
        'native_claim_id': digit * 32, 'native_intent_sha256': digit * 64,
        'native_terminal_sha256': 'f' * 64, 'call_id': 'fc-INVENTED-' + digit}


def source(child, original):
    launch = {'run_id': child['run_id'], 'claim_id': child['native_claim_id'],
        'intent_sha256': child['native_intent_sha256'], 'call_id': child['call_id']}
    return {'original_baseline_run_id': child['run_id'], 'original_output': original,
        'original_design_sha256': child['native_design_sha256'], 'original_manifest_sha256': 'd' * 64,
        'original_launch_sha256': account._file_digest(launch), 'original_provider_terminal_sha256': child['native_terminal_sha256'],
        'original_claim_id': child['native_claim_id'], 'original_intent_sha256': child['native_intent_sha256'],
        'original_call_id': child['call_id'], 'original_source_sha256': {'invented_worker.py': 'c' * 64}}


def ledger(*, chained=False):
    first, second, third = ('native_reasoning_fixture_' + name + '-envelope' for name in ('v1', 'v2', 'v3'))
    child1 = failed_child('native_reasoning_fixture_v1_baseline', first, '1' * 64, 'a')
    facts1 = source(child1, first[:-len('-envelope')])
    evidence = seal({'version': 'native-provider-positive-failure-v2', 'call_id': child1['call_id'],
        'provider_status': 'FAILURE', 'provider_status_value': 2, 'positive_provider_failure_status': True}, 'evidence_sha256')
    facts1.update(original_failure_evidence=evidence, original_failure_evidence_sha256=evidence['evidence_sha256'])
    prior = seal({'version': account.V2, 'original_envelope_id': first, 'new_envelope_id': second,
        'migrated_usd': 5.25, 'new_reservation_created': False, 'old_failed_child_run_id': child1['run_id'],
        'old_failed_child_allowance_held_usd': 1.75, 'original_failure': facts1,
        'new_design_sha256': '2' * 64, 'new_manifest_sha256': 'd' * 64,
        'recovery_review_sha256': 'e' * 64, 'new_source_sha256': {'invented_worker2.py': 'c' * 64},
        'remote_owner_absent': True, 'remote_artifacts_absent': True, 'validated_outputs': 0,
        'created_at_utc': '2026-11-04T02:00:00+00:00'}, 'migration_sha256')
    env1 = {'run_id': first, 'service': 'modal', 'status': 'superseded', 'native_envelope': True,
        'reserved_usd': 0, 'initial_reserved_usd': 7, 'native_design_sha256': '1' * 64,
        'dispatches': [child1['run_id']], 'superseded_by': second, 'native_migration': deepcopy(prior)}
    env2 = {'run_id': second, 'service': 'modal', 'status': 'reserved', 'native_envelope': True,
        'reserved_usd': 5.25, 'initial_reserved_usd': 5.25, 'native_design_sha256': '2' * 64,
        'dispatches': [], 'native_migration': deepcopy(prior)}
    jobs = [env1, child1, env2]
    if chained:
        child2 = failed_child('native_reasoning_fixture_v2_baseline', second, '2' * 64, 'b')
        facts2 = source(child2, second[:-len('-envelope')])
        facts2.update(parent_migration_receipt=deepcopy(prior), parent_migration_receipt_sha256=account._file_digest(prior),
            v1_failure_source=deepcopy(facts1), parent_mount_source_tokenizer_verified=True,
            parent_remote_owner_and_artifacts_exist=True, runtime_model_load_verified=False, validated_outputs=0)
        funding = seal({'version': account.V3, 'parent_envelope_id': second, 'new_envelope_id': third,
            'transferred_unused_usd': 3.5, 'additional_new_reservation_usd': 1.75, 'funded_envelope_usd': 5.25,
            'new_reservation_created': True, 'total_commitment_increase_usd': 1.75,
            'parent_failed_child_run_id': child2['run_id'], 'v1_failed_child_run_id': child1['run_id'],
            'historical_failed_allowance_each_usd': 1.75, 'parent_failure': facts2, 'config_proof': {'invented': True},
            'parent_migration_receipt_sha256': account._file_digest(prior), 'new_design_sha256': '3' * 64,
            'new_manifest_sha256': 'd' * 64, 'config_recovery_review_sha256': 'e' * 64,
            'new_source_sha256': {'invented_worker3.py': 'c' * 64}, 'parent_remote_owner_and_artifacts_exist': True,
            'parent_mount_source_tokenizer_verified': True, 'validated_outputs': 0,
            'created_at_utc': '2026-11-04T02:30:00+00:00'}, 'funding_sha256')
        env2.update(status='superseded', reserved_usd=0, dispatches=[child2['run_id']],
            superseded_by=third, native_config_funding=deepcopy(funding))
        env3 = {'run_id': third, 'service': 'modal', 'status': 'reserved', 'native_envelope': True,
            'reserved_usd': 5.25, 'initial_reserved_usd': 5.25, 'native_design_sha256': '3' * 64,
            'dispatches': [], 'native_config_funding': deepcopy(funding)}
        jobs.extend([child2, env3])
    return {'limits': {'modal': 30, 'deepseek': 20}, 'estimated_spend': {'modal': 0, 'deepseek': 2},
        'reserved': {'modal': 8.75 if chained else 7, 'deepseek': 0}, 'jobs': jobs}


def snapshot(*, age=0):
    return {'queried_at_utc': (NOW - timedelta(seconds=age)).isoformat(),
        'start_utc': (NOW - timedelta(days=1)).isoformat(), 'metered_cost': '4.25',
        'billed_cost': '0', 'source': 'Invented supported provider fixture'}


class NativeBudgetTests(unittest.TestCase):
    def test_v1_zero_transfer_preserves_history_and_pending_failure_liability(self):
        value = ledger(); original = deepcopy(value)
        with patch.object(account.legacy, 'fetch_provider', side_effect=AssertionError('No provider in pure API')):
            result = account.reconcile(value, snapshot(), now=NOW)
        self.assertEqual(value, original)
        self.assertIsNot(result, value)
        self.assertTrue(result['modal_budget_accounting']['new_paid_launches_allowed'])
        self.assertEqual(result['modal_budget_accounting']['issues'], [])
        self.assertEqual(result['reserved']['modal'], 7)
        self.assertEqual(result['estimated_spend']['modal'], 7.25)
        self.assertEqual(result['jobs'][0]['status'], 'superseded')
        self.assertEqual(result['jobs'][0]['native_migration'], original['jobs'][0]['native_migration'])
        self.assertNotIn('finished_at_utc', result['jobs'][0])
        self.assertNotIn('provider_app_stopped_at_utc', result['jobs'][0])
        self.assertEqual(result['jobs'][1]['status'], 'failed')
        self.assertEqual(result['jobs'][1]['reserved_usd'], 1.75)
        self.assertEqual(result['jobs'][1]['budget_liability']['kind'], 'terminal_usage_pending_collection')

    def test_complete_v1_v2_v3_dag_conserves_new_175_and_both_failed_histories(self):
        value = ledger(chained=True)
        result = account.reconcile(value, snapshot(), now=NOW)
        self.assertEqual(len(result['native_transfer_accounting']['verified_superseded_ids']), 2)
        self.assertEqual(result['reserved']['modal'], 8.75)
        self.assertEqual(sum(edge['new_reservation_usd'] for edge in result['native_transfer_accounting']['edges']), 1.75)
        self.assertEqual([job['status'] for job in result['jobs']], ['superseded', 'failed', 'superseded', 'failed', 'reserved'])
        self.assertEqual([job['reserved_usd'] for job in result['jobs']], [0, 1.75, 0, 1.75, 5.25])
        # Reversing source/target ledger order cannot invalidate the same DAG.
        value['jobs'].reverse()
        result = account.reconcile(value, snapshot(), now=NOW)
        self.assertTrue(result['native_transfer_accounting']['conservation_verified'])

    def test_unknown_states_remain_blocked_and_unknown_superseded_is_rejected(self):
        value = ledger()
        value['jobs'].append({'run_id': 'unrelated', 'service': 'modal', 'status': 'unrecognized', 'reserved_usd': 2})
        result = account.reconcile(value, snapshot(), now=NOW)
        self.assertFalse(result['modal_budget_accounting']['new_paid_launches_allowed'])
        self.assertEqual(result['reserved']['modal'], 9)
        self.assertIn('Unknown Modal job state: unrecognized', result['modal_budget_accounting']['issues'])
        value['jobs'][-1].update(status='superseded', reserved_usd=0)
        with self.assertRaises(ValueError): account.reconcile(value, snapshot(), now=NOW)
        value = ledger(); value['jobs'][0]['reserved_usd'] = .01
        with self.assertRaises(ValueError): account.reconcile(value, snapshot(), now=NOW)

    def test_missing_tampered_or_foreign_audit_never_normalizes_superseded(self):
        for mutation in ('missing', 'hash', 'nativeflag', 'targethash', 'childclaim', 'childamount', 'dispatch', 'launchhash', 'duplicate', 'malformedmoney'):
            value = ledger(); before = deepcopy(value)
            if mutation == 'missing': value['jobs'][2].pop('native_migration')
            elif mutation == 'hash': value['jobs'][0]['native_migration']['migration_sha256'] = '0' * 64
            elif mutation == 'nativeflag': value['jobs'][0].pop('native_envelope')
            elif mutation == 'targethash': value['jobs'][2]['native_design_sha256'] = '0' * 64
            elif mutation == 'childclaim': value['jobs'][1]['native_claim_id'] = '0' * 32
            elif mutation == 'childamount': value['jobs'][1]['reserved_usd'] = 0
            elif mutation == 'dispatch': value['jobs'][0]['dispatches'] = []
            elif mutation == 'launchhash':
                record = deepcopy(value['jobs'][0]['native_migration']); record['original_failure']['original_launch_sha256'] = '0' * 64
                seal(record, 'migration_sha256'); value['jobs'][0]['native_migration'] = record; value['jobs'][2]['native_migration'] = deepcopy(record)
            elif mutation == 'duplicate': value['jobs'].append(deepcopy(value['jobs'][2]))
            elif mutation == 'malformedmoney': value['jobs'][0]['reserved_usd'] = 'unparseable'
            mutated = deepcopy(value)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): account.reconcile(value, snapshot(), now=NOW)
            self.assertEqual(value, mutated)

    def test_chained_balance_parent_receipt_and_new_reservation_cannot_be_forged(self):
        for mutation in ('balance', 'priorhash', 'newmoney', 'zerobool', 'selfcycle', 'oldclaim'):
            value = ledger(chained=True)
            funding = deepcopy(value['jobs'][2]['native_config_funding'])
            if mutation == 'balance': value['jobs'][4]['reserved_usd'] = 5.24
            elif mutation == 'priorhash': funding['parent_migration_receipt_sha256'] = '0' * 64
            elif mutation == 'newmoney': funding['additional_new_reservation_usd'] = 0
            elif mutation == 'zerobool': funding['validated_outputs'] = False
            elif mutation == 'selfcycle': funding['new_envelope_id'] = funding['parent_envelope_id']
            elif mutation == 'oldclaim': funding['parent_failure']['v1_failure_source']['original_claim_id'] = '0' * 32
            seal(funding, 'funding_sha256')
            value['jobs'][2]['native_config_funding'] = funding; value['jobs'][4]['native_config_funding'] = deepcopy(funding)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): account.reconcile(value, snapshot(), now=NOW)

    def test_observation_staleness_and_verified_terminal_lag_rules_are_unchanged(self):
        value = ledger()
        result = account.reconcile(value, snapshot(age=3600), now=NOW)
        self.assertFalse(result['modal_budget_accounting']['new_paid_launches_allowed'])
        value['jobs'][1]['finished_at_utc'] = (NOW - timedelta(minutes=30)).isoformat()
        result = account.reconcile(value, snapshot(), now=NOW)
        self.assertEqual(result['reserved']['modal'], 5.25)
        self.assertEqual(result['jobs'][1]['reserved_usd'], 1.75)
        self.assertEqual(result['jobs'][1]['budget_liability']['kind'], 'covered_by_observation_after_lag_window')

    def test_cli_artifact_gate_checks_original_and_target_bytes_without_provider(self):
        parent = account.PRIVATE / 'local_check_tmp'; parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as temporary:
            root = Path(temporary); code = root / 'source'; code.mkdir()
            def write(path, data):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(account._file_bytes(data)); return hashlib.sha256(path.read_bytes()).hexdigest()
            (code / 'invented_worker.py').write_bytes(b'# Invented old source\n')
            (code / 'invented_worker2.py').write_bytes(b'# Invented new source\n')
            value = ledger(); old, child, new = value['jobs']
            record = deepcopy(old['native_migration']); facts = record['original_failure']
            original, target = root / facts['original_output'], root / new['run_id'][:-len('-envelope')]
            folder = original / 'arms' / child['run_id']
            facts['original_source_sha256'] = {'invented_worker.py': hashlib.sha256((code / 'invented_worker.py').read_bytes()).hexdigest()}
            old['native_design_sha256'] = child['native_design_sha256'] = facts['original_design_sha256'] = write(original / 'design.json', {'source_sha256': facts['original_source_sha256']})
            facts['original_manifest_sha256'] = write(original / 'study_manifest.json', {'invented': 'Original manifest'})
            facts['original_launch_sha256'] = write(folder / 'launch.json', {'run_id': child['run_id'],
                'call_id': child['call_id'], 'claim_id': child['native_claim_id'], 'intent_sha256': child['native_intent_sha256']})
            child['native_terminal_sha256'] = facts['original_provider_terminal_sha256'] = write(folder / 'provider_terminal.json', {
                'kind': 'failed', 'call_id': child['call_id'], 'claim_id': child['native_claim_id'], 'intent_sha256': child['native_intent_sha256']})
            record['new_source_sha256'] = {'invented_worker2.py': hashlib.sha256((code / 'invented_worker2.py').read_bytes()).hexdigest()}
            new['native_design_sha256'] = record['new_design_sha256'] = write(target / 'design.json', {'source_sha256': record['new_source_sha256'], 'migration_source': facts})
            record['new_manifest_sha256'] = write(target / 'study_manifest.json', {'invented': 'New manifest'})
            record['recovery_review_sha256'] = write(target / 'review_recovery.json', {'reviewed': True, 'design_sha256': record['new_design_sha256']})
            seal(record, 'migration_sha256')
            old['native_migration'] = deepcopy(record); new['native_migration'] = deepcopy(record)
            write(target / 'migration.json', record)
            with patch.object(account, 'PRIVATE', root), patch.object(account, 'ROOT', code), \
                    patch.object(account.legacy, 'fetch_provider', side_effect=AssertionError('No provider in artifact validation')):
                self.assertEqual(len(account.validate_local_audits(value)['verified_superseded_ids']), 1)
                for path in (target / 'migration.json', target / 'study_manifest.json', code / 'invented_worker.py'):
                    raw = path.read_bytes(); path.write_bytes(raw + b' ')
                    with self.subTest(file=path.name), self.assertRaises(ValueError): account.validate_local_audits(value)
                    path.write_bytes(raw)


if __name__ == '__main__': unittest.main()
