"""Sanitization and complete-receipt gates on invented local metadata only."""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cloud import native_reasoning_report as report
from cloud import native_reasoning_control as control
from cloud.comparison_metrics import summarize


class NativeReportTests(unittest.TestCase):
    def setUp(self):
        parent = control.PRIVATE / 'local_check_tmp'; parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.output = self.root / 'study'; self.collection = self.root / 'collection'
        self.output.mkdir(); self.collection.mkdir()
        self.sources = {name: 'a' * 64 for name in control.SOURCES}
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(control, 'verify_design', return_value={
            'collection': self.collection.relative_to(control.PRIVATE).as_posix()}))
        self.stack.enter_context(patch.object(control, 'source_inventory', return_value=self.sources))
        self.stack.enter_context(patch.object(report, 'PUBLIC', self.root / 'public'))
        self.stack.enter_context(patch.object(report, 'DOCS', self.root / 'docs'))
        control.write(self.output / 'design.json', {'fixture': True})
        control.write(self.collection / 'plan.json', {'plan_sha256': 'b' * 64})
        self.jobs = []
        self.stack.enter_context(patch.object(control, 'load_jobs', side_effect=lambda output: self.jobs))
        for phase in ('baseline', 'pair'):
            control.write(self.output / f'review_{phase}.json', {'invented_review': phase})

    def prepare_jobs(self, *, complete=False):
        control.write(self.output / 'study_manifest.json', {'fixture': True})
        dev = [{'id': f'gsm8k:train:{10000+i:05d}', 'prompt': f'PRIVATE QUESTION {i}', 'gold_answer': '7', 'source_split': 'train'} for i in range(200)]
        for role in control.ROLES:
            folder = self.output / 'arms' / ('invented_' + role)
            plan = {'run_id': folder.name, 'arm': role, 'token_budget': 0 if role == 'baseline' else 16384,
                'optimizer_updates': 0 if role == 'baseline' else 16}
            plan['protocol_hash'] = control.digest(plan)
            data = {'development': dev, 'arm': None if role == 'baseline' else {'training': [{'id': 'private_teaching_id'}]}}
            job = {'role': role, 'run_id': folder.name, 'folder_path': folder, 'data': data, 'plan': plan}
            self.jobs.append(job)
            if not complete: continue
            phase = 'baseline' if role == 'baseline' else 'pair'
            dispatch = control.make_dispatch(plan, data, self.sources, control.sha(self.output / f'review_{phase}.json'), 'c' * 32)
            control.write(folder / 'dispatch.json', dispatch)
            ack = {'run_id': job['run_id'], 'claim_id': dispatch['claim_id'], 'intent_sha256': dispatch['intent_sha256'], 'call_id': 'fc-INVENTED-' + role}
            control.write(folder / 'launch.json', ack)
            rows = [{'id': row['id'], 'gold_answer': '7', 'response': '#### 7', 'truncated': False,
                'generated_tokens': 10, 'elapsed_seconds': .1} for row in dev]
            metrics = summarize(rows)
            result = {'stage': 'completed', 'run_id': job['run_id'], 'plan': plan, 'dispatch': dispatch,
                'dispatch_sha256': control.digest(dispatch), 'protocol_hash': plan['protocol_hash'], 'call_id': ack['call_id'],
                'supervised_tokens': plan['token_budget'], 'optimizer_updates': plan['optimizer_updates'],
                'official_test_used': False, 'evaluation_complete': True, 'retained_evaluation_count': 200,
                'raw_pending': False, 'elapsed_seconds': 50, 'evaluations': {role: rows}}
            control.write(folder / 'result.json', result)
            control.write(folder / 'raw_validation.json', {'raw_batches_verified': 25, 'fixed_denominator': 200,
                'metrics': metrics, 'dispatch_sha256': control.digest(dispatch)})
            terminal = dict(ack, kind='completed', result_sha256=control.sha(folder / 'result.json'),
                raw_validation_sha256=control.sha(folder / 'raw_validation.json'))
            control.write(folder / 'provider_terminal.json', terminal)

    def test_active_teacher_counts_only_and_default_has_no_writes_or_raw_channels(self):
        control.write(self.collection / 'teacher_summary.json', {'stage': 'collecting', 'run_id': self.collection.name,
            'plan_sha256': 'b' * 64, 'requested_questions': 256, 'requested_original_calls': 512,
            'retained_original_outcomes': 34, 'eligible_question_pairs': 11, 'unknown_usage_attempts': 0,
            'conditions': {}, 'raw': 'PRIVATE RESPONSE', 'reasoning_content': 'SECRET CHANNEL'})
        before = {p.relative_to(self.root) for p in self.root.rglob('*')}
        value = report.build(self.output)
        self.assertEqual(value['teacher']['retained_original_outcomes'], 34)
        self.assertTrue(all(job['accuracy_percent'] is None for job in value['jobs']))
        self.assertIsNone(value['comparisons'])
        self.assertEqual({p.relative_to(self.root) for p in self.root.rglob('*')}, before)
        self.assertNotIn('PRIVATE RESPONSE', str(value)); self.assertNotIn('SECRET CHANNEL', str(value))

    def test_prepared_or_failed_partial_roles_have_no_accuracy(self):
        self.prepare_jobs()
        value = report.build(self.output)
        self.assertTrue(all(job['status'] == 'prepared' and job['accuracy_percent'] is None for job in value['jobs']))
        job = self.jobs[1]; folder = job['folder_path']
        partial = {'retained_evaluation_count': 8, 'supervised_tokens': 8192, 'optimizer_updates': 8,
            'evaluations': {'concise': [{'response': 'DO NOT PUBLISH'}]}}
        control.write(folder / 'provider_result.json', partial)
        control.write(folder / 'provider_terminal.json', {'kind': 'failed', 'partial_result_sha256': control.sha(folder / 'provider_result.json')})
        value = report.build(self.output)
        self.assertEqual(value['jobs'][1]['retained_evaluation_count'], 8)
        self.assertIsNone(value['jobs'][1]['accuracy_percent']); self.assertIsNone(value['jobs'][1]['metrics'])
        self.assertNotIn('DO NOT PUBLISH', str(value)); self.assertIsNone(value['comparisons'])

    def test_completed_metrics_need_each_full_receipt_and_hash_chain(self):
        self.prepare_jobs(complete=True)
        with patch.object(report, 'paired', return_value={'count': 200, 'difference_percentage_points': 0}):
            value = report.build(self.output)
            self.assertEqual(value['stage'], 'all_three_completed_and_locally_validated')
            self.assertEqual([job['accuracy_percent'] for job in value['jobs']], [100, 100, 100])
            self.assertEqual(len(value['comparisons']), 3)
            folder = self.jobs[2]['folder_path']
            control.write(folder / 'raw_validation.json', {'raw_batches_verified': 24})
            value = report.build(self.output)
        self.assertEqual(value['jobs'][2]['status'], 'receipt_validation_failed')
        self.assertIsNone(value['jobs'][2]['accuracy_percent']); self.assertIsNone(value['comparisons'])

    def test_forged_rehashed_proof_or_wrong_source_cannot_publish_metrics(self):
        self.prepare_jobs(complete=True)
        folder = self.jobs[0]['folder_path']
        proof = control.read(folder / 'raw_validation.json'); proof['fixed_denominator'] = 199
        control.write(folder / 'raw_validation.json', proof)
        terminal = control.read(folder / 'provider_terminal.json')
        terminal['raw_validation_sha256'] = control.sha(folder / 'raw_validation.json')
        control.write(folder / 'provider_terminal.json', terminal)
        value = report.build(self.output)
        self.assertIsNone(value['jobs'][0]['accuracy_percent'])
        self.sources['native_reasoning_contract.py'] = 'f' * 64
        value = report.build(self.output)
        self.assertTrue(all(job['accuracy_percent'] is None for job in value['jobs']))

    def test_explicit_write_only_three_sanitized_files(self):
        self.prepare_jobs()
        report.build(self.output, write=True)
        actual = {p.relative_to(self.root).as_posix() for directory in ('public', 'docs') for p in (self.root / directory).rglob('*') if p.is_file()}
        self.assertEqual(actual, {'public/NATIVE_REASONING_STUDY.json', 'public/NATIVE_REASONING_STUDY.md', 'docs/native-reasoning-study.json'})
        self.assertNotIn('PRIVATE QUESTION', (self.root / 'public/NATIVE_REASONING_STUDY.json').read_text(encoding='utf-8'))


if __name__ == '__main__': unittest.main()
