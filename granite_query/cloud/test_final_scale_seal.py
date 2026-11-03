"""Physical synthetic fixtures only; no actual model choice or official data."""
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cloud import final_scale_seal as seal
from cloud import final_scale_contract as contract


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8', newline='\n')


def weights(path, *, transform=None, payload_delta=0):
    header, end = {}, 0
    for module in ('q_proj', 'v_proj'):
        for side, shape in (('A', [8, 2]), ('B', [2, 8])):
            name = 'base_model.model.layers.0.self_attn.'+module+'.lora_'+side+'.weight'
            header[name] = {'dtype': 'F32', 'shape': shape, 'data_offsets': [end, end+64]}
            end += 64
    if transform:
        transform(header)
    raw = json.dumps(header, separators=(',', ':')).encode()
    raw += b' '*((-len(raw)) % 8)
    path.write_bytes(struct.pack('<Q', len(raw))+raw+b'\0'*(end+payload_delta))


def training_arm(budget):
    rows, updates = [], []
    for index in range(budget//1024):
        identifier = 'train:'+str(index)
        rows.append({'id': identifier, 'input_ids': [10]+[11]*1024, 'labels': [-100]+[11]*1024,
            'attention_mask': [1]*1025, 'prefix_tokens': 1, 'supervised_tokens': 1024, 'full_response_tokens': 1024})
        updates.append({'index': index, 'supervised_tokens': 1024, 'microbatches': [
            {'id': identifier, 'answer_start': 0, 'answer_end': 1024, 'supervised_tokens': 1024, 'loss_weight': 1.0}]})
    return {'arm': 'valued', 'token_budget': budget, 'tokens_per_update': 1024,
        'optimizer_updates': budget//1024, 'training': rows, 'updates': updates}


def development(count):
    prefix = 'new-dev:' if count == 200 else 'legacy-dev:'
    return [{'id': prefix+str(i), 'prompt': 'Synthetic local development calculation '+str(i), 'gold_answer': '13'}
        for i in range(count)]


def completed_files(folder, data, plan):
    folder.mkdir(parents=True, exist_ok=True)
    write(folder/'input.json', data)
    plan = dict(plan, run_id=folder.name, input_sha256=seal.sha(folder/'input.json'))
    plan['protocol_hash'] = contract.digest({k: v for k, v in plan.items() if k != 'run_id'})
    write(folder/'plan.json', plan)
    label = plan['checkpoint_name']
    rows = [{'id': r['id'], 'gold_answer': r['gold_answer'], 'response': 'Synthetic calculation.\n#### 13',
        'generated_tokens': 4, 'truncated': False, 'batch_size': 8,
        'batch_elapsed_seconds': .8, 'elapsed_seconds': .1} for r in data['development']]
    budget = plan.get('token_budget', 0)
    result = {'stage': 'completed', 'run_id': folder.name, 'plan': plan,
        'arm': data['arm']['arm'] if 'arm' in data else 'evaluation_only',
        'supervised_tokens': budget, 'optimizer_updates': budget//1024,
        'weighted_losses': [.5]*(budget//1024), 'held_out_test_used': False,
        'evaluations': {label: rows}, 'elapsed_seconds': 100.0}
    write(folder/'result.json', result)
    write(folder/'launch.json', {'run_id': folder.name, 'call_id': 'fc-synthetic-'+folder.name})
    write(folder/'study_terminal.json', {'kind': 'completed', 'call_id': 'fc-synthetic-'+folder.name,
        'result_sha256': seal.sha(folder/'result.json')})
    return plan


class PhysicalSealTests(unittest.TestCase):
    def setUp(self):
        parent = seal.PRIVATE_ROOT/'test_final_scale_seal'
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.temp.name).resolve()
        self.assertTrue(self.root.is_relative_to(seal.PRIVATE_ROOT.resolve()))
        self.registry = self.root/'global/final_test_access.json'
        self.patcher = patch.object(seal, 'ACCESS', self.registry)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.temp.cleanup()

    def checkpoint(self, count=200):
        study = self.root/('study'+str(count))
        folder = study/'arms'/('synthetic-chosen'+str(count))
        budget = 65536 if count == 200 else 32768
        plan = {'mode': 'train_evaluate', 'model': contract.MODEL, 'revision': contract.REVISION,
            'tokens_per_update': 1024, 'learning_rate': 2e-5, 'lora_r': 8, 'lora_alpha': 16,
            'context_limit': 2048, 'max_new_tokens': 512, 'enable_thinking': False, 'do_sample': False,
            'evaluation_batch_size': 8, 'evaluation_kind': 'development', 'fresh_base': True,
            'data_repetition': False, 'official_test_used': False, 'seed': 42,
            'arm': 'valued', 'checkpoint_name': 'skill', 'selector_name': 'skill',
            'token_budget': budget, 'optimizer_updates': budget//1024,
            'development_ids': [r['id'] for r in development(count)]}
        if count == 200:
            version = 'human-reference64k-dev200-v2'
            plan['experiment_version'] = version
        else:
            version = 'common-pool-data-efficiency-v1'
            plan['study_version'] = version
            names = {'training_worker_sha256': 'modal_valuation.py',
                'selection_code_sha256': 'data_efficiency_control.py', 'skill_code_sha256': 'student_valuation.py',
                'gradient_score_code_sha256': 'gradient_valuation.py'}
            plan['source_code'] = {k: seal.sha(seal.ROOT/name) for k, name in names.items()}
        data = {'development': development(count), 'arm': training_arm(budget)}
        plan = completed_files(folder, data, plan)
        relative = folder.relative_to(study).as_posix()
        manifest = {'version': version, 'jobs': [{'run_id': folder.name, 'folder': relative,
            'selector': 'skill', 'protocol_hash': plan['protocol_hash'], 'input_sha256': plan['input_sha256']}],
            'artifacts_sha256': {relative+'/'+name: seal.sha(folder/name) for name in ('plan.json', 'input.json')}}
        if count == 200:
            manifest.update(official_test_accessed=False, expected_dev=200,
                controller_sha256=seal.sha(seal.ROOT/'human_study_control.py'))
            names = ('student_valuation.py', 'valuation_contract.py', 'modal_valuation.py', 'modal_train.py',
                'study_runner.py', 'comparison_control.py', 'budget_reconcile.py', 'comparison_metrics.py',
                '../ranking/verification.py')
            manifest['code_sha256'] = {name: seal.sha(seal.ROOT/name) for name in names}
            path = study/'study_manifest.json'
        else:
            manifest.update(official_test_used=False, source_code=plan['source_code'])
            path = study/'manifest.json'
        write(path, manifest)
        if count == 200:
            write(folder/'human_claim.json', {'claim_id': 'f'*32, 'run_id': folder.name,
                'protocol_hash': plan['protocol_hash'], 'study_manifest_sha256': seal.sha(path)})
        adapter = folder/'adapter'
        adapter.mkdir()
        write(adapter/'adapter_config.json', {'base_model_name_or_path': contract.MODEL, 'r': 8,
            'lora_alpha': 16, 'lora_dropout': 0.0, 'target_modules': ['q_proj', 'v_proj'],
            'peft_type': 'LORA', 'bias': 'none', 'task_type': 'CAUSAL_LM'})
        weights(adapter/'adapter_model.safetensors')
        return folder

    def preparation(self, count=200):
        folder = self.checkpoint(count)
        chosen = seal.inspect_checkpoint(folder)
        sources = self.root/'sources'
        sources.mkdir()
        roles = {role: ['fixture_'+role+'.py'] for role in contract.SOURCE_ROLES}
        roles['contract'] = ['final_scale_contract.py', 'final_scale_seal.py']
        roles['receipts'] = ['final_scale_receipts.py']
        roles['checkpoint_validator'] += ['valuation_contract.py']
        source_paths = {}
        owned = {'final_scale_contract.py', 'final_scale_seal.py', 'final_scale_receipts.py', 'valuation_contract.py'}
        for names in roles.values():
            for name in names:
                path = seal.ROOT/name if name in owned else sources/name
                if name not in owned:
                    path.write_text('# Synthetic source-review fixture only.\n', encoding='utf-8')
                source_paths[name] = str(path)
        source_hashes = {name: seal.sha(path) for name, path in source_paths.items()}
        proposed = contract.build_contract(1319, source_hashes=source_hashes,
            source_roles=roles, selected=chosen['selected'])
        common = {'mode': 'evaluate_saved', 'model': contract.MODEL, 'revision': contract.REVISION,
            'evaluation_kind': 'development', 'evaluation_batch_size': 8, 'max_new_tokens': 512,
            'enable_thinking': False, 'do_sample': False,
            'development_ids': [r['id'] for r in development(200)]}
        base = self.root/'calibration/base'
        completed_files(base, {'development': development(200)}, dict(common, checkpoint_name='baseline'))
        if count == 200:
            calibration_chosen = folder
        else:
            calibration_chosen = self.root/'calibration/chosen'
            completed_files(calibration_chosen, {'development': development(200)}, dict(common,
                checkpoint_name='skill', adapter_from=folder.name+'/adapter',
                evaluated_adapter_inventory_sha256=chosen['selected']['adapter_inventory_sha256']))
        calibration_paths = {'base': str(base/'result.json'), 'chosen': str(calibration_chosen/'result.json')}
        measured = contract.calibration(proposed, base_generation_seconds=sum([.1]*200),
            chosen_generation_seconds=sum([.1]*200),
            evidence_hashes={role: seal.sha(path) for role, path in calibration_paths.items()})
        observed = '2026-11-03T22:59:00+00:00'
        funding = {'observed_at_utc': {'modal': observed, 'deepseek': observed},
            'new_paid_work_allowed': {'modal': True, 'deepseek': True},
            'limits_usd': {'modal': '30', 'deepseek': '20'}, 'spent_usd': {'modal': '0', 'deepseek': '0'},
            'reserved_usd': {'modal': '0', 'deepseek': '0'}}
        review = contract.review_template(proposed)
        review.update(reviewed=True, no_tuning_after_access_acknowledged=True,
            complete_denominator_acknowledged=True, all_source_roles_reviewed=True,
            calibration_sha256=measured['calibration_sha256'], funding_snapshot_sha256=contract.digest(funding))
        return {'contract': proposed, 'chosen_run': folder, 'source_paths': source_paths, 'review': review,
            'calibration_record': measured, 'funding_snapshot': funding,
            'as_of_utc': '2026-11-03T23:00:00+00:00',
            'actual_pricing_sha256': contract.digest(proposed['protocol']['pricing']),
            'calibration_source_paths': calibration_paths}

    def create(self, arguments, name='seal'):
        return seal.create(output=self.root/name, **arguments)

    def access(self, name='seal', destination=None, **kwargs):
        folder = self.root/name
        return seal.begin_access(folder, owner_token=seal.read_owner(folder),
            destination=destination or self.root/'inputs', loader_authorized=True,
            as_of_utc=kwargs.pop('as_of_utc', '2026-11-03T23:00:00+00:00'), **kwargs)

    def receipt(self, proposed):
        return {'full_source_sha256': '1'*64, 'sample_sha256': '2'*64, 'binding_sha256': '3'*64,
            'population_count': 1319, 'sample_count': 1319,
            'indices_sha256': proposed['protocol']['dataset']['indices_sha256'],
            'input_hash_convention': seal.INPUT_HASH_CONVENTION}

    def test_actual64_and200_saved_claim_provenance(self):
        for count in (64, 200):
            checkpoint = seal.inspect_checkpoint(self.checkpoint(count))
            self.assertEqual(checkpoint['development_count'], count)
            self.assertEqual(checkpoint['weights_validation']['tensor_count'], 4)
            self.assertIn('human_unique' if count == 200 else 'no_retrospective', checkpoint['identity_provenance'])
            self.assertFalse(checkpoint['development_worker_recorded_contemporaneous_adapter_hashes'])
            self.assertEqual(checkpoint['weight_inventory_capture_timing'], 'after_development_evaluation_before_final_seal')
            self.assertFalse(checkpoint['weights_validation']['pinned_model_tensor_layout_and_coverage_verified'])

    def test_create_verify_is_immutable_and_does_not_acquire_access(self):
        arguments = self.preparation(64)
        sealed = self.create(arguments)
        self.assertEqual(seal.verify(self.root/'seal'), sealed)
        self.assertFalse(self.registry.exists())
        self.assertFalse(sealed['official_test_accessed_by_seal'])
        self.assertFalse(sealed['paid_work_launched'])
        with self.assertRaises(FileExistsError):
            self.create(arguments)

    def test_human_claim_and_terminal_identity_fail_closed(self):
        folder = self.checkpoint(200)
        claim = seal.read(folder/'human_claim.json')
        claim['study_manifest_sha256'] = '0'*64
        write(folder/'human_claim.json', claim)
        with self.assertRaises(ValueError):
            seal.inspect_checkpoint(folder)
        claim['study_manifest_sha256'] = seal.sha(folder.parent.parent/'study_manifest.json')
        write(folder/'human_claim.json', claim)
        terminal = seal.read(folder/'study_terminal.json')
        terminal['call_id'] = 'fc-different-owner'
        write(folder/'study_terminal.json', terminal)
        with self.assertRaises(ValueError):
            seal.inspect_checkpoint(folder)

    def test_html_truncation_overlap_shape_and_trailing_weights_rejected(self):
        path = self.root/'weights.safetensors'
        weights(path)
        self.assertEqual(seal.inspect_safetensors(path)['payload_bytes'], 256)
        mutations = [lambda h: h[next(iter(h))].update(dtype=[]),
            lambda h: h[next(iter(h))].update(shape=[True, 2]),
            lambda h: h[next(iter(h))].update(shape=[4, 4]),
            lambda h: h[list(h)[1]].update(data_offsets=[0, 64])]
        for mutate in mutations:
            weights(path, transform=mutate)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                seal.inspect_safetensors(path)
        for delta in (-1, 1):
            weights(path, payload_delta=delta)
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                seal.inspect_safetensors(path)
        path.write_bytes(b'<html>not model weights</html>')
        with self.assertRaises(ValueError):
            seal.inspect_safetensors(path)

    def test_symlinks_and_escape_rejected(self):
        path = self.root/'file.py'
        path.write_text('synthetic', encoding='utf-8')
        original = Path.is_symlink
        with patch.object(Path, 'is_symlink', lambda item: item == path or original(item)):
            with self.assertRaises(ValueError):
                seal.sha(path)
        with self.assertRaises(ValueError):
            seal.sha(seal.PROJECT_ROOT.parent/'outside-source.py')
        with self.assertRaises(ValueError):
            seal._registry(self.root/'other-owner-registry.json')

    def test_explicit_permit_owner_destination_and_recovery(self):
        self.create(self.preparation())
        token = seal.read_owner(self.root/'seal')
        with self.assertRaises(ValueError):
            seal.begin_access(self.root/'seal', owner_token=token, destination=self.root/'inputs')
        self.assertFalse(self.registry.exists())
        permit = self.access()
        self.assertEqual(permit['test_access_count'], 1)
        self.assertEqual(self.access(as_of_utc='2030-01-01T00:00:00+00:00'), permit)
        with self.assertRaises(ValueError):
            self.access(destination=self.root/'different-inputs')
        with self.assertRaises(ValueError):
            seal.check_access(self.root/'seal', owner_token='0'*64, destination=self.root/'inputs')

    def test_shared_registry_excludes_old256_and_other_scaled_protocols(self):
        arguments = self.preparation()
        write(self.registry, {'freeze_sha256': '0'*64, 'owner_sha256': '1'*64, 'test_access_count': 1})
        with self.assertRaises(ValueError):
            self.create(arguments)
        self.assertFalse((self.root/'seal').exists())
        self.registry.unlink()
        self.create(arguments)
        self.create(arguments, 'other-seal')
        self.access()
        before = self.registry.read_bytes()
        with self.assertRaises(ValueError):
            seal.verify(self.root/'other-seal')
        with self.assertRaises(ValueError):
            self.create(arguments, 'third-seal')
        self.assertEqual(self.registry.read_bytes(), before)

    def test_first_access_requires_fresh_whole_bundle_funding(self):
        self.create(self.preparation())
        self.assertIsNotNone(seal.verify(self.root/'seal'))
        with self.assertRaises(ValueError):
            self.access(as_of_utc='2026-11-03T23:30:00+00:00')
        self.assertFalse(self.registry.exists())

    def test_dataset_receipt_is_append_only_and_read_only_checkable(self):
        arguments = self.preparation()
        self.create(arguments)
        self.access()
        kwargs = {'owner_token': seal.read_owner(self.root/'seal'), 'destination': self.root/'inputs',
            'receipt': self.receipt(arguments['contract'])}
        receipt = seal.bind_dataset_receipt(self.root/'seal', **kwargs)
        self.assertEqual(seal.bind_dataset_receipt(self.root/'seal', **kwargs), receipt)
        self.assertEqual(seal.check_dataset_receipt(self.root/'seal', **kwargs), receipt)
        kwargs['receipt']['sample_sha256'] = '4'*64
        with self.assertRaises(ValueError):
            seal.bind_dataset_receipt(self.root/'seal', **kwargs)

    def test_source_weight_and_owner_tampering_after_seal_rejected(self):
        arguments = self.preparation()
        self.create(arguments)
        source = Path(arguments['source_paths']['fixture_loader.py'])
        source.write_text('# changed source', encoding='utf-8')
        with self.assertRaises(ValueError):
            seal.verify(self.root/'seal')
        source.write_text('# Synthetic source-review fixture only.\n', encoding='utf-8')
        owner = seal.read(self.root/'seal/access_owner.json')
        owner['owner_token'] = '0'*64
        write(self.root/'seal/access_owner.json', owner)
        with self.assertRaises(ValueError):
            seal.verify(self.root/'seal')

    def test_calibration_requires_real_complete200_evidence(self):
        arguments = self.preparation(64)
        arguments['calibration_source_paths']['base'] = str(Path(arguments['chosen_run'])/'result.json')
        with self.assertRaises(ValueError):
            self.create(arguments)
        self.assertFalse(self.registry.exists())

    def test_seal_and_loader_destinations_cannot_modify_development_or_supervisor(self):
        arguments = self.preparation()
        with self.assertRaises(ValueError):
            seal.create(output=Path(arguments['chosen_run'])/'adapter/new-seal', **arguments)
        self.assertFalse((Path(arguments['chosen_run'])/'adapter/new-seal').exists())
        self.create(arguments)
        with self.assertRaises(ValueError):
            self.access(destination=self.registry.parent/'official-data')
        self.assertFalse(self.registry.exists())

    def test_alternate_adapter_algorithms_and_inconsistent_batch_timing_rejected(self):
        folder = self.checkpoint()
        path = folder/'adapter/adapter_config.json'
        original = seal.read(path)
        mutations = ({'peft_type': 'IA3'}, {'use_rslora': True}, {'use_dora': True},
            {'fan_in_fan_out': True}, {'rank_pattern': {'layer': 16}}, {'alpha_pattern': {'layer': 32}},
            {'modules_to_save': ['embed_tokens']}, {'layer_replication': [[0, 1]]})
        for change in mutations:
            write(path, dict(original, **change))
            with self.subTest(change=change), self.assertRaises(ValueError):
                seal.inspect_checkpoint(folder)
        write(path, original)
        result = seal.read(folder/'result.json')
        result['evaluations']['skill'][0].update(batch_elapsed_seconds=1.6, elapsed_seconds=.2)
        write(folder/'result.json', result)
        terminal = seal.read(folder/'study_terminal.json')
        terminal['result_sha256'] = seal.sha(folder/'result.json')
        write(folder/'study_terminal.json', terminal)
        with self.assertRaises(ValueError):
            seal.inspect_checkpoint(folder)

    def test_structurally_valid_weight_byte_change_invalidates_existing_seal(self):
        arguments = self.preparation()
        self.create(arguments)
        path = Path(arguments['chosen_run'])/'adapter/adapter_model.safetensors'
        original = path.read_bytes()
        path.write_bytes(original[:-1]+b'\x01')
        self.assertEqual(seal.inspect_safetensors(path)['tensor_count'], 4)
        with self.assertRaises(ValueError):
            seal.verify(self.root/'seal')


if __name__ == '__main__':
    unittest.main()
