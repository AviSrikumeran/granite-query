"""Offline fixtures and atomic mock-store tests; Modal is never imported."""
import ast
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
import uuid

from .demo_serving_v1 import (Admission, BASE_CONFIG_SHA256, MODEL, REVISION, TARGETS,
    DemoRefused, digest, prepare, public_model, read, validate_artifact,
    validate_manifest, validate_request, verify_adapter, verify_files)

NOW = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)


class AtomicStore:
    def __init__(self):
        self.data, self.lock = {}, threading.Lock()

    def get(self, key):
        with self.lock:
            return copy.deepcopy(self.data.get(key))

    def put(self, key, value, *, skip_if_exists=False):
        assert skip_if_exists is True, 'All writes must be conditional'
        with self.lock:
            if key in self.data:
                return False
            self.data[key] = copy.deepcopy(value)
            return True


def artifact(variant='correction'):
    # Deliberately fictional test records, never claimed research outcomes.
    config = {'peft_type': 'LORA', 'task_type': 'CAUSAL_LM', 'r': 16, 'bias': 'none',
              'target_modules': sorted(TARGETS), 'modules_to_save': None, 'rank_pattern': {}}
    return dict(schema_version=1, model=MODEL, revision=REVISION, variant=variant,
        checkpoint_id='test-only-' + variant, provenance_sha256='a' * 64,
        base={'volume_name': 'private-test-only', 'volume_subpath': 'pinned/bundle',
              'files_sha256': {'config.json': BASE_CONFIG_SHA256, 'tokenizer.json': 'b' * 64,
                              'tokenizer_config.json': 'c' * 64, 'model.safetensors': 'd' * 64}},
        adapter=None if variant == 'base' else {'config': config,
            'files_sha256': {'adapter_config.json': 'e' * 64, 'adapter_model.safetensors': 'f' * 64}},
        evaluation={'stage': 'completed', 'correct': 0, 'n': 1,
            'split_role': 'development_monitoring', 'artifact_sha256': '1' * 64,
            'report_url': 'https://avisrikumeran.github.io/granite-query/overnight-results.html'})


def manifest(variant='correction', **kwargs):
    params = dict(quota_namespace='test-only-namespace', budget_authorization='TEST ONLY: not funding',
                  serving_allowance=Decimal('1.00'), expires_at=NOW + timedelta(hours=2), now=NOW)
    params.update(kwargs)
    return prepare(artifact(variant), **params)


def body():
    return {'prompt': 'What is 2 + 3?', 'request_id': str(uuid.uuid4()), 'max_new_tokens': 64}


def resign(value):
    value['manifest_sha256'] = digest({k: v for k, v in value.items() if k != 'manifest_sha256'})
    return value


