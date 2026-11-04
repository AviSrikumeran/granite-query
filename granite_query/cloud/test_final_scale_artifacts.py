"""Synthetic files only; physical helper tests never load PEFT or official data."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cloud import final_scale_artifacts as artifacts
from cloud.test_granite_lora_layout import configuration, adapter, header


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path.write_bytes((json.dumps(value, sort_keys=True)+'\n').encode())


def write_weights(path, *, change=None, extra_bytes=0, duplicate=False, leading_space=False):
    value, size = header()
    if change:
        change(value)
    raw = json.dumps(value, separators=(',', ':')).encode()
    if duplicate:
        key = next(name for name in value if name != '__metadata__')
        raw = raw[:-1]+b','+json.dumps(key).encode()+b':'+json.dumps(value[key]).encode()+b'}'
    if leading_space:
        raw = b' '+raw
    raw += b' '*((-len(raw)) % 8)
    path.write_bytes(struct.pack('<Q', len(raw))+raw+b'\0'*(size+extra_bytes))


class PortableArtifactTests(unittest.TestCase):
    def setUp(self):
        self.package = Path(artifacts.__file__).resolve().parent
        parent = self.package/'runs/test_final_scale_artifacts'
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.temp.name).resolve()
        self.assertTrue(self.root.is_relative_to((self.package/'runs').resolve()))
        self.adapter = self.root/'adapter'
        self.adapter.mkdir()
        self.model_config = self.root/'config.json'
        write_json(self.model_config, configuration())
        write_json(self.adapter/'adapter_config.json', adapter())
        write_weights(self.adapter/'adapter_model.safetensors')

    def tearDown(self):
        self.temp.cleanup()

    def inspect(self, **kwargs):
        return artifacts.inspect_adapter(self.adapter, model_config_path=self.model_config,
            expected_model_config_sha256=sha(self.model_config), allowed_root=self.root, **kwargs)

    def verify(self, inventory, **kwargs):
        return artifacts.verify_adapter(self.adapter, inventory, model_config_path=self.model_config,
            expected_model_config_sha256=sha(self.model_config), allowed_root=self.root, **kwargs)

    def test_exact_raw_inventory_layout_and_no_runtime_load_claim(self):
        result = self.inspect()
        measured = result['weights']['layout']
        self.assertEqual((measured['tensor_count'], measured['parameters']), (160, 2621440))
        self.assertEqual(result['raw_adapter_config_sha256'], sha(self.adapter/'adapter_config.json'))
        self.assertEqual(result['adapter_files_sha256']['adapter_model.safetensors'], sha(self.adapter/'adapter_model.safetensors'))
        self.assertTrue(measured['complete_expected_layout_verified'])
        self.assertFalse(result['runtime_peft_load_verified'])
        self.assertFalse(result['saved_serializer_compatibility_observed_locally'])
        self.assertFalse(result['training_or_contemporaneous_development_weights_verified'])
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_base_config_gate_needs_no_adapter_or_model_load(self):
        with patch.object(artifacts, '_header', side_effect=AssertionError('Base config cannot read adapter weights')):
            result = artifacts.verify_model_config(self.model_config,
                expected_model_config_sha256=sha(self.model_config), allowed_root=self.root)
        self.assertEqual(result['model_config_sha256'], sha(self.model_config))
        self.assertEqual(result['dimensions']['value_output_size'], 512)
        self.assertFalse(result['runtime_model_or_peft_load_verified'])

    def test_legacy_hashes_and_explicit_portable_size_inventory_are_bound(self):
        observed = self.inspect()
        for value, sized in ((observed['adapter_files_sha256'], False), (observed['inventory'], True)):
            result = self.verify(value)
            self.assertTrue(result['exact_expected_inventory_verified'])
            self.assertEqual(result['expected_inventory_included_sizes'], sized)
        wrong = copy.deepcopy(observed['inventory'])
        wrong['adapter_config.json']['size_bytes'] += 1
        with self.assertRaises(ValueError):
            self.verify(wrong)
        (self.adapter/'unreviewed.txt').write_text('extra', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.verify(observed['inventory'])

    def test_structurally_valid_payload_mutation_cannot_match_original_hash(self):
        observed = self.inspect()
        path = self.adapter/'adapter_model.safetensors'
        raw = path.read_bytes()
        path.write_bytes(raw[:-1]+b'\x01')
        self.assertTrue(self.inspect()['weights']['layout']['complete_expected_layout_verified'])
        with self.assertRaises(ValueError):
            self.verify(observed['inventory'])

    def test_duplicate_config_and_model_json_are_rejected_before_semantic_use(self):
        path = self.adapter/'adapter_config.json'
        original = path.read_bytes().rstrip()
        path.write_bytes(original[:-1]+b',"r":8}')
        with self.assertRaises(ValueError):
            self.inspect()
        write_json(path, adapter())
        original = self.model_config.read_bytes().rstrip()
        self.model_config.write_bytes(original[:-1]+b',"hidden_size":2560}')
        with self.assertRaises(ValueError):
            self.inspect()

    def test_header_duplicate_size_format_and_trailing_data_fail_closed(self):
        path = self.adapter/'adapter_model.safetensors'
        for kwargs in ({'duplicate': True}, {'leading_space': True}, {'extra_bytes': 1}, {'extra_bytes': -1}):
            write_weights(path, **kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.inspect()
        path.write_bytes(struct.pack('<Q', artifacts.MAX_HEADER_BYTES+8)+b'{}')
        with self.assertRaises(ValueError):
            self.inspect()
        path.write_bytes(b'<html>not adapter weights</html>')
        with self.assertRaises(ValueError):
            self.inspect()

    def test_exact_coverage_shape_float_dtype_and_offsets_required(self):
        path = self.adapter/'adapter_model.safetensors'
        first = lambda value: next(k for k in value if k != '__metadata__')
        mutations = (
            lambda v: v.pop(first(v)),
            lambda v: v[first(v)].update(shape=[2560, 8]),
            lambda v: v[first(v)].update(dtype='I32'),
            lambda v: v[first(v)].update(dtype=[]),
            lambda v: v[first(v)].update(data_offsets=[False, 81920]),
            lambda v: v[list(v)[2]].update(data_offsets=[0, 81920]),
        )
        for change in mutations:
            write_weights(path, change=change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.inspect()

    def test_wrong_revision_geometry_and_adapter_algorithm_rejected(self):
        bad = dict(configuration(), num_key_value_heads=40)
        write_json(self.model_config, bad)
        with self.assertRaises(ValueError):
            self.inspect()
        write_json(self.model_config, configuration())
        for field, value in (('use_rslora', True), ('use_dora', True), ('modules_to_save', ['lm_head']), ('r', True)):
            write_json(self.adapter/'adapter_config.json', dict(adapter(), **{field: value}))
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.inspect()
        write_json(self.adapter/'adapter_config.json', adapter())
        with self.assertRaises(ValueError):
            artifacts.inspect_adapter(self.adapter, model_config_path=self.model_config)

    def test_explicit_key_format_never_guessed_or_silently_normalized(self):
        with self.assertRaises(ValueError):
            self.inspect(key_format='runtime_default')
        with self.assertRaises(ValueError):
            self.inspect(key_format='guess')

    def test_links_parent_escape_and_portable_inventory_traversal_rejected(self):
        path = self.adapter/'adapter_config.json'
        original = Path.is_symlink
        with patch.object(Path, 'is_symlink', lambda item: item == path or original(item)):
            with self.assertRaises(ValueError):
                self.inspect()
        with self.assertRaises(ValueError):
            artifacts.inspect_adapter(self.adapter, model_config_path=self.model_config,
                expected_model_config_sha256=sha(self.model_config), allowed_root=self.adapter)
        for path in ('../outside.py', '/absolute.py', 'C:/private.py', 'a\\b.py', 'a/../b.py', 'a//b.py', 'CON.py', 'file.py '):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.verify({path: 'a'*64})

    def test_file_change_during_inspection_is_not_a_stable_capture(self):
        original = artifacts._header
        def changing(path, *args):
            result = original(path, *args)
            raw = path.read_bytes()
            path.write_bytes(raw[:-1]+b'\x01')
            return result
        with patch.object(artifacts, '_header', side_effect=changing):
            with self.assertRaises(ValueError):
                self.inspect()

    def test_total_byte_bound_is_checked_before_hashing_or_parsing(self):
        with patch.object(artifacts, 'MAX_ADAPTER_BYTES', 10), \
             patch.object(artifacts, '_record', side_effect=AssertionError('Over-limit bundle must not be read')):
            with self.assertRaises(ValueError):
                self.inspect()

    def source_inventory(self, *, sizes=True):
        sources = {}
        for name in artifacts.HELPERS:
            path = self.package/name
            sources[name] = ({'path': name, 'sha256': sha(path), 'size_bytes': path.stat().st_size}
                if sizes else sha(path))
        extra = self.root/'fixture_extra.py'
        extra.write_text('# synthetic source only\n', encoding='utf-8')
        relative = extra.relative_to(self.package).as_posix()
        sources['fixture_role'] = {'path': relative, 'sha256': sha(extra), 'size_bytes': extra.stat().st_size}
        return sources

    def test_source_inventory_is_portable_and_binds_loaded_helpers(self):
        for sized in (False, True):
            inventory = self.source_inventory(sizes=sized)
            result = artifacts.verify_packaged_sources(self.package, inventory)
            self.assertTrue(result['packaged_source_hashes_verified'])
            self.assertEqual(result['verified_file_count'], 3)
            self.assertEqual(result['source_bundle_sha256'], artifacts.layout.digest(result['source_hashes']))
            self.assertFalse(result['runtime_model_or_peft_load_verified'])
            self.assertNotIn(str(self.root), json.dumps(result))
        copied = self.root/'copied_package'
        copied.mkdir()
        expected = {}
        for name in artifacts.HELPERS:
            shutil.copyfile(self.package/name, copied/name)
            expected[name] = sha(copied/name)
        with self.assertRaises(ValueError):
            artifacts.verify_packaged_sources(copied, expected)

    def test_source_tampering_missing_helpers_aliases_and_data_files_rejected(self):
        original = self.source_inventory()
        changed = copy.deepcopy(original)
        changed['final_scale_artifacts.py']['sha256'] = '0'*64
        with self.assertRaises(ValueError):
            artifacts.verify_packaged_sources(self.package, changed)
        changed = copy.deepcopy(original)
        changed.pop('granite_lora_layout.py')
        with self.assertRaises(ValueError):
            artifacts.verify_packaged_sources(self.package, changed)
        changed = copy.deepcopy(original)
        changed['duplicate_role'] = copy.deepcopy(changed['fixture_role'])
        with self.assertRaises(ValueError):
            artifacts.verify_packaged_sources(self.package, changed)
        changed = copy.deepcopy(original)
        changed['fixture_role']['path'] = 'sample.jsonl'
        with self.assertRaises(ValueError):
            artifacts.verify_packaged_sources(self.package, changed)


if __name__ == '__main__':
    unittest.main()
