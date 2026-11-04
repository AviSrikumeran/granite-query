"""Offline launcher preflight boundaries; never invokes a provider or model."""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cloud import native_reasoning_control as control
from cloud import modal_native_reasoning as worker
from cloud import modal_native_launch as launcher


class NativeLaunchTests(unittest.TestCase):
    def setUp(self):
        parent = control.PRIVATE / 'local_check_tmp'; parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output, self.state = self.root / 'launch_fixture', self.root / 'state'
        self.state.mkdir(); self.output.mkdir()
        self.sources = {name: 'a' * 64 for name in control.SOURCES}
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(control, 'STATE', self.state))
        self.stack.enter_context(patch.object(control, 'load_jobs', side_effect=lambda output: [self.job]))
        self.stack.enter_context(patch.object(control, 'source_inventory', side_effect=lambda: dict(self.sources)))
        self.stack.enter_context(patch.object(control, 'review', side_effect=lambda output, phase: control.read(output / f'review_{phase}.json')))
        self.funding = self.stack.enter_context(patch.object(control, 'fresh_funding', return_value=None))
        self.source_check = self.stack.enter_context(patch.object(worker, 'verify_sources', return_value={'fixture_only': True}))
        self.calibration = self.stack.enter_context(patch.object(control.Controller, 'calibrate', return_value={'pair_runtime_feasible': True}))
        control.write(self.output / 'design.json', {'fixture': 'No real protocol or source dataset'})
        control.write(self.output / 'study_manifest.json', {'fixture': 'No real study inputs'})
        control.write(self.output / 'calibration.json', {'fixture': 'Invented measured baseline proof'})
        self.reset('baseline')

    def reset(self, role):
        self.role = role
        self.folder = self.output / 'arms' / ('INVENTED_' + role)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.plan = {'run_id': self.folder.name, 'arm': role}
        self.data = {'fixture': 'No actual question or target bytes'}
        self.job = {'role': role, 'run_id': self.folder.name, 'plan': self.plan,
                    'data': self.data, 'folder_path': self.folder}
        phase = 'baseline' if role == 'baseline' else 'pair'
        review = {'study_manifest_sha256': control.sha(self.output / 'study_manifest.json')}
        if phase == 'pair': review['calibration_sha256'] = control.sha(self.output / 'calibration.json')
        control.write(self.output / f'review_{phase}.json', review)
        self.bind_dispatch()
        self.owner = {'pid': 12345, 'claim_id': self.dispatch['claim_id']}
        control.write(self.folder / 'controller_owner.json', self.owner)
        (self.state / 'gpu_launch.lock').write_text('12345', encoding='ascii')
        self.ledger = {'limits': {'modal': 30}, 'estimated_spend': {'modal': 12},
            'reserved': {'modal': 7}, 'jobs': [
                {'run_id': self.output.name + '-envelope', 'service': 'modal',
                 'status': 'reserved', 'reserved_usd': 5.25},
                {'run_id': self.job['run_id'], 'service': 'modal', 'status': 'spawning',
                 'reserved_usd': 1.75, 'native_claim_id': self.dispatch['claim_id'],
                 'native_intent_sha256': self.dispatch['intent_sha256'],
                 'native_design_sha256': control.sha(self.output / 'design.json'),
                 'native_envelope_parent': self.output.name + '-envelope'}]}
        self.save_ledger()

    def bind_dispatch(self):
        phase = 'baseline' if self.role == 'baseline' else 'pair'
        self.dispatch = control.make_dispatch(self.plan, self.data, self.sources,
            control.sha(self.output / f'review_{phase}.json'), claim_id='b' * 32)
        control.write(self.folder / 'dispatch.json', self.dispatch)
        if hasattr(self, 'ledger') and self.ledger['jobs'][-1]['run_id'] == self.job['run_id']:
            self.ledger['jobs'][-1]['native_intent_sha256'] = self.dispatch['intent_sha256']
            self.save_ledger()

    def save_ledger(self): control.write(self.state / 'budget.json', self.ledger)

    def test_accepts_correct_fully_bound_baseline_and_pair_without_provider(self):
        for role in ('baseline', 'concise', 'thinking'):
            self.reset(role)
            job, dispatch = launcher.preflight(self.folder)
            self.assertEqual(job, self.job); self.assertEqual(dispatch, self.dispatch)
        self.assertEqual(self.funding.call_count, 3)
        self.assertEqual(self.source_check.call_count, 3)
        self.assertEqual(self.calibration.call_count, 2)
        self.assertFalse(any(self.output.rglob('cli_spawn_started.json')))
        self.assertFalse(any(self.output.rglob('launch.json')))

    def test_rejects_missing_or_foreign_parent_gpu_lease_and_owner_claim(self):
        lease = self.state / 'gpu_launch.lock'
        lease.unlink()
        with self.assertRaises((ValueError, OSError)): launcher.preflight(self.folder)
        lease.write_text('99999', encoding='ascii')
        with self.assertRaises(ValueError): launcher.preflight(self.folder)
        lease.write_text('12345', encoding='ascii')
        control.write(self.folder / 'controller_owner.json', dict(self.owner, claim_id='c' * 32))
        with self.assertRaises(ValueError): launcher.preflight(self.folder)
        self.source_check.assert_not_called()

    def test_existing_cli_marker_or_ack_never_passes_preflight(self):
        for filename in ('cli_spawn_started.json', 'launch.json'):
            path = self.folder / filename
            control.write(path, {'fixture': 'Prior ambiguous or acknowledged transmission'})
            with self.subTest(filename=filename), self.assertRaises(ValueError): launcher.preflight(self.folder)
            path.unlink()
        self.source_check.assert_not_called()

    def test_rejects_foreign_child_claim_intent_design_amount_status_and_service(self):
        original = deepcopy(self.ledger)
        cases = [('native_claim_id', 'c' * 32), ('native_intent_sha256', 'd' * 64),
            ('native_design_sha256', 'e' * 64), ('reserved_usd', 1.74), ('reserved_usd', 7),
            ('status', 'reserved'), ('status', 'spawned'), ('status', 'completed'), ('service', 'deepseek')]
        for field, value in cases:
            self.ledger = deepcopy(original); self.ledger['jobs'][-1][field] = value; self.save_ledger()
            with self.subTest(field=field, value=value), self.assertRaises(ValueError): launcher.preflight(self.folder)
        self.ledger = deepcopy(original); self.ledger['jobs'].append(deepcopy(self.ledger['jobs'][-1])); self.save_ledger()
        with self.assertRaises(ValueError): launcher.preflight(self.folder)

    def test_foreign_active_unknown_and_protected_five_dollars_block(self):
        original = deepcopy(self.ledger)
        for status in ('running', 'spawning', 'queued', 'unknown'):
            self.ledger = deepcopy(original)
            self.ledger['jobs'].append({'run_id': 'foreign_gpu', 'service': 'modal', 'status': status, 'reserved_usd': 1})
            self.save_ledger()
            with self.subTest(status=status), self.assertRaises(ValueError): launcher.preflight(self.folder)
        self.ledger = deepcopy(original); self.ledger['estimated_spend']['modal'] = 18
        self.save_ledger(); launcher.preflight(self.folder)  # Exactly 5 remains.
        self.ledger['estimated_spend']['modal'] = 18.01; self.save_ledger()
        with self.assertRaises(ValueError): launcher.preflight(self.folder)
        self.funding.side_effect = ValueError('INVENTED unsupported/stale funding')
        with self.assertRaises(ValueError): launcher.preflight(self.folder)

    def test_exact_dispatch_source_hash_and_phase_manifest_review_are_required(self):
        original = deepcopy(self.dispatch)
        changed = deepcopy(original); changed['input_sha256'] = 'e' * 64
        changed['intent_sha256'] = control.digest({key: value for key, value in changed.items() if key != 'intent_sha256'})
        control.write(self.folder / 'dispatch.json', changed)
        with self.assertRaises(ValueError): launcher.preflight(self.folder)
        control.write(self.folder / 'dispatch.json', original)
        self.sources['native_reasoning_control.py'] = 'f' * 64
        with self.assertRaises(ValueError): launcher.preflight(self.folder)
        self.sources['native_reasoning_control.py'] = 'a' * 64
        review = control.read(self.output / 'review_baseline.json')
        review['study_manifest_sha256'] = '0' * 64
        control.write(self.output / 'review_baseline.json', review); self.bind_dispatch()
        with self.assertRaises(ValueError): launcher.preflight(self.folder)

    def test_pair_needs_measured_feasible_calibration_and_exact_calibration_hash(self):
        self.reset('thinking')
        self.calibration.return_value = {'pair_runtime_feasible': False}
        with self.assertRaises(ValueError): launcher.preflight(self.folder)
        self.calibration.return_value = {'pair_runtime_feasible': True}
        control.write(self.output / 'calibration.json', {'fixture': 'Changed after review'})
        with self.assertRaises(ValueError): launcher.preflight(self.folder)
        self.reset('thinking')
        self.source_check.side_effect = ValueError('INVENTED physical packaged-source mismatch')
        with self.assertRaises(ValueError): launcher.preflight(self.folder)


if __name__ == '__main__': unittest.main()
