"""Synthetic mount fixtures and unchanged native protocol checks; no providers."""
from pathlib import Path
import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from cloud import modal_native_reasoning_v3 as worker
from cloud import test_modal_native_reasoning as old_tests
from cloud import modal_native_reasoning_v2 as prior


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


class V3ProtocolTests(old_tests.NativeWorkerTests):
    """Run original mask/window/raw/scoring fixtures against the new module."""
    def setUp(self):
        self.legacy_patch = patch.object(old_tests, 'worker', worker)
        self.legacy_patch.start(); self.addCleanup(self.legacy_patch.stop)

    def test_version_and_source_inventory_are_separate(self):
        self.assertEqual(worker.VERSION, 'native-reasoning-worker-official-config-v3')
        self.assertIn('modal_native_reasoning_v3.py', worker.REQUIRED_SOURCES)
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


class OfficialConfigTests(unittest.TestCase):
    """Real saved public metadata only; all expensive/runtime IO is synthetic."""
    def setUp(self):
        self.raw = (worker.ROOT/'runs/supervisor/observed_pinned_config.original.json').read_bytes()
        boundary = worker.ROOT/'runs/local_check_tmp'; boundary.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=boundary); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.assertTrue(self.root.is_relative_to(boundary.resolve()))

    def runtime(self):
        runtime = object.__new__(worker.Runtime)
        runtime.root = self.root; runtime.folder = self.root/'INVENTED_native'; runtime.folder.mkdir()
        runtime.plan = {'run_id': runtime.folder.name, 'arm': 'baseline'}
        runtime.dispatch = {'intent_sha256': 'a'*64}; runtime.call_id = 'fc-INVENTED-v3'
        runtime.started = time.monotonic(); runtime.owner_claimed = True; runtime.error_artifacts = []
        return runtime

    def test_exact_official_metadata_and_semantically_equal_reformat_are_distinct(self):
        self.assertEqual((len(self.raw), hashlib.sha256(self.raw).hexdigest()),
            (905, worker.OFFICIAL_RAW_CONFIG_SHA))
        proof = worker.validate_official_model_config(self.raw)
        self.assertTrue(proof['official_raw_byte_identity_verified'])
        self.assertFalse(proof['runtime_model_load_verified'])
        self.assertEqual(proof['geometry']['value_output_size'], 512)
        historical = (worker.ROOT/'runs/supervisor/pinned_model_config.json').read_bytes()
        self.assertEqual(json.loads(self.raw), json.loads(historical))
        self.assertNotEqual(hashlib.sha256(historical).hexdigest(), worker.OFFICIAL_RAW_CONFIG_SHA)
        for bad in (historical, self.raw+b'\n', self.raw.replace(b'\n', b'\r\n'), bytearray(self.raw)):
            with self.subTest(length=len(bad)), self.assertRaises(ValueError):
                worker.validate_official_model_config(bad)

    def test_real_physical_helpers_accept_official_override_and_full_synthetic_layout(self):
        from cloud.test_final_scale_artifacts import write_weights, write_json
        from cloud.test_granite_lora_layout import adapter
        config = self.root/'config.json'; config.write_bytes(self.raw)
        with self.assertRaises(ValueError): worker.physical.verify_model_config(config, allowed_root=self.root)
        proof = worker.physical.verify_model_config(config,
            expected_model_config_sha256=worker.OFFICIAL_RAW_CONFIG_SHA, allowed_root=self.root)
        self.assertEqual(proof['model_config_sha256'], worker.OFFICIAL_RAW_CONFIG_SHA)
        target = self.root/'adapter'; target.mkdir()
        write_json(target/'adapter_config.json', adapter()); write_weights(target/'adapter_model.safetensors')
        observed = worker.physical.inspect_adapter(target, model_config_path=config,
            expected_model_config_sha256=worker.OFFICIAL_RAW_CONFIG_SHA, allowed_root=self.root)
        verified = worker.physical.verify_adapter(target, observed['adapter_files_sha256'], model_config_path=config,
            expected_model_config_sha256=worker.OFFICIAL_RAW_CONFIG_SHA, allowed_root=self.root)
        self.assertEqual((verified['weights']['layout']['tensor_count'], verified['weights']['layout']['parameters']),
            (160, 2621440))
        self.assertFalse(verified['runtime_peft_load_verified'])

    def test_all_physical_model_config_and_adapter_calls_override_historical_default(self):
        tree = ast.parse(Path(worker.__file__).read_text(encoding='utf-8'))
        found = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == 'physical'
                    and node.func.attr in ('verify_model_config', 'inspect_adapter', 'verify_adapter')):
                overrides = [x.value for x in node.keywords if x.arg == 'expected_model_config_sha256']
                self.assertEqual(len(overrides), 1)
                self.assertIsInstance(overrides[0], ast.Name); self.assertEqual(overrides[0].id, 'OFFICIAL_RAW_CONFIG_SHA')
                found.append(node.func.attr)
        self.assertEqual(sorted(found), ['inspect_adapter','verify_adapter','verify_adapter','verify_model_config'])

    def test_identity_failure_keeps_original_bytes_before_model_constructor(self):
        runtime = self.runtime(); bad = self.raw+b'\n'; source = self.root/'downloaded.json'; source.write_bytes(bad)
        model = Mock(); commit = Mock()
        modules = {'torch': SimpleNamespace(set_num_threads=Mock()),
            'huggingface_hub': SimpleNamespace(hf_hub_download=Mock(return_value=str(source))),
            'transformers': SimpleNamespace(AutoModelForCausalLM=model, set_seed=Mock()),
            'peft': SimpleNamespace(LoraConfig=Mock(), get_peft_model=Mock())}
        with patch.dict(sys.modules, modules), patch.object(worker.artifacts, 'commit', commit):
            with self.assertRaises(ValueError): runtime.load_model(runtime.plan)
        self.assertEqual((runtime.folder/'model_config.json').read_bytes(), bad)
        observation = json.loads((runtime.folder/'model_config_observation.json').read_bytes())
        self.assertTrue(observation['recorded_before_validation']); self.assertFalse(observation['raw_byte_identity_matches'])
        self.assertEqual(observation['observed_sha256'], hashlib.sha256(bad).hexdigest())
        commit.assert_called_once(); model.from_pretrained.assert_not_called()

    def test_caught_trace_is_private_bounded_and_finish_updates_terminal_worker_status(self):
        runtime = self.runtime(); state = {}
        try: raise ValueError('INVENTED diagnosis '+'漢'*70000)
        except ValueError as error:
            with patch.object(worker.artifacts, 'commit'): record = runtime.record_error(error, phase='execution')
        saved = json.loads((runtime.folder/record['path']).read_bytes())
        self.assertLessEqual(len(saved['traceback_utf8'].encode('utf-8')), 65536)
        self.assertTrue(saved['traceback_may_be_truncated']); self.assertFalse(saved['provider_terminal_confirmed'])
        self.assertIn('ValueError', saved['traceback_utf8']); self.assertNotIn('locals', saved)
        self.assertEqual(record['sha256'], hashlib.sha256((runtime.folder/record['path']).read_bytes()).hexdigest())
        result = {'stage':'failed','error_type':'ValueError','retained_evaluation_count':0,'expected_evaluation_count':200}
        with patch.object(worker, 'state', state), patch.object(worker.artifacts, 'commit'):
            runtime.finish(result)
        self.assertEqual(json.loads((runtime.folder/'result.json').read_bytes()), result)
        self.assertEqual(state[runtime.plan['run_id']]['stage'], 'failed')
        self.assertTrue(state[runtime.plan['run_id']]['worker_result_saved'])
        self.assertFalse(state[runtime.plan['run_id']]['provider_terminal_confirmed'])

    def test_generation_and_regular_errors_attempt_diagnostics_without_masking_failures(self):
        with patch.object(old_tests, 'worker', worker), old_tests.fixture() as (data, plan, dispatch, tok), \
                patch.object(worker.contract, 'tokenizer_identity', return_value=dict(worker.contract.TOKENIZER)):
            for kwargs, phase in (({'source_failure':True},'execution'), ({'generation_failure':True},'generation')):
                runtime = old_tests.FakeRuntime(tok, **kwargs)
                runtime.record_error = Mock(side_effect=OSError('INVENTED diagnostics unavailable'))
                result = worker.run_native(data, plan, dispatch, runtime=runtime)
                self.assertEqual(result['stage'], 'failed'); self.assertIsNone(result['metrics'])
                self.assertIn(result['error_type'], ('ValueError','RuntimeError'))
                self.assertEqual(runtime.record_error.call_args.kwargs['phase'], phase)

    def test_training_generation_resources_and_mount_policy_unchanged_from_v2(self):
        def methods(module):
            runtime = next(x for x in ast.parse(Path(module.__file__).read_text(encoding='utf-8')).body
                if isinstance(x, ast.ClassDef) and x.name == 'Runtime')
            return {x.name: ast.dump(x, include_attributes=False) for x in runtime.body if isinstance(x, ast.FunctionDef)}
        before, after = methods(prior), methods(worker)
        for name in ('begin','begin_update','backward_window','step_update','generate','input_counts','render','write_raw','write_batch'):
            self.assertEqual(before[name], after[name], name)
        self.assertEqual(worker.RESOURCES, prior.RESOURCES)
        self.assertEqual(worker.MOUNT_POLICY, prior.MOUNT_POLICY)


if __name__ == '__main__': unittest.main()
