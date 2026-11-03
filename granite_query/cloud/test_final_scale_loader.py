"""All source rows, seals and owners below are invented; no official data I/O."""
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cloud import final_scale_contract as contract_api
from cloud import final_scale_loader as loader


def synthetic_rows():
    return [{'question': f'INVENTED fixture {index}: add2 and5. Unicode π\u2028kept\u0085too.',
        'answer': 'INVENTED_REFERENCE calculate2+5.\n#### 7'} for index in range(1319)]


def synthetic_raw(rows=None):
    return b''.join(loader.encoded(row) for row in (synthetic_rows() if rows is None else rows))


def source_metadata(count=1000):
    names = ('final_scale_contract.py', 'final_scale_receipts.py', 'final_scale_loader.py',
        'fixture_granite.py', 'fixture_teacher.py', 'fixture_checkpoint.py',
        'fixture_image.py', 'fixture_scoring.py', 'fixture_paired.py')
    roles = {role: [name] for role, name in zip(contract_api.SOURCE_ROLES, names)}
    hashes = {name: loader.sha_bytes(('INVENTED '+name).encode()) for name in names}
    hashes['final_scale_loader.py'] = loader.sha_bytes(Path(loader.__file__).read_bytes())
    selected = {'model': contract_api.MODEL, 'revision': contract_api.REVISION, 'checkpoint_id': 'fixture-selected',
        'adapter_inventory_sha256': 'a'*64, 'development_evidence_sha256': 'b'*64}
    return contract_api.build_contract(count, source_hashes=hashes, source_roles=roles, selected=selected)


