"""Recovery report evidence/sanitization fixtures; all provider data is invented."""
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cloud import native_reasoning_recovery_report as report
from cloud import native_reasoning_control as local
from cloud.comparison_metrics import summarize


class RecoveryReportTests(unittest.TestCase):
    def setUp(self):
        parent = local.PRIVATE / 'local_check_tmp'; parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.output = self.root / 'recovery'; self.original = self.root / 'original'
        self.output.mkdir(); self.original.mkdir()
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(report, 'PUBLIC', self.root / 'public'))
        self.stack.enter_context(patch.object(report, 'DOCS', self.root / 'docs'))
        self.stack.enter_context(patch.object(report, 'paired', return_value={'count': 200, 'difference_percentage_points': 0}))
        self.api = SimpleNamespace(PRIVATE=local.PRIVATE, safe=local.safe, read=local.read,
            MIGRATION_VERSION='native-reasoning-unused-envelope-migration-v2',
            sha=local.sha, digest=local.digest, validate_launch=local.validate_launch,
            validate_result=local.validate_result, verify_design=Mock(side_effect=lambda output: local.read(output / 'design.json')),
            load_jobs=Mock(side_effect=lambda output: self.jobs), Controller=lambda output: SimpleNamespace(_dispatch=self.dispatch))
        self.jobs = []

    def prepare_original(self):
        folder = self.original / 'arms' / 'INVENTED_original_baseline'
        collection = self.root / 'teacher_collection'
        local.write(collection / 'plan.json', {'plan_sha256': 'e' * 64})
        local.write(collection / 'teacher_summary.json', {'run_id': collection.name, 'plan_sha256': 'e' * 64,
            'requested_questions': 256, 'requested_original_calls': 512, 'stage': 'completed',
            'retained_original_outcomes': 512, 'eligible_question_pairs': 210, 'unknown_usage_attempts': 1,
            'conditions': {}, 'raw': 'PRIVATE TEACHER REASONING'})
        local.write(self.original / 'design.json', {'source_sha256': {'old_worker.py': 'a' * 64}})
        local.write(self.original / 'study_manifest.json', {'fixture': True})
        launch = {'run_id': folder.name, 'call_id': report.ORIGINAL_CALL, 'claim_id': 'b' * 32, 'intent_sha256': 'c' * 64}
        local.write(folder / 'launch.json', launch)
        local.write(folder / 'provider_terminal.json', dict(launch, kind='failed'))
        local.write(folder / 'first_observed_call_graph.private.json', {'queried_call_id': report.ORIGINAL_CALL,
            'inputs': [{'function_call_id': report.ORIGINAL_CALL, 'status': 'FAILURE'}]})
        error = folder / 'first_observed_provider_error.private.log'
        error.write_bytes(b'PRIVATE ERROR TEXT WITH PRIVATE PATH AND CREDENTIAL-LIKE VALUE')
        source = {'original_output': self.original.relative_to(local.PRIVATE).as_posix(),
            'original_design_sha256': local.sha(self.original / 'design.json'),
            'original_manifest_sha256': local.sha(self.original / 'study_manifest.json'),
            'original_source_sha256': {'old_worker.py': 'a' * 64}, 'original_baseline_run_id': folder.name,
            'original_call_id': report.ORIGINAL_CALL, 'original_launch_sha256': local.sha(folder / 'launch.json'),
            'original_provider_terminal_sha256': local.sha(folder / 'provider_terminal.json'),
            'original_call_graph_sha256': local.sha(folder / 'first_observed_call_graph.private.json'),
            'original_error_sha256': local.sha(error)}
        local.write(self.output / 'design.json', {'migration_source': source, 'source_sha256': {'new_worker.py': 'd' * 64},
            'collection': collection.relative_to(local.PRIVATE).as_posix()})
        local.write(self.output / 'review_recovery.json', {'reviewed': True, 'phase': 'recovery',
            'design_sha256': local.sha(self.output / 'design.json'), 'source_sha256': {'new_worker.py': 'd' * 64},
            'pre_model_failure_verified': True, 'remote_owner_absent': True, 'remote_artifacts_absent': True, 'validated_outputs': 0})
        return folder

    def dispatch(self, job):
        value = local.read(job['folder_path'] / 'dispatch.json')
        if (value['source_sha256'] != local.read(self.output / 'design.json')['source_sha256']
                or value['input_sha256'] != local.digest(job['data']) or value['plan_sha256'] != local.digest(job['plan'])):
            raise ValueError('INVENTED new-controller binding failure')
        return value

    def prepare_jobs(self, completed=()):
        local.write(self.output / 'study_manifest.json', {'fixture': True})
        dev = [{'id': f'gsm8k:train:{10000+i:05d}', 'prompt': f'PRIVATE QUESTION {i}', 'source_split': 'train', 'gold_answer': '7'} for i in range(200)]
        for role in report.ROLES:
            folder = self.output / 'arms' / ('INVENTED_recovery_' + role)
            plan = {'run_id': folder.name, 'arm': role, 'token_budget': 0 if role == 'baseline' else 16384,
                'optimizer_updates': 0 if role == 'baseline' else 16}
            plan['protocol_hash'] = local.digest(plan)
            data = {'development': dev, 'arm': None if role == 'baseline' else {'training': [{'id': 'PRIVATE_TEACHING_ID'}]}}
            job = {'role': role, 'run_id': folder.name, 'folder_path': folder, 'plan': plan, 'data': data}
            self.jobs.append(job)
            if role not in completed: continue
            dispatch = local.make_dispatch(plan, data, {'new_worker.py': 'd' * 64}, 'e' * 64, 'f' * 32)
            local.write(folder / 'dispatch.json', dispatch)
            launch = {'run_id': job['run_id'], 'claim_id': dispatch['claim_id'], 'intent_sha256': dispatch['intent_sha256'], 'call_id': 'fc-INVENTED-recovery-' + role}
            local.write(folder / 'launch.json', launch)
            rows = [{'id': row['id'], 'gold_answer': '7', 'response': '#### 7', 'truncated': False,
                'generated_tokens': 8, 'elapsed_seconds': .1} for row in dev]
            metrics = summarize(rows)
            result = {'stage': 'completed', 'run_id': job['run_id'], 'arm': role, 'plan': plan,
                'dispatch': dispatch, 'dispatch_sha256': local.digest(dispatch), 'call_id': launch['call_id'],
                'protocol_hash': plan['protocol_hash'], 'supervised_tokens': plan['token_budget'], 'optimizer_updates': plan['optimizer_updates'],
                'official_test_used': False, 'evaluation_complete': True, 'raw_pending': False,
                'retained_evaluation_count': 200, 'elapsed_seconds': 25, 'evaluations': {role: rows}}
            local.write(folder / 'result.json', result)
            local.write(folder / 'raw_validation.json', {'raw_batches_verified': 25, 'fixed_denominator': 200,
                'metrics': metrics, 'dispatch_sha256': local.digest(dispatch)})
            local.write(folder / 'provider_terminal.json', dict(launch, kind='completed',
                result_sha256=local.sha(folder / 'result.json'), raw_validation_sha256=local.sha(folder / 'raw_validation.json')))

    def test_unprepared_keeps_original_failed_zero_and_all_new_metrics_unavailable(self):
        before = set(self.root.rglob('*'))
        value = report.build(self.output, control_api=self.api)
        self.assertEqual(value['stage'], 'recovery_unprepared')
        self.assertEqual(value['original_attempt']['validated_evaluation_outputs'], 0)
        self.assertTrue(all(job['accuracy_percent'] is None for job in value['jobs']))
        self.assertIsNone(value['comparisons']); self.assertEqual(set(self.root.rglob('*')), before)

    def test_original_positive_provider_failure_and_explicit_pre_model_review_are_bound(self):
        original = self.prepare_original()
        value = report.build(self.output, control_api=self.api)
        self.assertTrue(value['original_attempt']['recovery_evidence_verified'])
        self.assertEqual(value['original_attempt']['status'], 'failed_pre_model_attempt_verified')
        self.assertIsNone(value['original_attempt']['accuracy_percent'])
        self.assertNotIn('PRIVATE ERROR TEXT', str(value)); self.assertNotIn(str(self.original), str(value))
        review = local.read(self.output / 'review_recovery.json'); review['remote_owner_absent'] = False
        local.write(self.output / 'review_recovery.json', review)
        value = report.build(self.output, control_api=self.api)
        self.assertEqual(value['stage'], 'recovery_evidence_requires_reconciliation')
        self.assertTrue(all(job['accuracy_percent'] is None for job in value['jobs']))

    def test_only_actual_new_call_full_proof_can_publish_and_compare(self):
        self.prepare_original(); self.prepare_jobs(completed=report.ROLES)
        value = report.build(self.output, control_api=self.api)
        self.assertEqual(value['stage'], 'recovery_all_three_completed_and_validated')
        self.assertEqual(len(value['comparisons']), 3)
        folder = self.jobs[0]['folder_path']
        result = local.read(folder / 'result.json'); result['call_id'] = report.ORIGINAL_CALL
        local.write(folder / 'result.json', result)
        terminal = local.read(folder / 'provider_terminal.json'); terminal['result_sha256'] = local.sha(folder / 'result.json')
        local.write(folder / 'provider_terminal.json', terminal)
        value = report.build(self.output, control_api=self.api)
        self.assertEqual(value['jobs'][0]['status'], 'receipt_validation_failed')
        self.assertIsNone(value['jobs'][0]['accuracy_percent']); self.assertIsNone(value['comparisons'])

    def test_pending_and_failed_new_roles_never_get_partial_accuracy(self):
        self.prepare_original(); self.prepare_jobs(completed=('baseline',))
        value = report.build(self.output, control_api=self.api)
        self.assertEqual(value['jobs'][0]['accuracy_percent'], 100)
        self.assertTrue(all(job['accuracy_percent'] is None for job in value['jobs'][1:]))
        self.assertIsNone(value['comparisons'])
        folder = self.jobs[0]['folder_path']
        terminal = local.read(folder / 'provider_terminal.json'); terminal['kind'] = 'failed'
        local.write(folder / 'provider_terminal.json', terminal)
        value = report.build(self.output, control_api=self.api)
        self.assertEqual(value['stage'], 'recovery_attempt_failed_requires_review')
        self.assertIsNone(value['jobs'][0]['accuracy_percent'])

    def test_wrong_original_hash_or_missing_new_manifest_proof_suppresses_metrics(self):
        folder = self.prepare_original(); self.prepare_jobs(completed=report.ROLES)
        (folder / 'first_observed_provider_error.private.log').write_bytes(b'Changed private evidence')
        value = report.build(self.output, control_api=self.api)
        self.assertEqual(value['stage'], 'recovery_evidence_requires_reconciliation')
        self.assertTrue(all(job['accuracy_percent'] is None for job in value['jobs']))
        self.api.verify_design.side_effect = ValueError('INVENTED source manifest mismatch')
        value = report.build(self.output, control_api=self.api)
        self.assertTrue(all(job['metrics'] is None for job in value['jobs']))

    def test_explicit_write_only_new_sanitized_recovery_namespace_and_derived_dashboard_view(self):
        self.prepare_original(); self.prepare_jobs()
        old_json = report.PUBLIC / 'NATIVE_REASONING_STUDY.json'
        old_md = report.PUBLIC / 'NATIVE_REASONING_STUDY.md'
        old_json.parent.mkdir()
        old_json.write_bytes(b'{"historical_canonical":"preserve byte for byte"}')
        old_md.write_bytes(b'Historical canonical journal remains unchanged.\n')
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        report.build(self.output, write=True, control_api=self.api)
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        paths = {path.as_posix() for path, raw in after.items() if before.get(path) != raw}
        self.assertEqual(paths, {'public/NATIVE_REASONING_RECOVERY.json', 'public/NATIVE_REASONING_RECOVERY.md',
            'docs/native-reasoning-recovery.json', 'docs/native-reasoning-study.json'})
        self.assertEqual(old_json.read_bytes(), before[old_json.relative_to(self.root)])
        self.assertEqual(old_md.read_bytes(), before[old_md.relative_to(self.root)])
        text = (self.root / 'public/NATIVE_REASONING_RECOVERY.json').read_text(encoding='utf-8')
        for private in ('PRIVATE ERROR TEXT', 'PRIVATE QUESTION', 'PRIVATE_TEACHING_ID', 'PRIVATE TEACHER REASONING', str(self.original)):
            self.assertNotIn(private, text)
        view = local.read(self.root / 'docs/native-reasoning-study.json')
        canonical = local.read(self.root / 'docs/native-reasoning-recovery.json')
        self.assertEqual(view['report_kind'], 'derived_current_study_view')
        self.assertTrue(view['derived_current_study_view']); self.assertFalse(view['provider_export'])
        self.assertEqual(view['source_report'], 'native-reasoning-recovery.json')
        self.assertEqual(view['source_report_sha256'], local.sha(self.root / 'docs/native-reasoning-recovery.json'))
        self.assertEqual(view['original_historical_report'], 'progress/NATIVE_REASONING_STUDY.json')
        self.assertEqual(view['teacher']['retained_original_outcomes'], 512)
        self.assertEqual(view['teacher']['unknown_usage_attempts'], 1)
        self.assertEqual(view['protocol']['teacher_candidate_pairs'], 256)
        self.assertEqual(view['protocol']['student_evaluation_count'], view['protocol']['evaluation_count'])
        self.assertEqual(view['jobs'], canonical['jobs'])
        self.assertEqual(view['original_attempt'], canonical['original_attempt'])
        self.assertTrue(all(job['accuracy_percent'] is None for job in view['jobs']))

    def test_existing_525_transfer_receipt_is_bound_without_ledger_read(self):
        self.prepare_original(); self.prepare_jobs()
        design = local.read(self.output / 'design.json'); source = design['migration_source']
        record = {'version': self.api.MIGRATION_VERSION, 'original_envelope_id': self.original.name + '-envelope',
            'new_envelope_id': self.output.name + '-envelope', 'migrated_usd': 5.25, 'new_reservation_created': False,
            'old_failed_child_run_id': source['original_baseline_run_id'], 'old_failed_child_allowance_held_usd': 1.75,
            'original_failure': source, 'new_design_sha256': local.sha(self.output / 'design.json'),
            'new_manifest_sha256': local.sha(self.output / 'study_manifest.json'),
            'recovery_review_sha256': local.sha(self.output / 'review_recovery.json'), 'new_source_sha256': design['source_sha256'],
            'remote_owner_absent': True, 'remote_artifacts_absent': True, 'validated_outputs': 0,
            'created_at_utc': '2026-11-04T02:00:00+00:00'}
        record['migration_sha256'] = local.digest(record)
        local.write(self.output / 'migration.json', record)
        value = report.build(self.output, control_api=self.api)
        self.assertEqual(value['budget_migration']['status'], 'reviewed_receipt_verified_ledger_not_queried')
        self.assertEqual(value['budget_migration']['migrated_existing_envelope_usd'], 5.25)
        self.assertFalse(value['budget_migration']['new_credit_reserved_by_reporter'])
        record['migrated_usd'] = 7
        record['migration_sha256'] = local.digest({key: item for key, item in record.items() if key != 'migration_sha256'})
        local.write(self.output / 'migration.json', record)
        value = report.build(self.output, control_api=self.api)
        self.assertEqual(value['stage'], 'recovery_evidence_requires_reconciliation')
        self.assertTrue(all(job['accuracy_percent'] is None for job in value['jobs']))


if __name__ == '__main__': unittest.main()
