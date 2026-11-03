"""Offline fixtures; no provider, ledger, report or pinned-source mutation."""
import copy
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

import human_study_report as report
import test_human_study_control as fixtures
from cloud.evaluation_stats import paired


class HumanReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = type('ReportSourceFixture', (fixtures.HumanStudyTests,), {})
        cls.fixture.setUpClass()

    @classmethod
    def tearDownClass(cls):
        cls.fixture.tearDownClass()

    def setUp(self):
        self.study = self.fixture.root/('report-'+self._testMethodName)
        self.assertTrue(self.study.resolve().is_relative_to((report.ROOT/'runs').resolve()))
        shutil.copytree(self.fixture.template, self.study)
        self.manifest = report.read(self.study/'study_manifest.json')
        self.jobs = {j['selector']: j for j in self.manifest['jobs']}
        self.public_workspace = self.study/'public-fixture-workspace'

    def folder(self, selector):
        return self.study/self.jobs[selector]['folder']

    def write(self, folder, name, value):
        report.control.write(folder/name, value)

    def dispatch(self, selector):
        job = self.jobs[selector]
        folder = self.folder(selector)
        self.write(folder, 'human_claim.json', {'claim_id': f'{report.SELECTORS.index(selector)+1:032x}',
            'run_id': job['run_id'], 'protocol_hash': job['protocol_hash'],
            'study_manifest_sha256': report.control.sha(self.study/'study_manifest.json')})
        self.write(folder, 'launch.json', {'run_id': job['run_id'], 'call_id': 'fc-reportfixture-'+selector})

    def complete(self, selector, correct=150, *, truncate_first=False):
        self.dispatch(selector)
        job, folder = self.jobs[selector], self.folder(selector)
        data, plan = report.read(folder/'input.json'), report.read(folder/'plan.json')
        rows = [{'id': row['id'], 'gold_answer': row['gold_answer'],
            'response': 'PRIVATE_MODEL_REASONING_'+selector+'\n#### '+('13' if i < correct else '99'),
            'truncated': truncate_first and i == 0, 'generated_tokens': 5,
            'batch_size': 8, 'batch_elapsed_seconds': .8, 'elapsed_seconds': .1}
            for i, row in enumerate(data['development'])]
        result = {'stage': 'completed', 'run_id': job['run_id'], 'plan': plan,
            'arm': data['arm']['arm'] if 'arm' in data else 'evaluation_only',
            'supervised_tokens': job['token_budget'], 'optimizer_updates': job['token_budget']//1024,
            'weighted_losses': [.5]*(job['token_budget']//1024), 'held_out_test_used': False,
            'elapsed_seconds': 100, 'evaluations': {selector: rows}}
        self.write(folder, 'result.json', result)
        self.write(folder, 'study_terminal.json', {'kind': 'completed', 'call_id': 'fc-reportfixture-'+selector,
            'result_sha256': report.control.sha(folder/'result.json')})
        return result

    def build(self, **kwargs):
        return report.build(study=self.study, workspace=self.public_workspace,
            paired_fn=lambda left, right: paired(left, right, resamples=200), **kwargs)

    def test_queued_unknown_metrics_and_pure_default(self):
        with patch.object(report.control.HumanRunner, 'recover', side_effect=AssertionError('must not recover')), \
             patch.object(report.control.HumanRunner, 'calibrate', side_effect=AssertionError('must not calibrate')), \
             patch.object(report.control.Backend, 'refresh', side_effect=AssertionError('must not refresh')), \
             patch.object(report.control.Backend, 'poll', side_effect=AssertionError('must not poll')):
            public = self.build()
        self.assertEqual(public['status'], 'queued')
        self.assertEqual(public['completed_jobs'], 0)
        self.assertEqual(public['points'], [])
        for value in public['jobs'].values():
            self.assertEqual(value['status'], 'queued')
            self.assertIsNone(value['metrics'])
            self.assertIsNone(value['accuracy_percent'])
            self.assertIsNone(value['actual_supervised_tokens'])
        self.assertFalse(self.public_workspace.exists())
        self.assertFalse((self.study/'calibration.json').exists())

    def test_exact200_paired_directions_and_truncation(self):
        self.complete('baseline', 150)
        self.complete('random', 160)
        first = self.build()
        self.assertEqual(first['comparisons']['random_vs_baseline']['statistics']['difference_percentage_points'], 5)
        self.assertEqual(first['comparisons']['skill_vs_random']['status'], 'unavailable')
        self.assertIsNone(first['jobs']['skill']['metrics'])
        self.complete('skill', 170, truncate_first=True)
        public = self.build()
        self.assertEqual(public['status'], 'completed')
        self.assertEqual(public['jobs']['skill']['metrics']['numeric_correct'], 169)
        self.assertEqual(public['jobs']['skill']['metrics']['truncated'], 1)
        comparison = public['comparisons']['skill_vs_random']['statistics']
        self.assertEqual(comparison['count'], 200)
        self.assertEqual(comparison['corrected'], 10)
        self.assertEqual(comparison['regressed'], 1)
        self.assertEqual(comparison['difference_percentage_points'], 4.5)
        self.assertFalse(public['cohort']['legacy64_included'])
        self.assertEqual(public['jobs']['random']['actual_supervised_tokens'], 65536)
        self.assertEqual(public['jobs']['baseline']['actual_supervised_tokens'], 0)

    def test_duplicate_calls_and_claims_are_ambiguous(self):
        self.complete('baseline')
        self.complete('random')
        path = self.folder('random')/'launch.json'
        launch = report.read(path)
        launch['call_id'] = 'fc-reportfixture-baseline'
        self.write(path.parent, path.name, launch)
        public = self.build()
        for selector in ('baseline', 'random'):
            self.assertEqual(public['jobs'][selector]['status'], 'ambiguous')
            self.assertIsNone(public['jobs'][selector]['metrics'])
        self.complete('random')
        path = self.folder('random')/'human_claim.json'
        claim = report.read(path)
        claim['claim_id'] = report.read(self.folder('baseline')/'human_claim.json')['claim_id']
        self.write(path.parent, path.name, claim)
        self.assertEqual(self.build()['jobs']['baseline']['status'], 'ambiguous')

    def test_invalid_complete_outputs_never_receive_zero_accuracy(self):
        mutations = {
            'wrong_run': lambda r: r.update(run_id='wrong'),
            'wrong_gold': lambda r: r['evaluations']['random'][0].update(gold_answer='14'),
            'duplicate_qid': lambda r: r['evaluations']['random'][1].update(id=r['evaluations']['random'][0]['id']),
            'partial199': lambda r: r['evaluations']['random'].pop(),
            'wrong_plan': lambda r: r['plan'].update(learning_rate=.001),
            'wrong_arm': lambda r: r.update(arm='valued'),
            'incomplete_updates': lambda r: r['weighted_losses'].pop(),
            'wrong_timing': lambda r: r['evaluations']['random'][0].update(batch_elapsed_seconds=8),
            'wrong_batch_size': lambda r: r['evaluations']['random'][0].update(batch_size=4, elapsed_seconds=.2),
            'inconsistent_batch_time': lambda r: r['evaluations']['random'][0].update(batch_elapsed_seconds=1.6, elapsed_seconds=.2),
            'generation_longer_than_worker': lambda r: r.update(elapsed_seconds=10),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                value = self.complete('random')
                mutate(value)
                folder = self.folder('random')
                self.write(folder, 'result.json', value)
                terminal = report.read(folder/'study_terminal.json')
                terminal['result_sha256'] = report.control.sha(folder/'result.json')
                self.write(folder, 'study_terminal.json', terminal)
                public = self.build()
                self.assertEqual(public['jobs']['random']['status'], 'failed')
                self.assertIsNone(public['jobs']['random']['accuracy_percent'])
                self.assertEqual(public['points'], [])

    def test_lifecycle_and_ambiguous_terminal_hash(self):
        folder = self.folder('baseline')
        self.dispatch('baseline')
        self.assertEqual(self.build()['jobs']['baseline']['status'], 'running')
        self.write(folder, 'remote_status.json', {'stage': 'queued'})
        self.assertEqual(self.build()['jobs']['baseline']['status'], 'queued')
        self.write(folder, 'remote_status.json', {'stage': 'training'})
        self.assertEqual(self.build()['jobs']['baseline']['status'], 'running')
        for malformed in ([], {}):
            self.write(folder, 'remote_status.json', {'stage': malformed})
            self.assertEqual(self.build()['jobs']['baseline']['status'], 'ambiguous')
        self.write(folder, 'remote_status.json', {'stage': 'failed', 'error': 'PRIVATE_ERROR_BODY'})
        self.assertEqual(self.build()['jobs']['baseline']['status'], 'failed')
        (folder/'remote_status.json').unlink()
        self.complete('baseline')
        terminal = report.read(folder/'study_terminal.json')
        terminal['result_sha256'] = '0'*64
        self.write(folder, 'study_terminal.json', terminal)
        self.assertEqual(self.build()['jobs']['baseline']['status'], 'ambiguous')
        (folder/'launch.json').unlink()
        self.assertEqual(self.build()['jobs']['baseline']['status'], 'ambiguous')
        (folder/'human_claim.json').unlink()
        self.assertEqual(self.build()['jobs']['baseline']['status'], 'ambiguous')

    def test_calibration_and_exact_phase_review_remain_separate(self):
        self.complete('baseline')
        public = self.build()
        self.assertEqual(public['runtime_and_review']['calibration']['status'], 'pending_calibration_artifact')
        self.assertEqual(public['runtime_and_review']['pair_review'], 'blocked_by_baseline_calibration')
        base = public['jobs']['baseline']
        forecasts = {j['selector']: round(80+1.25*base['metrics']['latency_seconds_total']
            + .0032*j['forecast']['forwarded_input_tokens'], 3) for j in self.manifest['jobs'] if j['selector'] != 'baseline'}
        calibration = {'schema_version': 1, 'study_manifest_sha256': report.control.sha(self.study/'study_manifest.json'),
            'baseline_call_id': 'fc-reportfixture-baseline', 'baseline_result_sha256': base['result_sha256'],
            'baseline_elapsed_seconds': 100, 'baseline_generation_seconds': base['metrics']['latency_seconds_total'],
            'baseline_truncated': 0, 'forecast_seconds': forecasts,
            'formula': self.manifest['calibration_contract']['formula'], 'pair_runtime_feasible': True,
            'actual_worker_guards': {'training': 1400, 'evaluation': 1600, 'hard_timeout': 1800}}
        self.write(self.study, 'calibration.json', calibration)
        public = self.build()
        self.assertEqual(public['runtime_and_review']['calibration']['status'], 'validated')
        self.assertEqual(public['runtime_and_review']['pair_review'], 'pending_review')
        review = {'reviewed': True, 'phase': 'pair', 'study_manifest_sha256': report.control.sha(self.study/'study_manifest.json'),
            'controller_sha256': self.manifest['controller_sha256'], 'protected_modal_usd': 5,
            'approved_run_ids': [j['run_id'] for j in self.manifest['jobs'] if j['selector'] != 'baseline'],
            'calibration_sha256': report.control.sha(self.study/'calibration.json')}
        self.write(self.study, 'review_pair.json', review)
        self.assertEqual(self.build()['runtime_and_review']['pair_review'], 'reviewed')
        self.write(self.study, 'review_pair.json', [])
        self.assertEqual(self.build()['runtime_and_review']['pair_review'], 'invalid_review')
        self.write(self.study, 'review_pair.json', review)
        calibration['forecast_seconds']['skill'] += 1
        self.write(self.study, 'calibration.json', calibration)
        self.assertEqual(self.build()['runtime_and_review']['calibration']['status'], 'invalid_calibration_artifact')
        self.write(self.study, 'calibration.json', [])
        self.assertEqual(self.build()['runtime_and_review']['calibration']['status'], 'invalid_calibration_artifact')

    def test_changed_frozen_plan_fails_closed(self):
        path = self.folder('baseline')/'plan.json'
        plan = report.read(path)
        plan['max_new_tokens'] = 4096
        self.write(path.parent, path.name, plan)
        with self.assertRaises(ValueError):
            self.build()

    def test_sanitized_explicit_json_and_markdown_outputs(self):
        for selector in report.SELECTORS:
            self.complete(selector)
        self.write(self.folder('baseline'), 'remote_status.json', {'stage': 'completed',
            'error': 'PRIVATE_ERROR_BODY', 'api_key': 'PRIVATE_CREDENTIAL'})
        public = self.build(write=True)
        output = self.public_workspace/'docs/human-study-results.json'
        prose = self.public_workspace/'progress/HUMAN_STUDY_RESULTS.md'
        self.assertEqual(report.read(output), public)
        exported = output.read_text(encoding='utf-8')+prose.read_text(encoding='utf-8')
        for private in ('PRIVATE_MODEL_REASONING', 'PRIVATE_ERROR_BODY', 'PRIVATE_CREDENTIAL',
                        'fc-reportfixture', 'Question example', 'Unique development case', str(self.study.resolve())):
            self.assertNotIn(private, exported)
        self.assertIn('200', prose.read_text(encoding='utf-8'))
        self.assertEqual({p.relative_to(self.public_workspace).as_posix() for p in self.public_workspace.rglob('*') if p.is_file()},
            {'docs/human-study-results.json', 'progress/HUMAN_STUDY_RESULTS.md'})


if __name__ == '__main__':
    unittest.main()
