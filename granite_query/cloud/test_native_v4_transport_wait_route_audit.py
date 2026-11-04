"""Independent historical/fresh boundary and real argv composition fixtures."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from cloud import native_v4_transport_wait_v2 as wait


class WaitRouteAuditTests(unittest.TestCase):
    def setUp(self):
        parent = wait.control.ROOT/'runs/local_check_tmp'
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent); self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)/'INVENTED_study'
        self.folder = self.output/'arms/INVENTED_run'; self.folder.mkdir(parents=True)
        self.assertTrue(self.folder.resolve().is_relative_to(parent.resolve()))
        for name in ('transport_wait_review_v2.json',):
            wait.control.write(self.output/name, {'fixture': True})
        for name in ('transport_repair_intent.json', 'dispatch.json'):
            wait.control.write(self.folder/name, {'fixture': True})

    def evidence(self, stamp):
        return {'run_id':'INVENTED_run','observed_at_utc':stamp.isoformat(),
            'actual_remote_owner':None,'actual_remote_progress':None,
            'volume':{'exists':False,'provider_exception':'NotFoundError'},
            'old_processes':[None,None],
            'apps':[{'app_id':'ap-OLD','state':'stopped','tasks':'0'}]}

    def test_cpu_delay_does_not_relabel_valid_original_evidence_as_fresh(self):
        observed = datetime.now(timezone.utc)-timedelta(seconds=600)
        evidence = self.evidence(observed); job = {'run_id':'INVENTED_run'}
        intent = {'created_at_utc':(observed+timedelta(seconds=30)).isoformat()}
        wait.validate_historical_absence(evidence, job, intent)
        with self.assertRaises(ValueError): wait.base._fresh_absence(evidence, job)
        # A new observation, not the historical receipt, satisfies final TTL.
        wait.base._fresh_absence(self.evidence(datetime.now(timezone.utc)), job)

    def test_historical_timing_and_unknown_transmission_still_fail_closed(self):
        observed = datetime.now(timezone.utc)-timedelta(seconds=600)
        evidence = self.evidence(observed); job = {'run_id':'INVENTED_run'}
        for seconds in (-1, 121):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                wait.validate_historical_absence(evidence, job,
                    {'created_at_utc':(observed+timedelta(seconds=seconds)).isoformat()})
        intent = {'created_at_utc':(observed+timedelta(seconds=30)).isoformat()}
        for key,value in (('actual_remote_owner',{'call_id':'fc-INVENTED'}),
                ('volume',{'exists':False,'provider_exception':'PermissionDenied'}),
                ('old_processes',[None,{'pid':202}])):
            changed=deepcopy(evidence); changed[key]=value
            with self.subTest(key=key), self.assertRaises(ValueError):
                wait.validate_historical_absence(changed, job, intent)

    def test_actual_backend_has_bounded_local900_wait_and_correct_cli_routes(self):
        for repair in (False,True):
            expected_module = wait.REPAIR_CLI if repair else wait.NORMAL_CLI
            process = SimpleNamespace(returncode=0, stdout=b'INVENTED ap-LOCAL\n', stderr=b'')
            with patch.object(wait, 'validate_wait_review', return_value={'fixture':True}), \
                    patch.object(subprocess,'run',return_value=process) as run:
                wait.WaitBackend().run_cli(self.folder, repair=repair)
            run.assert_called_once()
            self.assertEqual(run.call_args.args[0], [sys.executable,'-m','modal','run','--detach',
                '-m',expected_module,'--folder',str(self.folder)])
            self.assertEqual(run.call_args.kwargs['timeout'],900)
            self.assertFalse(run.call_args.kwargs.get('shell',False))
            self.assertEqual(run.call_args.kwargs['env']['MODAL_IMAGE_BUILDER_VERSION'],'2025.06')
            self.assertNotIn('cloud.modal_native_launch_v3',run.call_args.args[0])
        self.assertEqual(wait.NORMAL_CLI,'cloud.modal_native_batch_launch_v4')
        self.assertEqual(wait.REPAIR_CLI,'cloud.modal_native_v4_transport_wait_v2::repair_launch_v2')

    def test_repair_policy_claim_is_durable_before_any_subprocess(self):
        target=self.folder/'transport_wait_policy_claim_v2.json'
        def process(*args,**kwargs):
            self.assertTrue(target.is_file())
            claim=wait.control.read(target)
            self.assertEqual(claim['local_cli_wait_seconds'],900)
            self.assertEqual(claim['base_intent_sha256'],wait.control.sha(self.folder/'transport_repair_intent.json'))
            self.assertFalse(claim['new_reservation_created'])
            return SimpleNamespace(returncode=0,stdout=b'INVENTED\n',stderr=b'')
        with patch.object(wait,'validate_wait_review',return_value={'fixture':True}), \
                patch.object(subprocess,'run',side_effect=process) as run:
            wait.WaitBackend().run_cli(self.folder,repair=True)
        run.assert_called_once()

    def test_unique_v2_entrypoint_uses_unchanged_frozen_worker_and_gpu_bounds(self):
        first=importlib.import_module('cloud.modal_native_v4_transport_launch')
        second=importlib.import_module('cloud.modal_native_v4_transport_wait_v2')
        worker=importlib.import_module('cloud.modal_native_reasoning_batch_v4')
        self.assertIs(first.app,second.app); self.assertIs(second.app,worker.app)
        self.assertTrue(hasattr(second,'repair_launch_v2'))
        self.assertEqual(worker.RESOURCES['timeout'],1800)
        self.assertEqual(worker.RESOURCES['retries'],0)
        self.assertEqual(worker.contract.protocol()['max_new_tokens'],2048)

    def test_future_advance_selects_wait_backend_without_changing_frozen_controller(self):
        advance=Mock(return_value={'stage':'INVENTED_no_action'})
        controller=Mock(return_value=SimpleNamespace(advance=advance))
        with patch.object(wait,'validate_wait_review',return_value={'fixture':True}), \
                patch.object(wait.control,'Controller',controller):
            wait.safe_advance(self.output)
        self.assertIsInstance(controller.call_args.args[1],wait.WaitBackend)
        advance.assert_called_once_with()


if __name__ == '__main__': unittest.main()
