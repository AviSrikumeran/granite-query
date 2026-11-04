"""Synthetic mount fixtures and unchanged native protocol checks; no providers."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from cloud import modal_native_reasoning_v2 as worker
from cloud import test_modal_native_reasoning as old_tests


class MountTests(unittest.TestCase):
    def setUp(self):
        boundary = worker.ROOT/'runs/local_check_tmp'
        boundary.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=boundary)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.assertTrue(self.folder.resolve().is_relative_to(boundary.resolve()))
        self.volume = self.folder/'volume'; self.volume.mkdir()
        self.alias = self.folder/'artifacts'
        self.alias_patch = patch.object(worker, 'TRUSTED_ARTIFACT_ALIAS', self.alias)
        self.alias_patch.start(); self.addCleanup(self.alias_patch.stop)

    def link_directory(self, alias, target):
        self.assertTrue(alias.absolute().is_relative_to(self.folder.absolute()))
        self.assertTrue(target.resolve().is_relative_to(self.folder.resolve()))
        try:
            alias.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError):
            if os.name != 'nt':
                self.skipTest('Directory-link fixture unavailable')
            # Directory junctions need no symlink privilege on normal Windows.
            # Both literal paths are already checked inside this fixture root.
            subprocess.run(['cmd', '/c', 'mklink', '/J', str(alias), str(target)],
                capture_output=True, check=True)

    def test_only_fixed_mount_alias_is_resolved_and_observation_is_real(self):
        self.link_directory(self.alias, self.volume)
        with self.assertRaises(ValueError):
            worker.physical._no_links(self.alias)
        root, proof = worker.normalize_artifact_mount(self.alias)
        self.assertTrue(os.path.samefile(root, self.volume))
        self.assertEqual(proof['configured_alias'], str(self.alias))
        self.assertTrue(os.path.samefile(proof['canonical_root'], self.volume))
        self.assertIn(proof['configured_kind'], ('symlink', 'junction'))
        self.assertIsInstance(proof['readlink_target'], str)
        self.assertEqual(proof['configured_lstat']['inode'], self.alias.lstat().st_ino)
        self.assertFalse(proof['descendant_links_allowed'])
        self.assertFalse(proof['source_or_adapter_links_allowed'])
        self.assertFalse(proof['platform_mount_origin_independently_verified'])
        self.assertEqual(worker._safe(root, 'run01/status.json'), root/'run01/status.json')
        other = self.folder/'other'; self.link_directory(other, self.volume)
        with self.assertRaises(ValueError): worker.normalize_artifact_mount(other)

    def test_missing_file_or_filesystem_root_targets_fail_closed(self):
        with self.assertRaises(ValueError): worker.normalize_artifact_mount(self.alias)
        self.alias.write_bytes(b'not a mount')
        with self.assertRaises(ValueError): worker.normalize_artifact_mount(self.alias)
        self.alias.unlink(); self.alias.mkdir()
        root, proof = worker.normalize_artifact_mount(self.alias)
        self.assertEqual(root, self.alias.resolve()); self.assertEqual(proof['configured_kind'], 'directory')
        self.assertIsNone(proof['readlink_target'])
        with patch.object(worker.Path, 'is_dir', return_value=False):
            with self.assertRaises(ValueError): worker.normalize_artifact_mount(self.alias)
        with patch.object(worker.Path, 'resolve', return_value=Path(Path.cwd().anchor)):
            with self.assertRaises(ValueError): worker.normalize_artifact_mount(self.alias)

    def test_linked_ancestor_outside_alias_and_target_link_chain_rejected(self):
        real_parent = self.folder/'real_parent'; real_parent.mkdir()
        (real_parent/'artifacts').mkdir()
        linked_parent = self.folder/'linked_parent'; self.link_directory(linked_parent, real_parent)
        with patch.object(worker, 'TRUSTED_ARTIFACT_ALIAS', linked_parent/'artifacts'):
            with self.assertRaises(ValueError): worker.normalize_artifact_mount(linked_parent/'artifacts')
        second = self.folder/'second'; self.link_directory(second, self.volume)
        self.link_directory(self.alias, second)
        with self.assertRaises(ValueError): worker.normalize_artifact_mount(self.alias)

    def test_child_adapter_and_source_links_stay_forbidden(self):
        self.link_directory(self.alias, self.volume)
        root, _ = worker.normalize_artifact_mount(self.alias)
        target = self.folder/'other'; target.mkdir()
        for name in ('child', 'adapter', 'sources'):
            child = self.volume/name; self.link_directory(child, target)
            with self.subTest(name=name), self.assertRaises(ValueError):
                worker._safe(root, name+'/record.json')
            with self.subTest(name=name), self.assertRaises(ValueError):
                worker._write(child/'record.json', {'must_not_write': True})
        self.assertFalse((target/'record.json').exists())
        with self.assertRaises(ValueError): worker._safe(root, '../other/record.json')
        with self.assertRaises(ValueError): worker._safe(root, '/absolute/record.json')

    def test_mount_proof_precedes_any_tokenizer_or_model_and_uses_canonical_paths(self):
        self.link_directory(self.alias, self.volume)
        with patch.object(old_tests, 'worker', worker), old_tests.fixture() as (data, plan, dispatch, _), \
                patch.object(worker.modal, 'current_function_call_id', return_value='fc-INVENTED-v2'), \
                patch.object(worker.state, 'put', return_value=True), patch.object(worker.artifacts, 'commit'):
            runtime = worker.Runtime(root=self.alias)
            runtime.begin(data, plan, dispatch)
            self.assertTrue(runtime.owner_claimed)
            self.assertTrue(os.path.samefile(runtime.root, self.volume))
            self.assertTrue(os.path.samefile(runtime.folder, self.volume/plan['run_id']))
            proof = runtime.folder/'mount_verification.json'
            self.assertTrue(proof.is_file()); self.assertFalse(proof.is_symlink())
            self.assertFalse(hasattr(runtime, 'tokenizer')); self.assertFalse(hasattr(runtime, 'model'))

    def test_untrusted_root_returns_failed_pre_owner_result_without_write(self):
        with patch.object(old_tests, 'worker', worker), old_tests.fixture() as (data, plan, dispatch, _), \
                patch.object(worker.modal, 'current_function_call_id', return_value='fc-INVENTED-v2'), \
                patch.object(worker.state, 'put') as owner, patch.object(worker.artifacts, 'commit') as commit:
            runtime = worker.Runtime(root=self.folder/'not_the_alias')
            result = worker.run_once(data, plan, dispatch, runtime=runtime)
            self.assertEqual(result['stage'], 'failed'); self.assertTrue(result['pre_owner_failure'])
            self.assertFalse(result['evaluation_complete']); self.assertIsNone(result['metrics'])
            self.assertFalse(result['worker_terminal']['confirmed_terminal'])
            self.assertFalse(result['mount_verification']['validation_succeeded'])
            self.assertEqual(result['mount_verification']['failed_check'], 'configured_alias_identity')
            self.assertIsNone(result['mount_verification']['configured_lstat'])
            owner.assert_not_called(); commit.assert_not_called()
            self.assertFalse((self.folder/'not_the_alias').exists())

    def test_rejected_target_link_preserves_observed_diagnostics_without_execution(self):
        second = self.folder/'second'; self.link_directory(second, self.volume)
        self.link_directory(self.alias, second)
        with patch.object(old_tests, 'worker', worker), old_tests.fixture() as (data, plan, dispatch, _), \
                patch.object(worker.modal, 'current_function_call_id', return_value='fc-INVENTED-v2'), \
                patch.object(worker.state, 'put') as owner, patch.object(worker.artifacts, 'commit') as commit:
            runtime = worker.Runtime(root=self.alias)
            result = worker.run_once(data, plan, dispatch, runtime=runtime)
            proof = result['mount_verification']
            self.assertEqual(result['stage'], 'failed'); self.assertTrue(result['pre_owner_failure'])
            self.assertEqual(proof['failed_check'], 'raw_target_no_links')
            self.assertEqual(proof['configured_lstat']['inode'], self.alias.lstat().st_ino)
            self.assertEqual(proof['readlink_target_sha256'], worker._sha(os.fsencode(os.readlink(self.alias))))
            self.assertIsInstance(proof['readlink_target'], str)
            self.assertFalse(proof['validation_succeeded']); self.assertIsNone(proof['canonical_root'])
            self.assertFalse(proof['raw_ancestors_and_target_have_no_other_links'])
            self.assertFalse(hasattr(runtime, 'tokenizer')); self.assertFalse(hasattr(runtime, 'model'))
            owner.assert_not_called(); commit.assert_not_called()
            self.assertFalse((self.volume/plan['run_id']).exists())


class V2ProtocolTests(old_tests.NativeWorkerTests):
    """Run original mask/window/raw/scoring fixtures against the new module."""
    def setUp(self):
        self.legacy_patch = patch.object(old_tests, 'worker', worker)
        self.legacy_patch.start(); self.addCleanup(self.legacy_patch.stop)

    def test_version_and_source_inventory_are_separate(self):
        self.assertEqual(worker.VERSION, 'native-reasoning-worker-mount-v2')
        self.assertIn('modal_native_reasoning_v2.py', worker.REQUIRED_SOURCES)
        self.assertNotIn('modal_native_reasoning.py', worker.REQUIRED_SOURCES)

    def test_duplicate_owner_or_existing_artifacts_block_execution(self):
        boundary = worker.ROOT/'runs/local_check_tmp'; boundary.mkdir(parents=True, exist_ok=True)
        with old_tests.fixture() as (data, plan, dispatch, _), tempfile.TemporaryDirectory(dir=boundary) as temporary:
            alias = Path(temporary)/'artifacts'; alias.mkdir()
            with patch.object(worker, 'TRUSTED_ARTIFACT_ALIAS', alias), \
                    patch.object(worker.modal, 'current_function_call_id', return_value='fc-INVENTED-owner'):
                runtime = worker.Runtime(root=alias)
                with patch.object(worker.state, 'put', return_value=False):
                    with self.assertRaises(ValueError): runtime.begin(data, plan, dispatch)
                self.assertFalse((alias/plan['run_id']).exists())
                (alias/plan['run_id']).mkdir()
                with patch.object(worker.state, 'put') as put:
                    with self.assertRaises(ValueError): runtime.begin(data, plan, dispatch)
                    put.assert_not_called()


if __name__ == '__main__': unittest.main()
