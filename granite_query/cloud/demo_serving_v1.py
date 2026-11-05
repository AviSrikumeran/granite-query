"""Offline contract for an explicitly experimental, single-variant demo.

This module never imports Modal, deploys, uploads weights, reserves funds, or
changes a funding ledger. A supplied private artifact manifest names the chosen
variant; no final-model selection or improvement is inferred. The allowance is
an operator authorization, not a provider balance or an invoice cap.

Admission requires a store with atomic put(..., skip_if_exists=True). Claims
are never refunded or retried. Modal Dict's inactivity TTL exceeds this <=24h
trial, but records are not represented as permanent provider archival storage.
"""
import argparse
import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import uuid

MODEL = 'ibm-granite/granite-4.2-3b'
REVISION = '4e9c275e232f10211ec88644d106a1f6a1b60e06'
BASE_CONFIG_SHA256 = 'e4f44b9c6924a283f1d1d36057a89f1a04404bf1561fc2c0b64cf98180e72915'
CONTRACT = 'granite-query-experimental-demo-v1'
DICT_NAME = 'granite-query-experimental-demo-admission-v1'
PREFIX = ('Solve the math problem. Explain only the necessary calculation steps concisely. '
          'Finish with #### followed by the numeric final answer.\n\n')
TARGETS = frozenset(('q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj'))
LIMITS = dict(max_requests=20, max_input_chars=2400, max_input_tokens=768,
              max_output_tokens=512, max_body_bytes=16384, context_limit=2048,
              gpu='L4', max_containers=1, min_containers=0, buffer_containers=0,
              timeout_seconds=90, startup_timeout_seconds=60,
              scaledown_window_seconds=2, single_use_containers=True,
              cpu_cores=1, memory_mib=12288)
SUPPORTED_GPUS = ('L4', 'A10G')
PUBLIC_LIMITS = ('max_requests', 'max_input_chars', 'max_input_tokens',
                 'max_output_tokens', 'context_limit')


class DemoRefused(ValueError):
    def __init__(self, message, status_code=503):
        super().__init__(message)
        self.status_code = status_code


def utcnow():
    return datetime.now(timezone.utc)


def stamp(value):
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise DemoRefused('An offset-aware timestamp is required')
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def parse_time(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError):
        raise DemoRefused('Invalid offset-aware timestamp') from None


def digest(value):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (ValueError, TypeError):
        raise DemoRefused('Contract must contain finite JSON values') from None
    return hashlib.sha256(raw).hexdigest()