class ScaleLoaderTests(unittest.TestCase):
    def setUp(self):
        parent = loader.ROOT/'runs/local_check_tmp'; parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=parent); self.root = Path(self.temporary.name).resolve()
        self.addCleanup(self.temporary.cleanup)
        self.folder = self.root/'seal'; self.folder.mkdir(); self.output = self.root/'input'
        checkpoint = self.root/'chosen-run'; checkpoint.mkdir()
        self.registry = self.root/'global/final_test_access.json'
        self.contract = source_metadata()
        self.owner = 'fixture-source-owner'
        stamp = datetime.now(timezone.utc).isoformat()
        funding = {'observed_at_utc': {'modal': stamp, 'deepseek': stamp},
            'new_paid_work_allowed': {'modal': True, 'deepseek': True}, 'limits_usd': {'modal': '30', 'deepseek': '20'},
            'spent_usd': {'modal': '0', 'deepseek': '0'}, 'reserved_usd': {'modal': '0', 'deepseek': '0'}}
        calibration = contract_api.calibration(self.contract, base_generation_seconds=100, chosen_generation_seconds=100,
            evidence_hashes={'base': 'c'*64, 'chosen': 'd'*64})
        review = contract_api.review_template(self.contract)
        review.update(reviewed=True, no_tuning_after_access_acknowledged=True, complete_denominator_acknowledged=True,
            all_source_roles_reviewed=True, calibration_sha256=calibration['calibration_sha256'],
            funding_snapshot_sha256=contract_api.digest(funding))
        self.sealed = {'contract': self.contract, 'seal_sha256': 'e'*64,
            'access_registry_path': str(self.registry), 'owner_sha256': contract_api.digest(self.owner),
            'checkpoint': {'run_path': str(checkpoint)},
            'source_paths': {}, 'review': review, 'calibration': calibration, 'funding_snapshot': funding,
            'reviewed_as_of_utc': stamp, 'pricing_sha256': contract_api.digest(self.contract['protocol']['pricing'])}
        loader.ensure_json(self.folder/'access_owner.json', {'owner_token': self.owner, 'seal_sha256': self.sealed['seal_sha256']})
        self.addCleanup(patch.stopall)
        patch.object(loader.seal, 'verify', return_value=self.sealed).start()
        patch.object(loader.seal, 'ACCESS', self.registry).start()
        patch.object(loader.urllib.request, 'urlopen', side_effect=AssertionError('No real network in fixtures')).start()

    def prepare(self, fetcher=None):
        return loader.prepare(self.folder, self.output, authorized=True,
            fetcher=(lambda _: synthetic_raw()) if fetcher is None else fetcher)

    def test_no_default_fetch_content_read_or_permit_and_metadata_only_inspection(self):
        with patch.object(loader.seal, 'begin_access', side_effect=AssertionError('No permit without authorization')):
            with self.assertRaises(ValueError): loader.prepare(self.folder, self.output)
            with self.assertRaises(ValueError): loader.load_prepared(self.folder, self.output)
            with self.assertRaises(ValueError): loader.fetch('https://fixture.invalid')
        self.assertFalse(self.output.exists()); self.assertFalse(self.registry.exists())
        self.output.mkdir(); (self.output/'source.jsonl').write_bytes(b'CONTENT_READ_TRAP')
        original = loader._raw
        def metadata_only(path, *args):
            if Path(path).name in ('source.jsonl', 'sample.jsonl', 'sample_binding.json'):
                raise AssertionError('Metadata inspection must not read source/sample content')
            return original(path, *args)
        with patch.object(loader, '_raw', side_effect=metadata_only):
            result = loader.inspect_metadata(self.folder, self.output)
        self.assertEqual(result['stage'], 'not_prepared'); self.assertFalse(result['source_access_performed_by_inspection'])

    def test_parser_uses_complete1319_and_retains_unicode_and_long_inputs_without_filtering(self):
        rows = synthetic_rows(); first = self.contract['protocol']['dataset']['indices'][0]
        rows[first]['question'] += 'x'*20000
        raw = synthetic_raw(rows); selected = loader.select(raw, self.contract)
        self.assertEqual(len(selected), 1000)
        self.assertEqual(selected[0]['prompt'], rows[first]['question'])
        self.assertIn('\u2028', selected[0]['prompt']); self.assertIn('\u0085', selected[0]['prompt'])
        self.assertFalse(any(row['training_eligible'] for row in selected))
        for bad in (raw[:100], synthetic_raw(rows[:-1])):
            with self.assertRaises(ValueError): loader.select(bad, self.contract)
        unused = next(i for i in range(1319) if i not in self.contract['protocol']['dataset']['indices'])
        rows[unused]['answer'] = 'Malformed even though this row was not sampled'
        with self.assertRaises(ValueError): loader.select(synthetic_raw(rows), self.contract)

    def test_full1319_count_and_shared_input_hash_excludes_gold(self):
        full = source_metadata(1319)
        selected = loader.select(synthetic_raw(), full)
        self.assertEqual([r['source_index'] for r in selected], list(range(1319)))
        row = selected[-1]; expected = contract_api.digest({'id': row['id'], 'source_index': row['source_index'],
            'messages': [{'role': 'user', 'content': full['protocol']['inference']['user_prefix']+row['prompt']}]})
        self.assertEqual(loader.question_input_hash(row, full), expected)
        self.assertEqual(loader.question_input_hash(dict(row, gold_answer='8'), full), expected)
        binding = loader.make_binding(full, synthetic_raw(), selected)
        self.assertEqual(len(binding['questions']), 1319)
        self.assertNotIn('reference_solution', binding['questions'][0])

    def test_permit_precedes_single_fetch_exact_bytes_persist_before_parse_then_read_only_recovery(self):
        raw = synthetic_raw(); calls = []
        original = loader.select
        def fetcher(url):
            self.assertTrue(self.registry.exists()); self.assertTrue((self.output/'fetch_started.json').exists())
            calls.append(url); return raw
        def parse_after_durable(raw_value, contract):
            self.assertEqual((self.output/'source.jsonl').read_bytes(), raw)
            self.assertTrue((self.output/'download_receipt.json').exists())
            return original(raw_value, contract)
        with patch.object(loader, 'select', side_effect=parse_after_durable):
            result = self.prepare(fetcher)
        self.assertEqual(result['count'], 1000); self.assertEqual(len(calls), 1)
        before = {p.name: p.read_bytes() for p in self.output.iterdir() if p.is_file()}
        loaded = loader.load_prepared(self.folder, self.output, authorized=True)
        after = {p.name: p.read_bytes() for p in self.output.iterdir() if p.is_file()}
        self.assertEqual(before, after); self.assertEqual(len(loaded['rows']), 1000)
        second = self.prepare(lambda _: self.fail('Persisted source must not be fetched twice'))
        self.assertTrue(second['permit_reused']); self.assertTrue(second['receipt_reused'])
        self.assertEqual(len(calls), 1); self.assertFalse((self.output/'loader.lock').exists())

    def test_ambiguous_fetch_and_invalid_source_never_retry(self):
        calls = []
        def timeout(_):
            calls.append(1); raise TimeoutError('INVENTED network loss after possible transmission')
        with self.assertRaises(TimeoutError): self.prepare(timeout)
        with self.assertRaisesRegex(ValueError, 'Ambiguous prior'): self.prepare(timeout)
        self.assertEqual(len(calls), 1)
        # A separately owned source can retain invalid raw bytes without retrying.
        self.output = self.root/'another-destination'
        with self.assertRaises(ValueError): self.prepare(lambda _: self.fail('Destination cannot change after permit'))

    def test_invalid_schema_wire_is_retained_and_never_refetched(self):
        invalid = b'INVENTED invalid response'; calls = []
        def fetcher(_): calls.append(1); return invalid
        with self.assertRaises(ValueError): self.prepare(fetcher)
        self.assertEqual((self.output/'source.jsonl').read_bytes(), invalid)
        with self.assertRaises(ValueError): self.prepare(fetcher)
        self.assertEqual(calls, [1])

    def test_filesystem_only_retries_and_persisted_download_resume_without_new_get(self):
        calls = []; replace = Path.replace; locks = []
        def blocked(path, target):
            if Path(target).name == 'source.jsonl':
                locks.append(1); raise PermissionError('INVENTED local sync lock')
            return replace(path, target)
        def fetcher(_): calls.append(1); return synthetic_raw()
        with patch.object(Path, 'replace', blocked), patch.object(loader.time, 'sleep'):
            with self.assertRaises(PermissionError): self.prepare(fetcher)
        self.assertEqual(len(locks), 4); self.assertEqual(calls, [1])
        self.assertTrue((self.output/'source.download').exists())
        self.assertTrue((self.output/'download_receipt.json').exists())
        result = self.prepare(lambda _: self.fail('Local rename recovery must not repeat GET'))
        self.assertEqual(result['count'], 1000); self.assertEqual(calls, [1])

    def test_global_legacy_owner_or_new_destination_blocks_before_source_read(self):
        self.registry.parent.mkdir()
        self.registry.write_text(json.dumps({'family': 'sealed256-final-v1', 'freeze_sha256': '0'*64,
            'owner_sha256': '1'*64}), encoding='utf-8')
        with self.assertRaises(ValueError): self.prepare(lambda _: self.fail('Legacy permit must block GET'))
        self.registry.unlink(); self.prepare()
        other = self.root/'new-destination'
        with self.assertRaises(ValueError): loader.prepare(self.folder, other, authorized=True,
            fetcher=lambda _: self.fail('Owner destination is immutable'))
        with self.assertRaises(ValueError): loader.load_prepared(self.folder, other, authorized=True)

    def test_changed_source_sample_binding_and_loader_role_fail_closed(self):
        self.prepare(); source = self.output/'source.jsonl'; original = source.read_bytes()
        source.write_bytes(original+b'\n')
        with self.assertRaises(ValueError): loader.load_prepared(self.folder, self.output, authorized=True)
        source.write_bytes(original)
        sample = self.output/'sample.jsonl'; sample.write_bytes(sample.read_bytes()+b'\n')
        with self.assertRaises(ValueError): loader.load_prepared(self.folder, self.output, authorized=True)
        sample.write_bytes(sample.read_bytes()[:-1])
        binding_path = self.output/'sample_binding.json'; binding = loader.read(binding_path)
        binding['questions'][0]['input_sha256'] = '0'*64
        binding['binding_sha256'] = contract_api.digest({k: v for k, v in binding.items() if k != 'binding_sha256'})
        binding_path.write_bytes(loader.encoded(binding))
        with self.assertRaises(ValueError): loader.load_prepared(self.folder, self.output, authorized=True)
        self.sealed['contract']['protocol']['source_hashes']['final_scale_loader.py'] = '0'*64
        with self.assertRaises(ValueError): self.prepare(lambda _: self.fail('Changed loader must not fetch'))

    def test_conflicting_global_receipt_or_malformed_download_metadata_never_repaired(self):
        self.prepare()
        path = loader.seal.dataset_receipt_path(self.sealed); saved = loader.read(path)
        saved['sample_sha256'] = '0'*64; path.write_bytes(loader.encoded(saved))
        before = path.read_bytes()
        with self.assertRaises(ValueError): loader.load_prepared(self.folder, self.output, authorized=True)
        with self.assertRaises(ValueError): self.prepare(lambda _: self.fail('Conflict cannot trigger GET'))
        self.assertEqual(path.read_bytes(), before)
        download = self.output/'download_receipt.json'; download.write_bytes(b'[]\n')
        with self.assertRaises(ValueError): self.prepare(lambda _: self.fail('Malformed receipt cannot trigger GET'))

    def test_exclusive_lock_and_bounded_network_read(self):
        self.output.mkdir(); (self.output/'loader.lock').write_text('another-owner', encoding='ascii')
        with self.assertRaises(FileExistsError): self.prepare(lambda _: self.fail('Another owner must block GET'))
        self.assertEqual((self.output/'loader.lock').read_text(encoding='ascii'), 'another-owner')
        sizes = []
        class Response(io.BytesIO):
            def read(self, size=-1): sizes.append(size); return super().read(size)
        with patch.object(loader.urllib.request, 'urlopen', return_value=Response(b'INVENTED bytes')) as request:
            self.assertEqual(loader.fetch('https://fixture.invalid', authorized=True), b'INVENTED bytes')
        self.assertEqual(sizes, [loader.MAX_SOURCE_BYTES+1]); self.assertEqual(request.call_count, 1)

    def test_raw_alias_and_ancestor_links_are_rejected_before_resolution_or_content_read(self):
        alias = self.root/'linked-alias'; alias.mkdir()
        content = alias/'metadata.json'; content.write_bytes(b'{}\n')
        original = Path.is_symlink
        with patch.object(Path, 'is_symlink', lambda path: path == alias or original(path)):
            with self.assertRaisesRegex(ValueError, 'Symlinks'):
                loader.private(alias/'new-destination')
            with self.assertRaisesRegex(ValueError, 'Symlinks'):
                loader._raw(content)

    def test_forbidden_prepare_destinations_create_no_directories_locks_or_error_state(self):
        protected = (Path(self.sealed['checkpoint']['run_path'])/'adapter/new-input',
            self.folder/'new-input', self.registry.parent/'new-input')
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        for output in protected:
            with self.subTest(output=output):
                with self.assertRaisesRegex(ValueError, 'overlap'):
                    loader.prepare(self.folder, output, authorized=True,
                        fetcher=lambda _: self.fail('Rejected destination must never fetch'))
                self.assertFalse(output.exists())
                self.assertFalse(self.registry.exists())
        after = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_linked_status_pending_or_target_is_never_opened_or_mutated(self):
        self.output.mkdir()
        original = Path.is_symlink
        for name in ('loader_state.json.pending', 'loader_state.json'):
            path = self.output/name
            path.write_bytes(b'INVENTED linked target contents must survive')
            before = path.read_bytes()
            with self.subTest(name=name), patch.object(Path, 'is_symlink',
                    lambda item: item == path or original(item)):
                # Reject during the read-only child scan, before even a permit.
                with self.assertRaisesRegex(ValueError, 'Symlinks'):
                    self.prepare(lambda _: self.fail('Linked status must block fetch'))
                self.assertFalse(self.registry.exists())
                # The writer itself remains safe if called after initial scan.
                with self.assertRaisesRegex(ValueError, 'Symlinks'):
                    loader._state(self.output, 'action_required')
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse((self.output/'loader.lock').exists())
            path.unlink()


if __name__ == '__main__':
    unittest.main()
