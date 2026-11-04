"""Synthetic batch32 publication gates; no actual run, provider or ledger I/O."""
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

from cloud import native_reasoning_batch_report_v4 as report
from cloud import native_reasoning_batch_contract_v4 as contract
from cloud import test_native_reasoning_recovery_report as fixtures
from cloud import native_reasoning_control as local


class BatchReportTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RecoveryReportTests(methodName='runTest')
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.root, self.output, self.api = self.fixture.root, self.fixture.output, self.fixture.api
        self.fixture.stack.enter_context(patch.object(report,'PUBLIC',self.root/'public'))
        self.fixture.stack.enter_context(patch.object(report,'DOCS',self.root/'docs'))
        self.fixture.stack.enter_context(patch.object(report,'paired',return_value={'count':200,'difference_percentage_points':0}))
        self.parent = {'status':'completed','call_id':'fc-INVENTED-completed-V3','validated_outputs':200,
            'runtime_infeasible':True,'result_sha256':'a'*64,'calibration_sha256':'b'*64,'accuracy_used_as_gate':False}
        self.api.parent_for_report = Mock(side_effect=lambda output:deepcopy(self.parent))
        self.funding = {'version':'native-reasoning-completed-parent-batch-funding-v4',
            'transferred_unused_usd':3.5,'additional_new_reservation_usd':1.75,'funded_envelope_usd':5.25,
            'new_reservation_created':True,'total_commitment_increase_usd':1.75,'parent_validated_outputs':200,
            'parent_runtime_infeasible':True,'new_batch_size':32,'new_max_new_tokens':contract.protocol()['max_new_tokens'],
            'accuracy_used_as_gate':False,'created_at_utc':'2026-11-04T04:00:00+00:00'}
        self.funding['funding_sha256'] = local.digest(self.funding)
        self.api.funding_record_for_report = Mock(side_effect=lambda output,stamp:deepcopy(self.funding))

    def prepare(self, completed=()):
        self.fixture.prepare_original(); self.fixture.prepare_jobs(completed=completed)
        for job in self.fixture.jobs:
            plan = job['plan']; settings = contract.protocol()
            plan.update({key:settings[key] for key in ('evaluation_batch_size','evaluation_batch_count','evaluation_partition',
                'max_new_tokens','enable_thinking','input_limit')})
            plan['protocol_hash'] = local.digest({key:value for key,value in plan.items() if key!='protocol_hash'})
            if job['role'] not in completed: continue
            folder = job['folder_path']
            dispatch = local.read(folder/'dispatch.json'); dispatch['plan_sha256'] = local.digest(plan)
            dispatch['intent_sha256'] = local.digest({key:value for key,value in dispatch.items() if key!='intent_sha256'})
            local.write(folder/'dispatch.json',dispatch)
            launch = local.read(folder/'launch.json'); launch['intent_sha256'] = dispatch['intent_sha256']
            local.write(folder/'launch.json',launch)
            result = local.read(folder/'result.json')
            result.update(plan=plan,protocol_hash=plan['protocol_hash'],dispatch=dispatch,dispatch_sha256=local.digest(dispatch),
                raw_batches=[{'start':start,'stop':stop,'sha256':local.digest({'invented_start':start})}
                    for start,stop in contract.evaluation_batches()],cuda_memory=None)
            local.write(folder/'result.json',result)
            proof = local.read(folder/'raw_validation.json'); proof.update(raw_batches_verified=7,dispatch_sha256=local.digest(dispatch))
            local.write(folder/'raw_validation.json',proof)
            terminal = local.read(folder/'provider_terminal.json')
            terminal.update(intent_sha256=dispatch['intent_sha256'],result_sha256=local.sha(folder/'result.json'),
                raw_validation_sha256=local.sha(folder/'raw_validation.json'))
            local.write(folder/'provider_terminal.json',terminal)

    def test_default_read_only_and_planned_funding_do_not_claim_execution(self):
        before = set(self.root.rglob('*'))
        value = report.build(self.output,control_api=self.api)
        self.assertEqual(value['stage'],'batch32_unprepared')
        self.assertEqual(set(self.root.rglob('*')),before)
        self.assertTrue(all(job['accuracy_percent'] is None for job in value['jobs']))
        self.assertEqual(value['funding']['status'],'planned_not_verified')
        self.assertEqual(value['protocol']['max_new_tokens'],2048)
        self.assertIsNone(value['completed_parent']['execution_failed'])

    def test_completed_parent_is_successful_evaluation_with_failed_runtime_gate(self):
        self.prepare()
        value = report.build(self.output,control_api=self.api)
        self.assertTrue(value['completed_parent']['evaluation_completed'])
        self.assertFalse(value['completed_parent']['execution_failed'])
        self.assertFalse(value['completed_parent']['runtime_gate_passed'])
        self.assertFalse(value['completed_parent']['model_quality_gain_claimed'])
        for field,wrong in (('status','failed'),('validated_outputs',199),('runtime_infeasible',False),('accuracy_used_as_gate',True)):
            original = deepcopy(self.parent); self.parent[field] = wrong
            value = report.build(self.output,control_api=self.api)
            self.assertEqual(value['stage'],'batch32_evidence_requires_reconciliation')
            self.assertTrue(all(job['accuracy_percent'] is None for job in value['jobs']))
            self.parent = original

    def test_seven_raw_proof_required_25_batch_or_tail_tamper_never_scores(self):
        self.prepare(completed=report.common.ROLES)
        value = report.build(self.output,control_api=self.api)
        self.assertEqual(value['stage'],'batch32_all_three_completed_and_validated')
        self.assertEqual(len(value['comparisons']),3)
        self.assertEqual(value['jobs'][0]['raw_batches_verified'],7)
        folder = self.fixture.jobs[0]['folder_path']
        proof = local.read(folder/'raw_validation.json'); proof['raw_batches_verified'] = 25
        local.write(folder/'raw_validation.json',proof)
        terminal = local.read(folder/'provider_terminal.json'); terminal['raw_validation_sha256'] = local.sha(folder/'raw_validation.json')
        local.write(folder/'provider_terminal.json',terminal)
        value = report.build(self.output,control_api=self.api)
        self.assertIsNone(value['jobs'][0]['accuracy_percent']); self.assertIsNone(value['comparisons'])
        proof['raw_batches_verified'] = 7; local.write(folder/'raw_validation.json',proof)
        result = local.read(folder/'result.json'); result['raw_batches'][-1]['stop'] = 199
        local.write(folder/'result.json',result)
        terminal.update(raw_validation_sha256=local.sha(folder/'raw_validation.json'),result_sha256=local.sha(folder/'result.json'))
        local.write(folder/'provider_terminal.json',terminal)
        self.assertIsNone(report.build(self.output,control_api=self.api)['jobs'][0]['accuracy_percent'])

    def test_actual_funding_receipt_distinguishes_new_reservation_and_cap(self):
        self.prepare(); local.write(self.output/'funding.json',self.funding)
        value = report.build(self.output,control_api=self.api)
        self.assertEqual(value['funding']['status'],'actual_receipt_verified_ledger_not_queried')
        self.assertEqual(value['funding']['transferred_existing_unused_usd'],3.5)
        self.assertEqual(value['funding']['additional_new_reservation_usd'],1.75)
        self.assertTrue(value['funding']['new_reservation_created']); self.assertFalse(value['funding']['additional_cash_claimed'])
        changed = deepcopy(self.funding); changed['new_max_new_tokens'] = 1024
        local.write(self.output/'funding.json',changed)
        self.assertEqual(report.build(self.output,control_api=self.api)['stage'],'batch32_evidence_requires_reconciliation')

    def test_optional_memory_none_does_not_hide_valid200_metrics(self):
        self.prepare(completed=('baseline',))
        value = report.build(self.output,control_api=self.api)
        self.assertEqual(value['jobs'][0]['accuracy_percent'],100)
        self.assertTrue(all(job['accuracy_percent'] is None for job in value['jobs'][1:]))
        self.assertIsNone(value['comparisons'])
        self.assertTrue(value['protocol']['memory_telemetry_optional'])

    def test_explicit_four_outputs_preserve_all_canonical_history(self):
        self.prepare()
        report.PUBLIC.mkdir(); report.DOCS.mkdir()
        originals = ['NATIVE_REASONING_STUDY','NATIVE_REASONING_RECOVERY','NATIVE_REASONING_CONFIG_RECOVERY']
        for name in originals:
            for extension in ('json','md'): (report.PUBLIC/f'{name}.{extension}').write_bytes(('HISTORY '+name).encode())
        for name in ('native-reasoning-recovery.json','native-reasoning-config-recovery.json'):
            (report.DOCS/name).write_bytes(('HISTORY '+name).encode())
        before = {path.relative_to(self.root):path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        report.build(self.output,write=True,control_api=self.api)
        after = {path.relative_to(self.root):path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        changed = {path.as_posix() for path,raw in after.items() if before.get(path)!=raw}
        self.assertEqual(changed,{'public/NATIVE_REASONING_BATCH32_V4.json','public/NATIVE_REASONING_BATCH32_V4.md',
            'docs/native-reasoning-batch32-v4.json','docs/native-reasoning-study.json'})
        view = local.read(report.DOCS/'native-reasoning-study.json')
        self.assertEqual(view['source_report'],'native-reasoning-batch32-v4.json')
        self.assertTrue(view['derived_current_study_view']); self.assertFalse(view['provider_export'])
        self.assertEqual(view['source_report_sha256'],local.sha(report.DOCS/'native-reasoning-batch32-v4.json'))
        self.assertEqual(len(view['historical_reports']),3)
        for private in ('PRIVATE QUESTION','PRIVATE TEACHER REASONING','PRIVATE ERROR TEXT',str(self.root)):
            self.assertNotIn(private,str(view))


if __name__=='__main__': unittest.main()