def _name(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', value))


def _hash(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[a-f0-9]{64}', value))


def _keys(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise DemoRefused('Invalid ' + label + ' fields')


def _relative(value):
    return (isinstance(value, str) and 0 < len(value) <= 200 and '\\' not in value
            and not PurePosixPath(value).is_absolute()
            and all(_name(part) and part not in ('.', '..') for part in value.split('/')))


def _inventory(value):
    if not isinstance(value, dict) or not value or len(value) > 64:
        raise DemoRefused('Explicit artifact hash inventory required')
    if any(not _name(name) or not _hash(sha) for name, sha in value.items()):
        raise DemoRefused('Artifact filenames and SHA256 values must be explicit')


def validate_adapter_config(config):
    if (not isinstance(config, dict) or config.get('peft_type') != 'LORA'
            or config.get('task_type') != 'CAUSAL_LM' or type(config.get('r')) is not int
            or config['r'] != 16 or config.get('bias') != 'none'
            or not isinstance(config.get('target_modules'), list)
            or any(not isinstance(name, str) for name in config['target_modules'])
            or len(config['target_modules']) != len(TARGETS)
            or set(config['target_modules']) != TARGETS
            or config.get('modules_to_save') is not None
            or config.get('rank_pattern') not in (None, {})
            or config.get('target_parameters') is not None
            or config.get('auto_mapping') is not None):
        raise DemoRefused('Expected the explicit rank-16 causal-LM LoRA target layout')
    return config


def validate_artifact(artifact):
    _keys(artifact, ('schema_version', 'variant', 'checkpoint_id', 'model', 'revision',
                     'base', 'adapter', 'evaluation', 'provenance_sha256'), 'artifact manifest')
    if type(artifact['schema_version']) is not int or artifact['schema_version'] != 1:
        raise DemoRefused('Unsupported artifact manifest version')
    if artifact['variant'] not in ('base', 'correction') or not _name(artifact['checkpoint_id']):
        raise DemoRefused('Choose one explicit base or correction deployment variant')
    if artifact['model'] != MODEL or artifact['revision'] != REVISION or not _hash(artifact['provenance_sha256']):
        raise DemoRefused('Pinned model and immutable provenance hash required')
    base = artifact['base']
    _keys(base, ('volume_name', 'volume_subpath', 'files_sha256'), 'private base bundle')
    if not _name(base['volume_name']) or not _relative(base['volume_subpath']):
        raise DemoRefused('Explicit private base-volume location required')
    files = base['files_sha256']
    _inventory(files)
    if (files.get('config.json') != BASE_CONFIG_SHA256
            or not {'tokenizer.json', 'tokenizer_config.json'} <= set(files)
            or not {'model.safetensors', 'model.safetensors.index.json'} & set(files)
            or not any(name.endswith('.safetensors') for name in files)
            or any(not (name.endswith(('.json', '.safetensors', '.txt'))
                        or name in {'tokenizer.model', 'chat_template.jinja'}) for name in files)):
        raise DemoRefused('Base bundle requires pinned config, tokenizer and safetensors hashes')
    adapter = artifact['adapter']
    if artifact['variant'] == 'base':
        if adapter is not None:
            raise DemoRefused('Base deployments must not attach an adapter')
    else:
        _keys(adapter, ('files_sha256', 'config'), 'correction adapter')
        _inventory(adapter['files_sha256'])
        if set(adapter['files_sha256']) != {'adapter_config.json', 'adapter_model.safetensors'}:
            raise DemoRefused('Only the two explicitly hashed adapter files are allowed')
        validate_adapter_config(adapter['config'])
    measured = artifact['evaluation']
    _keys(measured, ('stage', 'correct', 'n', 'split_role', 'report_url', 'artifact_sha256'), 'recorded evaluation')
    if (measured['stage'] != 'completed' or measured['split_role'] != 'development_monitoring'
            or type(measured['n']) is not int or measured['n'] < 1
            or type(measured['correct']) is not int or not 0 <= measured['correct'] <= measured['n']
            or not _hash(measured['artifact_sha256'])
            or not isinstance(measured['report_url'], str)
            or not re.fullmatch(r'https://avisrikumeran\.github\.io/granite-query/[A-Za-z0-9_./-]+', measured['report_url'])
            or '..' in measured['report_url']):
        raise DemoRefused('Explicit completed development evidence is required; no final-test claim')
    return artifact


def _allowance(value):
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise DemoRefused('A positive finite Decimal serving allowance is required')
    return value


def _selected_limits(gpu):
    if gpu not in SUPPORTED_GPUS:
        raise DemoRefused('Explicit GPU choice must be L4 or A10G')
    return dict(LIMITS, gpu=gpu)


def prepare(artifact, *, quota_namespace, budget_authorization, serving_allowance,
            expires_at, now=None, gpu='L4'):
    """Return a new contract without cloud calls or any financial mutation."""
    now = now or utcnow()
    validate_artifact(artifact)
    value = dict(schema_version=1, contract=CONTRACT, experimental=True,
                 checkpoint_improvement_established=False, artifact=copy.deepcopy(artifact),
                 artifact_manifest_sha256=digest(artifact), quota_namespace=quota_namespace,
                 budget_authorization=budget_authorization,
                 serving_allowance_usd=str(_allowance(serving_allowance)),
                 issued_at_utc=stamp(now), expires_at_utc=stamp(expires_at),
                 limits=_selected_limits(gpu))
    value['manifest_sha256'] = digest(value)
    return validate_manifest(value, now=now)


def validate_manifest(manifest, *, now=None):
    _keys(manifest, ('schema_version', 'contract', 'experimental', 'checkpoint_improvement_established',
                     'artifact', 'artifact_manifest_sha256', 'quota_namespace', 'budget_authorization',
                     'serving_allowance_usd', 'issued_at_utc', 'expires_at_utc', 'limits', 'manifest_sha256'), 'demo contract')
    unsigned = {k: v for k, v in manifest.items() if k != 'manifest_sha256'}
    if not _hash(manifest['manifest_sha256']) or digest(unsigned) != manifest['manifest_sha256']:
        raise DemoRefused('Immutable demo contract hash mismatch')
    limits = manifest['limits']
    if not isinstance(limits, dict):
        raise DemoRefused('Experimental serving limits must be explicit')
    expected_limits = _selected_limits(limits.get('gpu'))
    if (type(manifest['schema_version']) is not int or manifest['schema_version'] != 1
            or manifest['contract'] != CONTRACT or manifest['experimental'] is not True
            or manifest['checkpoint_improvement_established'] is not False
            or limits != expected_limits
            or any(type(limits[key]) is not type(expected) for key, expected in expected_limits.items())):
        raise DemoRefused('Experimental fixed serving policy changed')
    validate_artifact(manifest['artifact'])
    if manifest['artifact_manifest_sha256'] != digest(manifest['artifact']):
        raise DemoRefused('Artifact provenance changed')
    if not _name(manifest['quota_namespace']):
        raise DemoRefused('An explicit fresh quota namespace is required')
    authorization = manifest['budget_authorization']
    if not isinstance(authorization, str) or not authorization.strip() or len(authorization) > 500:
        raise DemoRefused('An explicit budget authorization reference is required')
    if not isinstance(manifest['serving_allowance_usd'], str):
        raise DemoRefused('Serving allowance must be an explicit decimal string')
    try:
        _allowance(Decimal(manifest['serving_allowance_usd']))
    except (InvalidOperation, TypeError):
        raise DemoRefused('Invalid serving allowance') from None
    issued, expires = parse_time(manifest['issued_at_utc']), parse_time(manifest['expires_at_utc'])
    if not timedelta(0) < expires - issued <= timedelta(hours=24):
        raise DemoRefused('Trial window must be positive and at most 24 hours')
    now = now or utcnow()
    if not issued <= now < expires:
        raise DemoRefused('Experimental trial expired or has not begun', 410)
    return manifest


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DemoRefused('Duplicate JSON fields are not allowed')
        result[key] = value
    return result


def read(path):
    def reject_constant(_):
        raise DemoRefused('Nonfinite JSON values are not allowed')
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=_pairs,
                      parse_constant=reject_constant)


def verify_files(folder, inventory, *, weights=True):
    """Hash only explicitly named flat files; refuse links and path escapes."""
    _inventory(inventory)
    root = Path(folder).resolve(strict=True)
    entries = list(root.iterdir())
    if (any(path.is_symlink() or not path.is_file() for path in entries)
            or {path.name for path in entries} != set(inventory)):
        raise DemoRefused('Private artifact bundle must contain exactly its inventoried regular files')
    for name, expected in inventory.items():
        if not weights and name.endswith('.safetensors'):
            continue
        path = root / name
        if path.is_symlink() or not path.is_file() or path.resolve().parent != root:
            raise DemoRefused('Artifact file missing or not a regular bundle file')
        sha = hashlib.sha256()
        with path.open('rb') as handle:
            for part in iter(lambda: handle.read(8 * 1024 * 1024), b''):
                sha.update(part)
        if sha.hexdigest() != expected:
            raise DemoRefused('Artifact bytes differ from the explicit manifest')
    index = root / 'model.safetensors.index.json'
    if index.exists():
        if index.name not in inventory:
            raise DemoRefused('Unhashed model index is not allowed')
        mapping = read(index).get('weight_map')
        if (not isinstance(mapping, dict) or not mapping
                or any(not isinstance(name, str) or not name.endswith('.safetensors')
                       or name not in inventory for name in mapping.values())):
            raise DemoRefused('Every indexed model shard must be explicitly hashed')


def verify_adapter(folder, artifact):
    validate_artifact(artifact)
    if artifact['variant'] != 'correction':
        raise DemoRefused('No adapter belongs to this deployment')
    verify_files(folder, artifact['adapter']['files_sha256'])
    actual = read(Path(folder) / 'adapter_config.json')
    validate_adapter_config(actual)
    if actual != artifact['adapter']['config']:
        raise DemoRefused('Adapter configuration differs from its inspected manifest')


def public_model(manifest):
    """Gateway-compatible allowlist; never expose private paths or authorization."""
    artifact = manifest['artifact']
    measured = artifact['evaluation']
    return dict(schema_version=1, experimental=True, model=MODEL, revision=REVISION,
                checkpoint_id=artifact['checkpoint_id'], variant=artifact['variant'],
                supported_variants=[artifact['variant']],
                training_method='None; original checkpoint' if artifact['variant'] == 'base' else 'LoRA sequence supervised fine-tuning',
                checkpoint_improvement_established=False,
                measured_accuracy={k: measured[k] for k in ('correct', 'n', 'split_role', 'report_url')},
                expires_at_utc=manifest['expires_at_utc'],
                limits={k: LIMITS[k] for k in PUBLIC_LIMITS},
                note='Experimental single-variant trial. Development evidence is not a serving benchmark. '
                     'Cold/warm latency and selected-GPU accuracy are unverified. Failed or cancelled requests consume quota. '
                     'The request envelope is not a provider-enforced invoice cap.')


def validate_request(body, *, variant=None):
    if not isinstance(body, dict) or set(body) - {'prompt', 'max_new_tokens', 'request_id', 'variant'}:
        raise DemoRefused('Expected prompt, UUID request_id and optional max_new_tokens only', 422)
    prompt, cap = body.get('prompt'), body.get('max_new_tokens', LIMITS['max_output_tokens'])
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > LIMITS['max_input_chars']:
        raise DemoRefused('Prompt must contain 1 to 2400 characters', 422)
    if type(cap) is not int or not 1 <= cap <= LIMITS['max_output_tokens']:
        raise DemoRefused('max_new_tokens must be an integer from 1 to 512', 422)
    if 'variant' in body and (variant not in ('base', 'correction') or body['variant'] != variant):
        raise DemoRefused('Request variant differs from this single-variant deployment', 422)
    raw_id = body.get('request_id')
    if not isinstance(raw_id, str) or not re.fullmatch(r'[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}', raw_id):
        raise DemoRefused('A canonical UUID request_id is required', 422)
    return dict(prompt=prompt.strip(), max_new_tokens=cap, request_id=str(uuid.UUID(raw_id)))


class Admission:
    """Atomic, nonrefundable permits. No release, reset, or recovery operation."""
    def __init__(self, store, manifest):
        self.store, self.manifest = store, copy.deepcopy(manifest)
        self.prefix = 'experimental:v1:' + manifest['quota_namespace'] + ':'

    def initialize(self, *, now=None):
        validate_manifest(self.manifest, now=now)
        expected = {'manifest_sha256': self.manifest['manifest_sha256'], 'enabled': True}
        prior = self.store.get(self.prefix + 'control')
        if prior is None and self.used():
            raise DemoRefused('Orphaned permits cannot be reset')
        added = self.store.put(self.prefix + 'control', expected, skip_if_exists=True)
        if self.store.get(self.prefix + 'control') != expected:
            raise DemoRefused('Namespace is disabled, ambiguous, or belongs to another contract')
        return {'initialized': True, 'new': added}

    def ready(self, *, now=None):
        validate_manifest(self.manifest, now=now)
        expected = {'manifest_sha256': self.manifest['manifest_sha256'], 'enabled': True}
        if self.store.get(self.prefix + 'control') != expected:
            raise DemoRefused('Trial is not explicitly initialized or has been disabled')

    def used(self):
        return sum(self.store.get(self.prefix + f'slot:{i}') is not None for i in range(20))

    def claim(self, body, *, now=None):
        now = now or utcnow()
        self.ready(now=now)
        body = validate_request(body, variant=self.manifest['artifact']['variant'])
        if self.used() >= 20:
            raise DemoRefused('The 20-request experimental quota is exhausted', 429)
        fingerprint = digest(body)
        nonce = self.prefix + 'request:' + body['request_id']
        claim = {'payload_sha256': fingerprint}
        if not self.store.put(nonce, claim, skip_if_exists=True):
            raise DemoRefused('Request already attempted; no retry is allowed', 409)
        if self.store.get(nonce) != claim:
            raise DemoRefused('Request claim persistence is ambiguous; do not retry')
        record = dict(request_id=body['request_id'], payload_sha256=fingerprint,
                      manifest_sha256=self.manifest['manifest_sha256'], admitted_at_utc=stamp(now))
        for i in range(20):
            key = self.prefix + f'slot:{i}'
            if self.store.put(key, record, skip_if_exists=True):
                if self.store.get(key) != record:
                    raise DemoRefused('Permit acknowledgement is ambiguous; request consumed')
                return dict(record, slot=i)
        raise DemoRefused('The 20-request experimental quota is exhausted', 429)

    def _ticket(self, ticket, body, *, now=None):
        self.ready(now=now)
        _keys(ticket, ('request_id', 'payload_sha256', 'manifest_sha256', 'admitted_at_utc', 'slot'), 'admission ticket')
        i = ticket['slot']
        if type(i) is not int or not 0 <= i < 20:
            raise DemoRefused('Invalid permit index')
        expected = {k: v for k, v in ticket.items() if k != 'slot'}
        body = validate_request(body, variant=self.manifest['artifact']['variant'])
        if (self.store.get(self.prefix + f'slot:{i}') != expected
                or ticket['manifest_sha256'] != self.manifest['manifest_sha256']
                or body['request_id'] != ticket['request_id'] or digest(body) != ticket['payload_sha256']
                or self.store.get(self.prefix + 'request:' + body['request_id']) != {'payload_sha256': digest(body)}):
            raise DemoRefused('Ticket does not match the immutable persisted request')
        return i, {'request_id': body['request_id'], 'payload_sha256': digest(body)}

    def mark_dispatch(self, ticket, body, *, now=None):
        i, record = self._ticket(ticket, body, now=now)
        key = self.prefix + f'dispatch:{i}'
        if not self.store.put(key, record, skip_if_exists=True):
            raise DemoRefused('Dispatch already attempted; no retry is allowed', 409)
        if self.store.get(key) != record:
            raise DemoRefused('Dispatch persistence is ambiguous; do not retry')

    def mark_worker(self, ticket, body, *, now=None):
        i, record = self._ticket(ticket, body, now=now)
        if self.store.get(self.prefix + f'dispatch:{i}') != record:
            raise DemoRefused('Worker lacks an authorized dispatch')
        key = self.prefix + f'worker:{i}'
        if not self.store.put(key, record, skip_if_exists=True):
            raise DemoRefused('Worker already attempted; no retry is allowed', 409)
        if self.store.get(key) != record:
            raise DemoRefused('Worker persistence is ambiguous; do not retry')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prepare_args = sub.add_parser('prepare')
    for arg in ('artifact-manifest', 'quota-namespace', 'budget-authorization', 'serving-allowance-usd', 'expires-at', 'output'):
        prepare_args.add_argument('--' + arg, required=True)
    prepare_args.add_argument('--gpu', choices=SUPPORTED_GPUS, default='L4')
    validate_args = sub.add_parser('validate')
    validate_args.add_argument('--manifest', required=True)
    args = parser.parse_args()
    if args.command == 'validate':
        validate_manifest(read(args.manifest))
    else:
        value = prepare(read(args.artifact_manifest), quota_namespace=args.quota_namespace,
                        budget_authorization=args.budget_authorization,
                        serving_allowance=Decimal(args.serving_allowance_usd),
                        expires_at=parse_time(args.expires_at), gpu=args.gpu)
        with Path(args.output).open('x', encoding='utf-8', newline='\n') as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write('\n')
    print(json.dumps({'valid': True, 'deployed': False, 'cloud_calls': False}))


if __name__ == '__main__':
    main()
