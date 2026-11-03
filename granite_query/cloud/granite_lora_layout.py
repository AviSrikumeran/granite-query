"""Pure, separately versioned exact Granite4.2-3B classic-r8 q/v layout checks.

No imports or functions read files, instantiate models, fetch metadata, inspect
datasets or authorize execution. Supply already loaded config/header metadata.
This helper is not integrated into any existing seal, loader or running worker.
"""
import hashlib
import json
import math

VERSION = 'granite42-3b-classic-qv-r8-layout-v1'
MODEL = 'ibm-granite/granite-4.2-3b'
REVISION = '4e9c275e232f10211ec88644d106a1f6a1b60e06'
RANK = 8
LAYERS = 40
HIDDEN = 2560
HEADS = 40
KV_HEADS = 8
HEAD_DIM = 64
TENSOR_COUNT = 160
PARAMETER_COUNT = 2621440
KEY_FORMATS = ('runtime_default', 'peft_saved')
CONFIG_FIELDS = {'architectures': ['GraniteForCausalLM'], 'model_type': 'granite',
    'hidden_size': HIDDEN, 'num_hidden_layers': LAYERS, 'num_attention_heads': HEADS,
    'num_key_value_heads': KV_HEADS, 'attention_bias': False}
EVIDENCE = {
    'pinned_model': MODEL, 'pinned_revision': REVISION,
    'local_config': {'path': 'cloud/runs/supervisor/pinned_model_config.json',
        'sha256': '65105f30da56ea03465f7424540a51b66f3a77bcff2af06f6288d093c65905b0'},
    'local_transformers': {'version': '4.57.1', 'path': 'transformers/models/granite/modeling_granite.py',
        'sha256': '920678d503bcb6795ba46c1b9579c28aad208a3ff0b73e7e02754e7cd9e3c19c',
        'attention_projection_lines': [118, 141], 'decoder_layer_construction_lines': [367, 368]},
    'runtime_layout': {'path': 'cloud/runs/gradient_features_math_v1/recovery_artifacts/parameter_layout.json',
        'file_sha256': '03d6b36f4ba288e44bdddf940555c919c6a7e99a2c556e0acae308d3f94f42dc',
        'recorded_layout_sha256': '75fde9dcdc82a8bd533a47f1e453062b1ad45a31d3007d1a09d6a8ee90a82fd9',
        'tensors': TENSOR_COUNT, 'parameters': PARAMETER_COUNT},
    'runtime_protocol': {'path': 'cloud/runs/gradient_features_math_v1/recovery_artifacts/plan.json',
        'sha256': '9e905b88991c6577377444d421f1d11043ac35190c1a5c46b8dba73f6721e1f0'},
    'runtime_adapter_config': {'path': 'cloud/runs/gradient_features_math_v1/recovery_artifacts/snapshots/update008/adapter/adapter_config.json',
        'sha256': '9508ba34ff4f9fff21096524e686f34e3e94acc9872bcdfbf1c0e7b36310ed85'},
    'remote_verification_performed_by_this_helper': False,
    'saved_header_observed_locally': False,
    'saved_key_policy': 'peft_saved is an explicit adapter-name-free convention derived from observed runtime module keys. A local saved header/PEFT serializer was unavailable; future integration must independently confirm serializer/load compatibility.',
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def validate_config(config, *, model=MODEL, revision=REVISION):
    if model != MODEL or revision != REVISION or not isinstance(config, dict):
        raise ValueError('Only the pinned Granite checkpoint configuration is supported')
    if any(type(config.get(key)) is not type(expected) or config[key] != expected
           for key, expected in CONFIG_FIELDS.items()):
        raise ValueError('Pinned Granite attention architecture differs')
    if 'head_dim' in config and (type(config['head_dim']) is not int or config['head_dim'] != HEAD_DIM):
        raise ValueError('Explicit attention head dimension differs')
    if config['hidden_size']//config['num_attention_heads'] != HEAD_DIM:
        raise ValueError('Attention dimension derivation differs')
    return {'layers': LAYERS, 'hidden_size': HIDDEN, 'head_dim': HEAD_DIM,
        'query_output_size': HEADS*HEAD_DIM, 'value_output_size': KV_HEADS*HEAD_DIM}


def validate_adapter_config(config):
    fixed = {'base_model_name_or_path': MODEL, 'peft_type': 'LORA', 'r': 8,
        'lora_alpha': 16, 'bias': 'none', 'task_type': 'CAUSAL_LM'}
    if not isinstance(config, dict) or any(type(config.get(k)) is not type(v) or config[k] != v for k, v in fixed.items()):
        raise ValueError('Adapter must use the pinned classic LoRA recipe')
    if isinstance(config.get('lora_dropout'), bool) or config.get('lora_dropout') != 0:
        raise ValueError('Adapter dropout differs')
    targets = config.get('target_modules')
    if not isinstance(targets, list) or any(not isinstance(x, str) for x in targets) or sorted(targets) != ['q_proj', 'v_proj']:
        raise ValueError('Require exactly the q/v attention projections')
    for key in ('use_rslora', 'use_dora', 'fan_in_fan_out', 'use_qalora', 'lora_bias'):
        if config.get(key, False) is not False:
            raise ValueError('Alternate LoRA behavior is unsupported')
    if any(config.get(key, {}) != {} for key in ('rank_pattern', 'alpha_pattern')):
        raise ValueError('Per-layer rank or scaling overrides are unsupported')
    if any(config.get(key) not in (None, []) for key in
            ('modules_to_save', 'layer_replication', 'exclude_modules', 'target_parameters', 'trainable_token_indices')):
        raise ValueError('Additional adapted modules or parameters are unsupported')
    if any(config.get(key) is not None for key in ('layers_to_transform', 'layers_pattern')):
        raise ValueError('The recipe must cover every q/v attention layer')
    return True


def expected_layout(config, *, model=MODEL, revision=REVISION, key_format='runtime_default'):
    """Return the exact160 tensor shapes; no permissive prefix normalization."""
    dimensions = validate_config(config, model=model, revision=revision)
    if not isinstance(key_format, str) or key_format not in KEY_FORMATS:
        raise ValueError('Unknown explicit LoRA key format')
    suffix = '.default.weight' if key_format == 'runtime_default' else '.weight'
    result = {}
    for layer in range(LAYERS):
        for projection, output in (('q_proj', dimensions['query_output_size']), ('v_proj', dimensions['value_output_size'])):
            prefix = f'base_model.model.model.layers.{layer}.self_attn.{projection}'
            result[prefix+'.lora_A'+suffix] = [RANK, HIDDEN]
            result[prefix+'.lora_B'+suffix] = [output, RANK]
    return result


def validate_layout(tensor_shapes, config, adapter_config, *, model=MODEL, revision=REVISION,
                    key_format='runtime_default'):
    """Validate complete coverage/names/shapes, not tensor values or training."""
    expected = expected_layout(config, model=model, revision=revision, key_format=key_format)
    validate_adapter_config(adapter_config)
    if (not isinstance(tensor_shapes, dict) or len(tensor_shapes) != TENSOR_COUNT
            or any(not isinstance(name, str) for name in tensor_shapes) or set(tensor_shapes) != set(expected)):
        raise ValueError('Require the exact complete160 q/v LoRA tensor keys')
    for name, shape in tensor_shapes.items():
        if (not isinstance(shape, list) or len(shape) != 2 or any(type(x) is not int for x in shape)
                or shape != expected[name]):
            raise ValueError('LoRA tensor shape differs from the pinned projection')
    parameters = sum(math.prod(shape) for shape in tensor_shapes.values())
    if parameters != PARAMETER_COUNT:
        raise ValueError('Complete LoRA parameter count differs')
    return {'version': VERSION, 'model': MODEL, 'revision': REVISION, 'key_format': key_format,
        'layers': LAYERS, 'attention_modules': 2*LAYERS, 'tensor_count': TENSOR_COUNT,
        'parameters': parameters, 'layout_sha256': digest(expected),
        'complete_expected_layout_verified': True, 'tensor_values_verified': False,
        'training_or_contemporaneous_development_weights_verified': False,
        'saved_serializer_compatibility_observed_locally': False,
        'scope': 'Exact metadata geometry and module coverage only; caller must verify file hashes, parse header safely, bind source/config provenance and enforce runtime loading before official data access.'}


def validate_header(header, payload_bytes, config, adapter_config, *, model=MODEL,
                    revision=REVISION, key_format='peft_saved'):
    """Validate already parsed safetensors header metadata and full payload span.

    The caller must reject duplicate JSON keys and check the raw format/header
    bounds; this pure function never opens a weights file or executes a model.
    """
    if not isinstance(header, dict) or type(payload_bytes) is not int or not 0 < payload_bytes <= PARAMETER_COUNT*8:
        raise ValueError('Invalid bounded header metadata or payload length')
    metadata = header.get('__metadata__', {})
    if not isinstance(metadata, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in metadata.items()):
        raise ValueError('Safetensors metadata must contain only string pairs')
    tensors = {name: value for name, value in header.items() if name != '__metadata__'}
    if any(not isinstance(value, dict) or set(value) != {'shape', 'dtype', 'data_offsets'} for value in tensors.values()):
        raise ValueError('Unexpected tensor header schema')
    result = validate_layout({name: value['shape'] for name, value in tensors.items()}, config,
        adapter_config, model=model, revision=revision, key_format=key_format)
    widths = {'F16': 2, 'BF16': 2, 'F32': 4, 'F64': 8}
    intervals = []
    for value in tensors.values():
        offsets, dtype = value['data_offsets'], value['dtype']
        if (not isinstance(dtype, str) or dtype not in widths or not isinstance(offsets, list) or len(offsets) != 2
                or any(type(x) is not int for x in offsets) or not 0 <= offsets[0] < offsets[1] <= payload_bytes
                or offsets[1]-offsets[0] != math.prod(value['shape'])*widths[dtype]):
            raise ValueError('Tensor payload interval, dtype or byte size differs')
        intervals.append(tuple(offsets))
    end = 0
    for start, stop in sorted(intervals):
        if start != end:
            raise ValueError('Tensor payload has overlaps or unaccounted gaps')
        end = stop
    if end != payload_bytes:
        raise ValueError('Tensor payload is truncated or contains trailing bytes')
    return dict(result, payload_bytes=payload_bytes, header_metadata_sha256=digest(header),
        contiguous_full_payload_verified=True)