class ContractTests(unittest.TestCase):
    def test_explicit_base_and_correction_without_final_choice(self):
        for variant in ('base', 'correction'):
            value = manifest(variant)
            self.assertEqual(validate_manifest(value, now=NOW), value)
            self.assertEqual(value['artifact']['variant'], variant)
            self.assertNotIn('selection', value)
            self.assertNotIn('final_choice', value)
            self.assertTrue(value['experimental'])
            self.assertFalse(value['checkpoint_improvement_established'])

    def test_no_default_variant_unpinned_model_or_added_claim(self):
        for key, value in [('variant', None), ('revision', 'main'), ('model', 'other'),
                           ('checkpoint_id', ''), ('final_choice', True), ('improved', True)]:
            candidate = artifact()
            candidate[key] = value
            with self.subTest(key=key), self.assertRaises(DemoRefused):
                validate_artifact(candidate)

    def test_no_funds_default_or_nonfinite_allowance(self):
        for amount in ('1', 1, True, Decimal(0), Decimal('-1'), Decimal('NaN'), Decimal('Infinity')):
            with self.subTest(amount=str(amount)), self.assertRaises(DemoRefused):
                manifest(serving_allowance=amount)
        for kwargs in ({'budget_authorization': ''}, {'quota_namespace': '../other'}):
            with self.assertRaises(DemoRefused):
                manifest(**kwargs)

    def test_launch_window_and_expiry(self):
        for hours in (-1, 0, 24.001):
            with self.assertRaises(DemoRefused):
                manifest(expires_at=NOW + timedelta(hours=hours))
        value = manifest(expires_at=NOW + timedelta(hours=24))
        for when in (NOW - timedelta(seconds=1), NOW + timedelta(hours=24)):
            with self.assertRaises(DemoRefused) as caught:
                validate_manifest(value, now=when)
            self.assertEqual(caught.exception.status_code, 410)

    def test_manifest_hash_artifact_hash_and_fixed_limit(self):
        value = manifest()
        value['artifact']['checkpoint_id'] = 'changed'
        with self.assertRaises(DemoRefused):
            validate_manifest(value, now=NOW)
        with self.assertRaises(DemoRefused):
            validate_manifest(resign(value), now=NOW)
        value = manifest()
        value['limits']['max_requests'] = 21
        with self.assertRaises(DemoRefused):
            validate_manifest(resign(value), now=NOW)

    def test_rank16_targets_only_and_development_evidence(self):
        for change in ({'r': 8}, {'target_modules': ['all-linear']}, {'target_modules': [{}]},
                       {'modules_to_save': ['lm_head']}, {'rank_pattern': {'q_proj': 32}}):
            candidate = artifact()
            candidate['adapter']['config'].update(change)
            with self.subTest(change=change), self.assertRaises(DemoRefused):
                validate_artifact(candidate)
        candidate = artifact()
        candidate['evaluation']['split_role'] = 'final_test'
        with self.assertRaises(DemoRefused):
            validate_artifact(candidate)

    def test_metadata_allowlist_and_unverified_latency(self):
        metadata = public_model(manifest())
        self.assertEqual(metadata['variant'], 'correction')
        self.assertEqual(metadata['measured_accuracy']['split_role'], 'development_monitoring')
        self.assertFalse(metadata['checkpoint_improvement_established'])
        self.assertIn('unverified', metadata['note'])
        for private in ('private-test-only', 'pinned/bundle', 'budget_authorization', 'serving_allowance'):
            self.assertNotIn(private, json.dumps(metadata))

    def test_private_json_duplicates_and_nonfinite_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent / '.test_work') as directory:
            path = Path(directory) / 'test.json'
            for raw in ('{"x":1,"x":2}', '{"x":NaN}'):
                path.write_text(raw)
                with self.assertRaises(DemoRefused):
                    read(path)

    def test_adapter_hashes_and_configuration_checked(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent / '.test_work') as directory:
            candidate, root = artifact(), Path(directory)
            (root / 'adapter_config.json').write_text(json.dumps(candidate['adapter']['config']))
            (root / 'adapter_model.safetensors').write_bytes(b'OFFLINE FIXTURE: NOT A REAL MODEL')
            candidate['adapter']['files_sha256'] = {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
            verify_adapter(root, candidate)
            (root / 'adapter_model.safetensors').write_bytes(b'tampered')
            with self.assertRaises(DemoRefused):
                verify_adapter(root, candidate)

    def test_unhashed_canonical_weights_and_index_shards_rejected(self):
        candidate = artifact('base')
        candidate['base']['files_sha256']['foo.safetensors'] = candidate['base']['files_sha256'].pop('model.safetensors')
        with self.assertRaises(DemoRefused):
            validate_artifact(candidate)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent / '.test_work') as directory:
            root = Path(directory)
            (root / 'config.json').write_bytes(b'fixture')
            inventory = {'config.json': hashlib.sha256(b'fixture').hexdigest()}
            (root / 'model.safetensors').write_bytes(b'uninventoried fixture')
            with self.assertRaises(DemoRefused):
                verify_files(root, inventory)
            (root / 'model.safetensors').unlink()
            index = root / 'model.safetensors.index.json'
            index.write_text('{"weight_map":{"x":"unhashed.safetensors"}}')
            inventory[index.name] = hashlib.sha256(index.read_bytes()).hexdigest()
            with self.assertRaises(DemoRefused):
                verify_files(root, inventory)


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.store, self.value = AtomicStore(), manifest()
        self.gate = Admission(self.store, self.value)
        self.gate.initialize(now=NOW)

    def test_bad_request_never_consumes_permit(self):
        for key, value in [('prompt', ''), ('prompt', 'x' * 2401), ('max_new_tokens', True),
                           ('max_new_tokens', 513), ('request_id', 'bad'), ('variant', 'base')]:
            request = dict(body(), **{key: value})
            with self.subTest(key=key), self.assertRaises(DemoRefused):
                self.gate.claim(request, now=NOW)
        self.assertEqual(self.gate.used(), 0)

    def test_gateway_shape_and_matching_variant(self):
        request = dict(body(), variant='correction')
        canonical = validate_request(request, variant='correction')
        self.assertNotIn('variant', canonical)
        self.assertEqual(canonical['max_new_tokens'], 64)

    def test_uuid_replay_or_changed_payload_cannot_retry(self):
        request = body()
        self.gate.claim(request, now=NOW)
        for retry in (request, dict(request, prompt='Changed')):
            with self.assertRaises(DemoRefused) as caught:
                self.gate.claim(retry, now=NOW)
            self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.gate.used(), 1)

    def test_concurrent_containers_share_twenty_atomic_permits(self):
        def attempt(_):
            try:
                return Admission(self.store, self.value).claim(body(), now=NOW)['slot']
            except DemoRefused as error:
                return error.status_code
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(attempt, range(60)))
        slots = [value for value in results if value < 20]
        self.assertEqual(len(slots), 20)
        self.assertEqual(len(set(slots)), 20)
        self.assertEqual(results.count(429), 40)

    def test_dispatch_worker_markers_permanent_once_only(self):
        request = body()
        ticket = self.gate.claim(request, now=NOW)
        with self.assertRaises(DemoRefused):
            self.gate.mark_worker(ticket, request, now=NOW)
        self.gate.mark_dispatch(ticket, request, now=NOW)
        with self.assertRaises(DemoRefused):
            self.gate.mark_dispatch(ticket, request, now=NOW)
        self.gate.mark_worker(ticket, request, now=NOW)
        with self.assertRaises(DemoRefused):
            self.gate.mark_worker(ticket, request, now=NOW)
        self.assertEqual(self.gate.used(), 1)

    def test_changed_ticket_payload_and_expired_dispatch_rejected(self):
        request = body()
        ticket = self.gate.claim(request, now=NOW)
        with self.assertRaises(DemoRefused):
            self.gate.mark_dispatch(dict(ticket, slot=True), request, now=NOW)
        with self.assertRaises(DemoRefused):
            self.gate.mark_dispatch(ticket, dict(request, prompt='Other'), now=NOW)
        with self.assertRaises(DemoRefused):
            self.gate.mark_dispatch(ticket, request, now=NOW + timedelta(hours=3))

    def test_controls_fail_closed_and_cannot_reset(self):
        with self.assertRaises(DemoRefused):
            Admission(AtomicStore(), self.value).claim(body(), now=NOW)
        self.assertFalse(self.gate.initialize(now=NOW)['new'])
        self.store.data[self.gate.prefix + 'control']['enabled'] = False
        with self.assertRaises(DemoRefused):
            self.gate.initialize(now=NOW)

    def test_ambiguous_ack_consumes_request_without_dispatch(self):
        original = self.store.get
        self.store.get = lambda key: {'ambiguous': True} if ':slot:' in key and original(key) is not None else original(key)
        request = body()
        with self.assertRaises(DemoRefused):
            self.gate.claim(request, now=NOW)
        self.store.get = original
        with self.assertRaises(DemoRefused):
            self.gate.claim(request, now=NOW)
        self.assertEqual(self.gate.used(), 1)
        self.assertFalse(any(':dispatch:' in key for key in self.store.data))


