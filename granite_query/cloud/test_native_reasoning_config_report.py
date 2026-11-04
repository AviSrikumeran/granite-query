"""V3 report fixtures reuse invented V2 receipt builders; no providers run."""
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

from cloud import native_reasoning_config_report as report
from cloud import test_native_reasoning_recovery_report as fixtures
from cloud import native_reasoning_control as local


class ConfigReportTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RecoveryReportTests(methodName='runTest')
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.root, self.output, self.api = self.fixture.root, self.fixture.output, self.fixture.api
        self.fixture.stack.enter_context(patch.object(report, 'PUBLIC', self.root / 'public'))
        self.fixture.stack.enter_context(patch.object(report, 'DOCS', self.root / 'docs'))
        self.fixture.stack.enter_context(patch.object(report, 'paired', return_value={'count': 200, 'difference_percentage_points': 0}))
        self.chain = [{'call_id': call, 'status': 'failed', 'validated_outputs': 0,
            'model_loaded': False, 'evaluation_complete': False, 'evidence_sha256': str(index + 1) * 64}
            for index, call in enumerate(report.PRIOR_CALLS)]
        self.chain[1].update(mount_verified=True, source_verified=True, tokenizer_verified=True, elapsed_seconds=19.087607)
        self.api.failure_chain_for_report = Mock(side_effect=lambda output: deepcopy(self.chain))
        self.funding = {'version': 'native-reasoning-config-stage-funding-v3',
            'transferred_unused_usd': 3.5, 'additional_new_reservation_usd': 1.75,
            'funded_envelope_usd': 5.25, 'new_reservation_created': True,
            'total_commitment_increase_usd': 1.75, 'validated_outputs': 0,
            'created_at_utc': '2026-11-04T03:00:00+00:00'}
        self.funding['funding_sha256'] = local.digest(self.funding)
        self.api.funding_record_for_report = Mock(side_effect=lambda output, stamp: deepcopy(self.funding))

    def test_default_is_read_only_and_pending_metrics_unavailable(self):
        before = set(self.root.rglob('*'))
        value = report.build(self.output, control_api=self.api)
        self.assertEqual(value['stage'], 'config_recovery_unprepared')
        self.assertTrue(all(item['accuracy_percent'] is None for item in value['jobs']))
        self.assertEqual([item['validated_evaluation_outputs'] for item in value['prior_attempts']], [0, 0])
        self.assertEqual(set(self.root.rglob('*')), before)
        self.assertEqual(value['funding']['planned_additional_new_reservation_usd'], 1.75)
        self.assertFalse(value['funding']['additional_cash_claimed'])

    def test_history_requires_both_actual_calls_zero_outputs_and_v2_startup_proofs(self):
        self.fixture.prepare_original(); self.fixture.prepare_jobs()
        value = report.build(self.output, control_api=self.api)
        self.assertEqual(value['stage'], 'config_recovery_plans_prepared')
        self.assertEqual([item['call_id'] for item in value['prior_attempts']], list(report.PRIOR_CALLS))
        self.assertTrue(value['prior_attempts'][1]['tokenizer_verified'])
        self.assertEqual(value['prior_attempts'][1]['elapsed_seconds'], 19.087607)
        for field, wrong in [('validated_outputs', 1), ('call_id', 'fc-other'), ('model_loaded', True), ('mount_verified', False)]:
            original = deepcopy(self.chain)
            self.chain[1][field] = wrong
            value = report.build(self.output, control_api=self.api)
            self.assertEqual(value['stage'], 'config_recovery_evidence_requires_reconciliation')
            self.assertTrue(all(item['metrics'] is None for item in value['jobs']))
            self.chain = original

    def test_funding_discloses_transfer_and_new_reservation_within_existing_ceiling(self):
        self.fixture.prepare_original(); self.fixture.prepare_jobs()
        local.write(self.output / 'funding.json', self.funding)
        value = report.build(self.output, control_api=self.api)
        self.assertEqual(value['funding']['transferred_existing_unused_usd'], 3.5)
        self.assertEqual(value['funding']['additional_new_reservation_usd'], 1.75)
        self.assertTrue(value['funding']['new_reservation_created'])
        self.assertEqual(value['funding']['funded_envelope_usd'], 5.25)
        self.assertEqual(value['funding']['existing_modal_ceiling_usd'], 30)
        self.assertFalse(value['funding']['additional_cash_claimed'])
        changed = deepcopy(self.funding); changed['new_reservation_created'] = False
        local.write(self.output / 'funding.json', changed)
        self.assertEqual(report.build(self.output, control_api=self.api)['stage'], 'config_recovery_evidence_requires_reconciliation')
        changed = deepcopy(self.funding); changed['validated_outputs'] = False
        local.write(self.output / 'funding.json', changed)
        self.assertEqual(report.build(self.output, control_api=self.api)['stage'], 'config_recovery_evidence_requires_reconciliation')

    def test_complete_new_receipts_only_and_no_reuse_of_failed_old_calls(self):
        self.fixture.prepare_original(); self.fixture.prepare_jobs(completed=report.ROLES)
        value = report.build(self.output, control_api=self.api)
        self.assertEqual(value['stage'], 'config_recovery_all_three_completed_and_validated')
        self.assertEqual(len(value['comparisons']), 3)
        folder = self.fixture.jobs[0]['folder_path']
        for name in ('launch.json', 'result.json', 'provider_terminal.json'):
            item = local.read(folder / name); item['call_id'] = report.PRIOR_CALLS[1]
            local.write(folder / name, item)
        terminal = local.read(folder / 'provider_terminal.json'); terminal['result_sha256'] = local.sha(folder / 'result.json')
        local.write(folder / 'provider_terminal.json', terminal)
        value = report.build(self.output, control_api=self.api)
        self.assertIsNone(value['jobs'][0]['accuracy_percent']); self.assertIsNone(value['comparisons'])

    def test_explicit_outputs_preserve_v1_and_v2_canonical_history(self):
        self.fixture.prepare_original(); self.fixture.prepare_jobs()
        report.PUBLIC.mkdir()
        histories = ('NATIVE_REASONING_STUDY.json', 'NATIVE_REASONING_STUDY.md',
                     'NATIVE_REASONING_RECOVERY.json', 'NATIVE_REASONING_RECOVERY.md')
        for name in histories: (report.PUBLIC / name).write_bytes(('ORIGINAL ' + name).encode())
        report.DOCS.mkdir()
        (report.DOCS / 'native-reasoning-recovery.json').write_bytes(b'ORIGINAL V2 CANONICAL DOCS')
        before = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        report.build(self.output, write=True, control_api=self.api)
        after = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        changed = {path.as_posix() for path, raw in after.items() if before.get(path) != raw}
        self.assertEqual(changed, {'public/NATIVE_REASONING_CONFIG_RECOVERY.json', 'public/NATIVE_REASONING_CONFIG_RECOVERY.md',
            'docs/native-reasoning-config-recovery.json', 'docs/native-reasoning-study.json'})
        for name in histories: self.assertEqual((report.PUBLIC / name).read_bytes(), before[(report.PUBLIC / name).relative_to(self.root)])
        self.assertEqual((report.DOCS / 'native-reasoning-recovery.json').read_bytes(), b'ORIGINAL V2 CANONICAL DOCS')
        view = local.read(report.DOCS / 'native-reasoning-study.json')
        self.assertTrue(view['derived_current_study_view']); self.assertFalse(view['provider_export'])
        self.assertEqual(view['source_report'], 'native-reasoning-config-recovery.json')
        self.assertEqual(view['source_report_sha256'], local.sha(report.DOCS / 'native-reasoning-config-recovery.json'))
        self.assertEqual(len(view['historical_reports']), 2)
        for private in ('PRIVATE ERROR TEXT', 'PRIVATE QUESTION', 'PRIVATE TEACHER REASONING', str(self.root)):
            self.assertNotIn(private, str(view))

    def test_completed_perfect_score_does_not_override_infeasible_runtime(self):
        self.fixture.prepare_original(); self.fixture.prepare_jobs(completed=('baseline',))
        for job in self.fixture.jobs: job['forwarded_input_tokens'] = 0 if job['role'] == 'baseline' else 33638
        folder = self.fixture.jobs[0]['folder_path']
        result = local.read(folder / 'result.json'); result['elapsed_seconds'] = 1600
        local.write(folder / 'result.json', result)
        terminal = local.read(folder / 'provider_terminal.json'); terminal['result_sha256'] = local.sha(folder / 'result.json')
        local.write(folder / 'provider_terminal.json', terminal)
        metrics = self.api.validate_result(self.fixture.jobs[0], result)
        calibration = {'design_sha256': local.sha(self.output / 'design.json'), 'baseline_call_id': terminal['call_id'],
            'baseline_result_sha256': terminal['result_sha256'], 'raw_validation_sha256': terminal['raw_validation_sha256'],
            'baseline_elapsed_seconds': 1600, 'baseline_generation_seconds': metrics['latency_seconds_total'],
            'baseline_truncated': metrics['truncated'], 'forecast_seconds': {role: round(80 + 1.25 * metrics['latency_seconds_total'] + .0032 * 33638, 3) for role in ('concise', 'thinking')},
            'pair_runtime_feasible': False, 'guards': {'training': 1400, 'evaluation': 1600, 'hard': 1800}}
        local.write(self.output / 'calibration.json', calibration)
        value = report.build(self.output, control_api=self.api)
        self.assertEqual(value['stage'], 'config_recovery_baseline_complete_pair_runtime_infeasible')
        self.assertEqual(value['jobs'][0]['accuracy_percent'], 100)
        self.assertFalse(value['calibration']['pair_runtime_feasible'])
        self.assertIsNone(value['comparisons'])
        calibration['forecast_seconds']['thinking'] += .001
        local.write(self.output / 'calibration.json', calibration)
        value = report.build(self.output, control_api=self.api)
        self.assertEqual(value['stage'], 'config_recovery_evidence_requires_reconciliation')
        self.assertTrue(all(job['accuracy_percent'] is None for job in value['jobs']))


if __name__ == '__main__': unittest.main()
