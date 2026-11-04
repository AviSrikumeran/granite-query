"""Independent transport composition checks; no provider or experiment IO.

The original controller is intentionally frozen with its diagnosed bad route.
These checks exercise the separately reviewed transport instead of pretending
that the frozen controller was edited or its previous attempt was dispatched.
"""
import importlib
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class TransportRouteAuditTests(unittest.TestCase):
    def setUp(self):
        self.transport = importlib.import_module('cloud.native_v4_transport')
        self.control = importlib.import_module('cloud.native_reasoning_batch_control_v4')
        parent = self.control.ROOT/'runs/local_check_tmp'
        parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name).resolve()/'INVENTED folder with spaces'
        self.folder.mkdir()
        self.assertTrue(self.folder.is_relative_to(parent.resolve()))

    def expected_args(self, module):
        return [sys.executable, '-m', 'modal', 'run', '--detach', '-m',
            module, '--folder', str(self.folder)]

    def test_fresh_route_factory_composes_the_correct_frozen_cli(self):
        self.assertEqual(self.transport.NORMAL_CLI, 'cloud.modal_native_batch_launch_v4')
        args = self.transport.launch_args(self.folder)
        self.assertEqual(args, self.expected_args(self.transport.NORMAL_CLI))
        self.assertNotIn('cloud.modal_native_launch_v3', args)
        self.assertNotIn(self.transport.REPAIR_CLI, args)

    def test_repair_route_is_the_explicit_delegation_cli_only(self):
        self.assertEqual(self.transport.REPAIR_CLI,
            'cloud.modal_native_v4_transport_launch::repair_launch')
        args = self.transport.launch_args(self.folder, repair=True)
        self.assertEqual(args, self.expected_args(self.transport.REPAIR_CLI))
        self.assertNotIn('cloud.modal_native_launch_v3', args)
        self.assertNotIn(self.transport.NORMAL_CLI, args)

    def test_actual_future_backend_subprocess_uses_factory_and_preserves_folder(self):
        completed = SimpleNamespace(returncode=0,
            stdout=b'INVENTED local transport app ap-INVENTED\n', stderr=b'')
        # Only the synthetic study review is stubbed. The actual backend,
        # command factory and subprocess boundary are exercised together.
        with patch.object(self.transport, 'validate_transport_review', return_value={}), \
                patch.object(subprocess, 'run', return_value=completed) as run:
            self.transport.TransportBackend().launch(self.folder)
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], self.expected_args(self.transport.NORMAL_CLI))
        self.assertEqual(run.call_args.kwargs['cwd'], self.control.ROOT.parent)
        env = run.call_args.kwargs['env']
        self.assertEqual(env['PYTHONIOENCODING'], 'utf-8')
        self.assertEqual(env['PYTHONUTF8'], '1')
        self.assertEqual(env['MODAL_IMAGE_BUILDER_VERSION'], '2025.06')
        self.assertFalse(run.call_args.kwargs.get('shell', False))

    def test_correct_cli_is_bound_to_the_actual_batch32_output2048_worker(self):
        cli = importlib.import_module(self.transport.NORMAL_CLI)
        worker = importlib.import_module('cloud.modal_native_reasoning_batch_v4')
        self.assertIs(cli.worker, worker)
        self.assertIs(cli.app, worker.app)
        self.assertEqual(worker.contract.protocol()['evaluation_batch_size'], 32)
        self.assertEqual(worker.contract.protocol()['max_new_tokens'], 2048)
        self.assertIn('modal_native_reasoning_batch_v4.py', worker.REQUIRED_SOURCES)

    def test_repair_cli_imports_after_normal_cli_without_duplicate_entrypoint(self):
        normal = importlib.import_module(self.transport.NORMAL_CLI)
        repair = importlib.import_module('cloud.modal_native_v4_transport_launch')
        self.assertIs(repair.app, normal.app)
        self.assertTrue(hasattr(repair, 'repair_launch'))
        self.assertNotEqual(repair.repair_launch, normal.launch)

    def test_future_advance_injects_correct_backend_before_frozen_controller(self):
        from unittest.mock import Mock
        advance = Mock(return_value={'stage': 'INVENTED_no_paid_action'})
        controller = Mock(return_value=SimpleNamespace(advance=advance))
        with patch.object(self.transport, 'validate_transport_review', return_value={}), \
                patch.object(self.control, 'Controller', controller):
            result = self.transport.safe_advance(self.folder)
        self.assertEqual(result, {'stage': 'INVENTED_no_paid_action'})
        controller.assert_called_once()
        self.assertEqual(controller.call_args.args[0], self.folder)
        self.assertIsInstance(controller.call_args.args[1], self.transport.TransportBackend)
        advance.assert_called_once_with()

    def test_realistic_direct_or_single_venv_redirector_ancestry_is_bounded(self):
        launcher = str(self.folder/'venv/Scripts/python.exe')
        driver = {'pid':101, 'parent_pid':99, 'creation_utc':'2026-11-04T00:00:00+00:00',
            'executable_path':str(self.folder/'base/python.exe')}
        cli = {'pid':303, 'parent_pid':101, 'creation_utc':'2026-11-04T00:00:02+00:00',
            'executable_path':str(self.folder/'base/python.exe')}
        self.assertEqual(self.transport.validate_cli_ancestry(driver, cli, None, launcher)['depth'], 1)
        cli['parent_pid'] = 202
        redirector = {'pid':202, 'parent_pid':101, 'creation_utc':'2026-11-04T00:00:01+00:00',
            'executable_path':launcher}
        self.assertEqual(self.transport.validate_cli_ancestry(driver, cli, redirector, launcher)['depth'], 2)
        for changed in (dict(redirector, parent_pid=404),
                dict(redirector, executable_path=str(self.folder/'unrelated/python.exe')),
                dict(redirector, creation_utc='2026-11-03T23:59:59+00:00')):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.transport.validate_cli_ancestry(driver, cli, changed, launcher)
        with self.assertRaises(ValueError):
            self.transport.validate_cli_ancestry(driver,
                dict(cli, creation_utc='2026-11-03T23:59:59+00:00'), redirector, launcher)

    def test_running_transport_app_must_match_exact_self_id_and_have_zero_tasks(self):
        apps = [{'app_id':'ap-OLD', 'state':'stopped', 'tasks':'0'},
            {'app_id':'ap-SELF', 'state':'ephemeral', 'tasks':'0'}]
        self.transport._zero_apps(apps, own_app_id='ap-SELF')
        with self.assertRaises(ValueError): self.transport._zero_apps(apps)
        with self.assertRaises(ValueError):
            self.transport._zero_apps([{'state':'ephemeral', 'tasks':'0'}])
        with self.assertRaises(ValueError): self.transport._zero_apps(apps, own_app_id='ap-OTHER')
        active = deepcopy(apps); active[1]['tasks'] = '1'
        with self.assertRaises(ValueError): self.transport._zero_apps(active, own_app_id='ap-SELF')
        foreign = deepcopy(apps); foreign.append({'app_id':'ap-FOREIGN', 'state':'running', 'tasks':'0'})
        with self.assertRaises(ValueError): self.transport._zero_apps(foreign, own_app_id='ap-SELF')

    def test_self_app_exception_does_not_relax_never_transmitted_proof(self):
        evidence = {'run_id':'INVENTED_run', 'observed_at_utc':datetime.now(timezone.utc).isoformat(),
            'actual_remote_owner':None, 'actual_remote_progress':None,
            'volume':{'exists':False, 'provider_exception':'NotFoundError'}, 'old_processes':[None,None],
            'apps':[{'app_id':'ap-SELF', 'state':'ephemeral', 'tasks':'0'}]}
        job = {'run_id':'INVENTED_run'}
        self.transport._fresh_absence(evidence, job, own_app_id='ap-SELF')
        for key,value in (('actual_remote_owner', {'call_id':'fc-INVENTED'}),
                ('actual_remote_progress', {'stage':'started'}),
                ('volume', {'exists':False,'provider_exception':'PermissionDenied'}),
                ('old_processes', [None, {'pid':202}])):
            changed = deepcopy(evidence); changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.transport._fresh_absence(changed, job, own_app_id='ap-SELF')


if __name__ == '__main__':
    unittest.main()