class ModalSourceTests(unittest.TestCase):
    def test_declarative_envelope_and_proxy_auth_without_import(self):
        tree = ast.parse(Path(__file__).with_name('modal_demo_api_v1.py').read_text())
        functions = {item.name: item for item in ast.walk(tree) if isinstance(item, ast.FunctionDef)}
        def keywords(name, kind):
            return [{kw.arg: ast.literal_eval(kw.value) for kw in dec.keywords
                     if isinstance(kw.value, (ast.Constant, ast.Tuple))}
                    for dec in functions[name].decorator_list if isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute) and dec.func.attr == kind]
        gpu = keywords('generate_once', 'function')[0]
        for key, expected in {'gpu': 'L4', 'timeout': 90, 'startup_timeout': 60, 'retries': 0,
            'max_containers': 1, 'min_containers': 0, 'buffer_containers': 0,
            'scaledown_window': 2, 'single_use_containers': True}.items():
            self.assertEqual(gpu[key], expected)
        self.assertEqual(keywords('web', 'asgi_app'), [{'requires_proxy_auth': True}])
        source_loop = next(item for item in ast.walk(functions['attach_source']) if isinstance(item, ast.For))
        self.assertEqual(ast.literal_eval(source_loop.iter), ('demo_serving_v1.py', 'modal_demo_api_v1.py'))
        package_creation = [item for item in ast.walk(tree) if isinstance(item, ast.Call)
                            and isinstance(item.func, ast.Attribute) and item.func.attr == 'run_commands']
        self.assertEqual(len(package_creation), 1)
        self.assertEqual([ast.literal_eval(arg) for arg in package_creation[0].args],
                         ['mkdir -p /root/cloud', 'touch /root/cloud/__init__.py'])
        source = ast.unparse(tree)
        for text in ('read_only=True', 'create_if_missing=False', 'local_files_only=True'):
            self.assertIn(text, source)
        for text in ('add_local_dir', '.deploy(', '.spawn(', 'from_pretrained(MODEL'):
            self.assertNotIn(text, source)


if __name__ == '__main__':
    unittest.main()
