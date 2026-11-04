"""Portable physical source/adapter verification, without model or dataset I/O.

Callers supply explicit artifact roots, source maps and pinned metadata. Files are
hashed and JSON/safetensors headers checked; no tensor deserialization, imports
from an artifact, downloads, provider calls, source permits or dispatch occur.
Successful physical checks are not proof of a successful runtime PEFT load.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import struct

from cloud import granite_lora_layout as layout

VERSION = 'portable-granite-artifacts-v1'
PINNED_CONFIG_SHA = layout.EVIDENCE['local_config']['sha256']
MAX_JSON_BYTES = 4*1024*1024
MAX_HEADER_BYTES = 2*1024*1024
MAX_FILE_BYTES = 64*1024*1024
MAX_ADAPTER_BYTES = 256*1024*1024
MAX_ADAPTER_FILES = 256
MAX_ADAPTER_ENTRIES = 1024
HELPERS = ('final_scale_artifacts.py', 'granite_lora_layout.py')
HASH = re.compile('[a-f0-9]{64}')
DEVICES = re.compile(r'(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])', re.IGNORECASE)


def _sha(value):
    return isinstance(value, str) and HASH.fullmatch(value) is not None


def _relative(value):
    if (not isinstance(value, str) or not value or any(c in value for c in ('\\', ':', '\0'))
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError('Inventory paths must be portable, contained relative paths')
    parts = value.split('/')
    if any(not part or part in ('.', '..') or part.rstrip(' .') != part or DEVICES.fullmatch(part.split('.')[0]) for part in parts):
        raise ValueError('Inventory path traversal or platform aliases are forbidden')
    return value


def _no_links(path):
    for item in (path, *path.parents):
        if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
            raise ValueError('Artifact/source paths cannot contain symlinks or junctions')


def _path(value, *, allowed_root=None, directory=False):
    if not isinstance(value, (str, Path)):
        raise ValueError('Physical artifact path must be explicit')
    candidate = Path(value)
    if '..' in candidate.parts:
        raise ValueError('Physical artifact paths cannot contain parent traversal')
    candidate = candidate.absolute()
    _no_links(candidate)
    result = candidate.resolve(strict=True)
    if allowed_root is not None:
        boundary = _path(allowed_root, directory=True)
        if not result.is_relative_to(boundary):
            raise ValueError('Physical path escapes the explicit artifact root')
    if not (result.is_dir() if directory else result.is_file()):
        raise ValueError('Require an actual directory or regular file')
    return result


def _stable(path, limit):
    path = _path(path)
    before = path.stat()
    if not 0 <= before.st_size <= limit:
        raise ValueError('Physical file exceeds the bounded artifact envelope')
    # An offline OneDrive placeholder would require a new implicit download.
    if getattr(before, 'st_file_attributes', 0) & (0x1000 | 0x40000 | 0x400000):
        raise ValueError('Artifact must already be physically available locally')
    return path, (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)


def _unchanged(path, identity):
    _no_links(path)
    after = path.stat()
    if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != identity:
        raise ValueError('Physical artifact changed during verification')


def _record(path, *, relative, limit=MAX_FILE_BYTES):
    path, before = _stable(path, limit)
    hasher = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024*1024), b''):
            hasher.update(block)
    _unchanged(path, before)
    return {'path': relative, 'sha256': hasher.hexdigest(), 'size_bytes': before[2]}


def _pairs(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError('Duplicate JSON keys cannot identify a physical artifact')
        result[name] = value
    return result


def _constant(value):
    raise ValueError('Nonfinite JSON constants are forbidden')


def _json(raw):
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError('Physical artifact is not valid bounded UTF8 JSON') from error
    if not isinstance(value, dict):
        raise ValueError('Physical JSON artifact must be an object')
    return value


def _read_json(path):
    path, before = _stable(path, MAX_JSON_BYTES)
    raw = path.read_bytes()
    _unchanged(path, before)
    return _json(raw), hashlib.sha256(raw).hexdigest()


def _files(root):
    root = _path(root, directory=True)
    result, pending, entries = {}, [root], 0
    while pending:
        directory = _path(pending.pop(), allowed_root=root, directory=True)
        with os.scandir(directory) as listing:
            for entry in listing:
                entries += 1
                if entries > MAX_ADAPTER_ENTRIES:
                    raise ValueError('Adapter directory exceeds the bounded entry count')
                path = Path(entry.path)
                _no_links(path)
                if entry.is_dir(follow_symlinks=False):
                    pending.append(path)
                elif entry.is_file(follow_symlinks=False):
                    path = _path(path, allowed_root=root)
                    relative = _relative(path.relative_to(root).as_posix())
                    if len(result) >= MAX_ADAPTER_FILES:
                        raise ValueError('Too many adapter artifact files')
                    result[relative] = path
                else:
                    raise ValueError('Artifact entries must be regular files or directories')
    if not result:
        raise ValueError('Adapter artifact directory is empty')
    if len({name.casefold() for name in result}) != len(result):
        raise ValueError('Case aliases cannot identify portable adapter files')
    return root, {name: result[name] for name in sorted(result)}


def _expected(value):
    if not isinstance(value, dict) or not 1 <= len(value) <= MAX_ADAPTER_FILES:
        raise ValueError('An explicit nonempty hash-bound inventory is required')
    normalized = {}
    sizes = True
    for identity, entry in value.items():
        _relative(identity)
        if isinstance(entry, str):
            if not _sha(entry):
                raise ValueError('Inventory hashes must be lowercase SHA256')
            normalized[identity] = {'path': identity, 'sha256': entry, 'size_bytes': None}
            sizes = False
        elif isinstance(entry, dict) and set(entry) in ({'sha256', 'size_bytes'}, {'path', 'sha256', 'size_bytes'}):
            path = _relative(entry.get('path', identity))
            if not _sha(entry['sha256']) or type(entry['size_bytes']) is not int or not 0 <= entry['size_bytes'] <= MAX_FILE_BYTES:
                raise ValueError('Inventory hash/size metadata differs from the bounded contract')
            normalized[identity] = dict(entry, path=path)
        else:
            raise ValueError('Unsupported portable inventory entry')
    if len({entry['path'].casefold() for entry in normalized.values()}) != len(normalized):
        raise ValueError('Inventory aliases or duplicate file paths are forbidden')
    return normalized, sizes


def _header(path, config, adapter_config, key_format):
    path, before = _stable(path, MAX_FILE_BYTES)
    with path.open('rb') as handle:
        prefix = handle.read(8)
        if len(prefix) != 8:
            raise ValueError('Truncated safetensors length prefix')
        length = struct.unpack('<Q', prefix)[0]
        if not 2 <= length <= MAX_HEADER_BYTES or length % 8 or length+8 >= before[2]:
            raise ValueError('Safetensors header length/file completeness is invalid')
        raw = handle.read(length)
    _unchanged(path, before)
    if not raw.startswith(b'{'):
        raise ValueError('Safetensors header must start with a JSON object')
    header = _json(raw)
    observed = layout.validate_header(header, before[2]-8-length, config, adapter_config,
        model=layout.MODEL, revision=layout.REVISION, key_format=key_format)
    return {'header_sha256': hashlib.sha256(raw).hexdigest(), 'header_bytes': length,
        'payload_bytes': before[2]-8-length, 'layout': observed}


def _model_config(model_config_path, expected_model_config_sha256, allowed_root):
    if not _sha(expected_model_config_sha256):
        raise ValueError('A reviewed model-config raw hash is required')
    path = _path(model_config_path, allowed_root=allowed_root)
    path, before = _stable(path, MAX_JSON_BYTES)
    config, config_sha = _read_json(path)
    _unchanged(path, before)
    if config_sha != expected_model_config_sha256:
        raise ValueError('Pinned model config raw bytes differ from the reviewed hash')
    dimensions = layout.validate_config(config)
    return config, {'model': layout.MODEL, 'revision': layout.REVISION,
        'model_config_sha256': config_sha, 'size_bytes': before[2], 'dimensions': dimensions,
        'pinned_reference_config_bytes_verified': config_sha == PINNED_CONFIG_SHA,
        'runtime_model_or_peft_load_verified': False}


def verify_model_config(model_config_path, *, expected_model_config_sha256=PINNED_CONFIG_SHA, allowed_root=None):
    """Base-role metadata gate; no adapter or model is opened/instantiated."""
    return _model_config(model_config_path, expected_model_config_sha256, allowed_root)[1]


def _inspect(root, files, inventory, *, model_config_path, expected_model_config_sha256, key_format, allowed_root):
    required = ('adapter_config.json', 'adapter_model.safetensors')
    if any(name not in files for name in required):
        raise ValueError('Actual adapter config and safetensors weights are required')
    config, config_info = _model_config(model_config_path, expected_model_config_sha256, allowed_root)
    adapted, adapter_sha = _read_json(files['adapter_config.json'])
    if adapter_sha != inventory['adapter_config.json']['sha256']:
        raise ValueError('Adapter config changed after inventory hashing')
    layout.validate_adapter_config(adapted)
    weights = _header(files['adapter_model.safetensors'], config, adapted, key_format)
    hashes = {name: entry['sha256'] for name, entry in inventory.items()}
    if {name: str(path) for name, path in _files(root)[1].items()} != {name: str(path) for name, path in files.items()}:
        raise ValueError('Adapter file set changed during verification')
    # Recheck identities after config/header parsing, without loading tensors.
    for name, path in files.items():
        if path.stat().st_size != inventory[name]['size_bytes']:
            raise ValueError('Adapter file size changed after hashing')
    return {'schema_version': 1, 'version': VERSION, 'model': layout.MODEL, 'revision': layout.REVISION,
        'key_format': key_format, 'adapter_files_sha256': hashes, 'inventory': inventory,
        'adapter_inventory_sha256': layout.digest(hashes), 'physical_inventory_sha256': layout.digest(inventory),
        'model_config_sha256': config_info['model_config_sha256'], 'raw_adapter_config_sha256': adapter_sha,
        'pinned_reference_config_bytes_verified': config_info['pinned_reference_config_bytes_verified'],
        'weights': dict(weights, **inventory['adapter_model.safetensors']),
        'saved_serializer_compatibility_observed_locally': layout.EVIDENCE['saved_header_observed_locally'],
        'runtime_peft_load_verified': False, 'tensor_values_verified': False,
        'training_or_contemporaneous_development_weights_verified': False}


def inspect_adapter(adapter_dir, *, model_config_path, expected_model_config_sha256=PINNED_CONFIG_SHA,
                    key_format='peft_saved', allowed_root=None):
    root = _path(adapter_dir, allowed_root=allowed_root, directory=True)
    root, files = _files(root)
    identities = {name: _stable(path, MAX_FILE_BYTES)[1] for name, path in files.items()}
    if sum(identity[2] for identity in identities.values()) > MAX_ADAPTER_BYTES:
        raise ValueError('Adapter inventory exceeds the total byte envelope')
    inventory = {name: _record(path, relative=name) for name, path in files.items()}
    result = _inspect(root, files, inventory, model_config_path=model_config_path,
        expected_model_config_sha256=expected_model_config_sha256, key_format=key_format, allowed_root=allowed_root)
    for name, path in files.items():
        _unchanged(path, identities[name])
    return result


def verify_adapter(adapter_dir, expected_inventory, *, model_config_path,
                   expected_model_config_sha256=PINNED_CONFIG_SHA, key_format='peft_saved', allowed_root=None):
    expected, sizes = _expected(expected_inventory)
    result = inspect_adapter(adapter_dir, model_config_path=model_config_path,
        expected_model_config_sha256=expected_model_config_sha256, key_format=key_format, allowed_root=allowed_root)
    by_path = {entry['path']: entry for entry in expected.values()}
    if set(by_path) != set(result['inventory']):
        raise ValueError('Actual adapter files differ from the exact sealed inventory')
    for path, entry in by_path.items():
        actual = result['inventory'][path]
        if actual['sha256'] != entry['sha256'] or entry['size_bytes'] is not None and actual['size_bytes'] != entry['size_bytes']:
            raise ValueError('Adapter hash/size differs from the sealed bytes')
    return dict(result, expected_inventory_sha256=layout.digest(expected_inventory),
        exact_expected_inventory_verified=True, expected_inventory_included_sizes=sizes)


def verify_packaged_sources(package_root, expected_sources):
    """Verify supplied portable source paths against the actual loaded package."""
    root = _path(package_root, directory=True)
    expected, sizes = _expected(expected_sources)
    actual, hashes, by_name = {}, {}, {}
    for identity, entry in expected.items():
        if not entry['path'].endswith('.py'):
            raise ValueError('Source inventory can contain only reviewed Python files')
        path = _path(root/entry['path'], allowed_root=root)
        observed = _record(path, relative=entry['path'], limit=MAX_JSON_BYTES)
        if observed['sha256'] != entry['sha256'] or entry['size_bytes'] is not None and observed['size_bytes'] != entry['size_bytes']:
            raise ValueError('Packaged source bytes differ from the reviewed inventory')
        actual[identity], hashes[identity] = observed, observed['sha256']
        by_name.setdefault(path.name, []).append(path)
    loaded = {'final_scale_artifacts.py': Path(__file__).resolve(),
        'granite_lora_layout.py': Path(layout.__file__).resolve()}
    if any(by_name.get(name) != [path] for name, path in loaded.items()):
        raise ValueError('Reviewed package must bind these exact loaded artifact/layout helpers')
    return {'version': VERSION, 'verified_file_count': len(actual), 'inventory': actual,
        'source_hashes': hashes, 'source_bundle_sha256': layout.digest(hashes),
        'expected_inventory_sha256': layout.digest(expected_sources),
        'physical_inventory_sha256': layout.digest(actual), 'expected_inventory_included_sizes': sizes,
        'packaged_source_hashes_verified': True, 'runtime_model_or_peft_load_verified': False}


if __name__ == '__main__':
    print(json.dumps({'stage': 'implementation_only_no_artifacts_opened', 'version': VERSION,
        'runtime_peft_load_verified': False, 'providers_called': False, 'official_data_accessed': False}))
