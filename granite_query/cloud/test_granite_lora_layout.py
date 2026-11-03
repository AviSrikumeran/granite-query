"""Synthetic tensor metadata only; no model import, weights or official data."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cloud import granite_lora_layout as layout


def configuration():
    return {'architectures': ['GraniteForCausalLM'], 'model_type': 'granite',
        'hidden_size': 2560, 'num_hidden_layers': 40, 'num_attention_heads': 40,
        'num_key_value_heads': 8, 'attention_bias': False}


def adapter():
    return {'base_model_name_or_path': layout.MODEL, 'peft_type': 'LORA', 'r': 8,
        'lora_alpha': 16, 'lora_dropout': 0.0, 'bias': 'none', 'task_type': 'CAUSAL_LM',
        'target_modules': ['v_proj', 'q_proj']}


def shapes(*, saved=False):
    result = {}
    for number in range(40):
        stem = f'base_model.model.model.layers.{number}.self_attn.'
        suffix = '.weight' if saved else '.default.weight'
        for projection, side, shape in (('q_proj', 'A', [8, 2560]), ('q_proj', 'B', [2560, 8]),
                ('v_proj', 'A', [8, 2560]), ('v_proj', 'B', [512, 8])):
            result[stem+projection+'.lora_'+side+suffix] = shape
    return result


def header():
    result = {'__metadata__': {'format': 'pt'}}; offset = 0
    for name, shape in shapes(saved=True).items():
        stop = offset+shape[0]*shape[1]*4
        result[name] = {'shape': shape, 'dtype': 'F32', 'data_offsets': [offset, stop]}
        offset = stop
    return result, offset


class GraniteLayoutTests(unittest.TestCase):
    def test_complete_runtime_geometry_has_grouped_query_value_width_and_exact_count(self):
        result = layout.validate_layout(shapes(), configuration(), adapter())
        self.assertEqual((result['layers'], result['attention_modules'], result['tensor_count'], result['parameters']),
            (40, 80, 160, 2621440))
        expected = layout.expected_layout(configuration())
        self.assertEqual(expected, shapes())
        self.assertEqual(expected['base_model.model.model.layers.39.self_attn.q_proj.lora_B.default.weight'], [2560, 8])
        self.assertEqual(expected['base_model.model.model.layers.39.self_attn.v_proj.lora_B.default.weight'], [512, 8])

    def test_saved_key_format_is_explicit_and_does_not_permissively_normalize(self):
        self.assertEqual(layout.expected_layout(configuration(), key_format='peft_saved'), shapes(saved=True))
        result = layout.validate_layout(shapes(saved=True), configuration(), adapter(), key_format='peft_saved')
        self.assertFalse(result['saved_serializer_compatibility_observed_locally'])
        with self.assertRaises(ValueError): layout.validate_layout(shapes(saved=True), configuration(), adapter())
        with self.assertRaises(ValueError): layout.expected_layout(configuration(), key_format='guess')

    def test_missing_layer_projection_and_extra_layer_never_pass_by_total_numel(self):
        original = shapes()
        missing = dict(original); missing.pop(next(iter(missing)))
        extra = dict(original); key = next(iter(extra)); extra[key.replace('.0.', '.40.')] = extra.pop(key)
        tiny = {key: value for key, value in original.items() if '.layers.0.' in key}
        for value in (missing, extra, tiny):
            with self.subTest(count=len(value)), self.assertRaises(ValueError):
                layout.validate_layout(value, configuration(), adapter())

    def test_unexpected_module_prefix_adapter_name_and_mixed_names_rejected(self):
        mutations = (lambda name: name.replace('q_proj', 'k_proj'),
            lambda name: name.replace('base_model.model.model.', 'base_model.model.'),
            lambda name: name.replace('.default.', '.other.'), lambda name: name.replace('.default.', '.'))
        for mutate in mutations:
            value = shapes(); key = next(iter(value)); value[mutate(key)] = value.pop(key)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                layout.validate_layout(value, configuration(), adapter())

    def test_q_and_v_output_dimensions_cannot_be_swapped_or_transposed(self):
        value = shapes(); first = next(iter(value))
        mutations = ([2560, 8], [True, 2560], (8, 2560), [8, 512])
        for shape in mutations:
            bad = copy.deepcopy(value); bad[first] = shape
            with self.subTest(shape=shape), self.assertRaises(ValueError):
                layout.validate_layout(bad, configuration(), adapter())
        bad = shapes(); bad['base_model.model.model.layers.2.self_attn.v_proj.lora_B.default.weight'] = [2560, 8]
        with self.assertRaises(ValueError): layout.validate_layout(bad, configuration(), adapter())

    def test_model_revision_and_architecture_fields_fail_closed(self):
        for field, value in (('hidden_size', 2048), ('num_hidden_layers', 39), ('num_key_value_heads', 40),
                ('num_attention_heads', True), ('attention_bias', True), ('model_type', 'other'), ('head_dim', 128)):
            bad = dict(configuration(), **{field: value})
            with self.subTest(field=field), self.assertRaises(ValueError):
                layout.expected_layout(bad)
        with self.assertRaises(ValueError): layout.expected_layout(configuration(), revision='another-revision')
        with self.assertRaises(ValueError): layout.expected_layout(configuration(), model='another-model')
        self.assertEqual(layout.validate_config(dict(configuration(), head_dim=64))['value_output_size'], 512)

    def test_alternate_algorithm_scaling_rank_and_layer_restrictions_rejected(self):
        for field, value in (('peft_type', 'ADALORA'), ('r', True), ('r', 16), ('lora_alpha', 8),
                ('use_rslora', True), ('use_dora', True), ('fan_in_fan_out', True), ('rank_pattern', {'layer': 8}),
                ('alpha_pattern', {'layer': 16}), ('layers_to_transform', [0]), ('modules_to_save', ['lm_head']),
                ('target_modules', ['q_proj', 'q_proj']), ('target_modules', ['q_proj', {}])):
            bad = dict(adapter(), **{field: value})
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                layout.validate_layout(shapes(), configuration(), bad)

    def test_full_synthetic_header_validates_all_payload_bytes_without_deserialization(self):
        value, size = header()
        self.assertEqual(size, 10485760)
        result = layout.validate_header(value, size, configuration(), adapter())
        self.assertTrue(result['complete_expected_layout_verified']); self.assertTrue(result['contiguous_full_payload_verified'])
        self.assertFalse(result['tensor_values_verified'])

    def test_header_missing_module_offsets_trailing_data_and_dtype_rejected(self):
        value, size = header(); first = next(key for key in value if key != '__metadata__')
        mutations = (lambda h: h[first].update(dtype='I8'),
            lambda h: h[first].update(data_offsets=[1, 81921]),
            lambda h: h[first].update(data_offsets=[False, 81920]),
            lambda h: h[first].update(extra='unexpected'), lambda h: h['__metadata__'].update(format=[]))
        for mutate in mutations:
            bad = copy.deepcopy(value); mutate(bad)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                layout.validate_header(bad, size, configuration(), adapter())
        for wrong in (True, size-1, size+1):
            with self.subTest(size=wrong), self.assertRaises(ValueError):
                layout.validate_header(value, wrong, configuration(), adapter())

    def test_no_file_access_or_input_mutation_and_layout_returns_fresh_values(self):
        config, adapted, tensor_shapes = configuration(), adapter(), shapes()
        before = copy.deepcopy((config, adapted, tensor_shapes))
        with patch('builtins.open', side_effect=AssertionError('Pure helper must never read files')):
            result = layout.validate_layout(tensor_shapes, config, adapted)
        self.assertEqual((config, adapted, tensor_shapes), before)
        first = layout.expected_layout(config); key = next(iter(first)); first[key][0] = 99
        self.assertEqual(layout.expected_layout(config)[key], [8, 2560])
        self.assertFalse(result['training_or_contemporaneous_development_weights_verified'])
        self.assertFalse(layout.EVIDENCE['remote_verification_performed_by_this_helper'])


if __name__ == '__main__':
    unittest.main()
