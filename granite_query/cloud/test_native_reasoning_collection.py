"""Invented TRAIN/API fixtures only; no provider, actual funding or test reads."""
from contextlib import ExitStack
from decimal import Decimal
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cloud import native_reasoning_collection as collect
from cloud import native_reasoning_contract as contract
from cloud.test_teacher_depth_pilot import SeamTokenizer
from cloud.test_final_scale_funding import ledger as synthetic_ledger

NOW = '2026-11-03T23:00:00+00:00'


def wire(body, *, answer='7', unknown=False, finish='stop'):
    mode = body['thinking']['type']
    return collect.encoded({'model': 'deepseek-v4-pro-0813', 'choices': [{
        'message': {'content': 'Original visible answer.\n#### '+answer,
            'reasoning_content': 'R original reasoning\u2028retained.' if mode == 'enabled' else ''},
        'finish_reason': finish}], 'usage': {} if unknown else {'prompt_tokens': 50, 'completion_tokens': 30}})


class NativeCollectionTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        actual_root = Path(collect.__file__).resolve().parent
        parent = actual_root/'runs/test_native_reasoning_collection'; parent.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'fixture_cloud'; (self.root/'runs').mkdir(parents=True)
        self.output = self.root/'runs/paired-fixture'; self.tokenizer = SeamTokenizer()
        self.original_count = collect.QUESTIONS
        self.stack.enter_context(patch.object(collect, 'ROOT', self.root))
        self.stack.enter_context(patch.object(collect, 'QUESTIONS', 2))
        self.stack.enter_context(patch.object(collect, 'other_collector_locks', return_value=[]))
        self.dependency = self.root/'fixture_dependency.py'; self.dependency.write_text('immutable fixture source\n')
        self.real_dependencies = collect.dependencies
        self.stack.enter_context(patch.object(collect, 'dependencies', return_value=[self.dependency]))
        self.stack.enter_context(patch.object(contract, 'tokenizer_identity', return_value=dict(contract.TOKENIZER)))
        self.training = self.root/'fixture-train.jsonl'; self.training.write_bytes(b'INVENTED TRAIN CACHE\n')
        probes = self.root.parent/'fixture-probes.jsonl'; probes.write_bytes(b'')
        self.stack.enter_context(patch.object(collect.source, 'SOURCE', self.training))
        self.stack.enter_context(patch.object(collect.source, 'SOURCE_SHA', collect.sha(self.training.read_bytes())))
        self.stack.enter_context(patch.object(collect.source, 'PROBES', probes))
        # All7473 records are invented; source IO is never delegated to the
        # real canonical loader. Two pairs keep crash fixtures inexpensive.
        self.canonical = [{'id': f'gsm8k:train:{i:05d}', 'source_split': 'train',
            'prompt': f'Invented case{chr(97+i//676%26)}{chr(97+i//26%26)}{chr(97+i%26)} has 3 apples and obtains 4. How many apples?',
            'gold_answer': '7', 'reference_solution': '3 + 4 = <<3+4=7>>7.\n#### 7'} for i in range(7473)]
        self.stack.enter_context(patch.object(collect.source, 'load_source', return_value=(self.canonical, {})))
        self.stack.enter_context(patch.object(collect.source, 'ancestry_exclusions', return_value=(set(), {'fixture': True})))
        artifacts = []
        for path in (probes, self.root/'runs/human_math_cohort2048_dev200_v1/candidates.jsonl',
                self.root/'runs/human_math_cohort2048_dev200_v1/development.jsonl',
                self.root/'runs/teacher_depth32_v1/candidates.jsonl'):
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'')
            artifacts.append({'run': path.relative_to(self.root.parent).as_posix(),
                'sha256': collect.sha(path.read_bytes()), 'question_records': 0})
        self.real_load_exclusions = collect.load_exclusions
        self.stack.enter_context(patch.object(collect, 'load_exclusions', return_value=([], artifacts)))
        self.plan = collect.prepare(self.output, tokenizer=self.tokenizer)
        self.plan, self.rows, self.requests = collect.validate_run(self.output, tokenizer=self.tokenizer)
        self.reservation_id = 'paired-fixture-teacher'; self.review = dict(collect.review_template(self.plan, self.reservation_id), reviewed=True)
        self.review_path = self.output/'approved-review.json'; collect.write(self.review_path, self.review)
        self.ledger_path = self.root/'runs/state/budget.json'
        ledger = synthetic_ledger(); ledger['reserved']['deepseek'] = 7
        ledger['jobs'].append({'run_id': self.reservation_id, 'service': 'deepseek', 'status': 'reserved', 'reserved_usd': 7,
            'native_reasoning_plan_sha256': self.plan['plan_sha256'], 'native_reasoning_requests_sha256': self.plan['requests_sha256'],
            'native_reasoning_review_sha256': collect.digest(self.review)})
        collect.write(self.ledger_path, ledger)
        self.transport = Mock(side_effect=lambda body, key: (200, wire(body)))

    def tearDown(self):
        self.stack.close(); self.temp.cleanup()

    def run_collection(self, **kwargs):
        values = {'reservation_id': self.reservation_id, 'review_path': self.review_path,
            'authorized': True, 'workers': 1, 'tokenizer': self.tokenizer, 'transport': self.transport,
            'ledger_path': self.ledger_path, 'key': 'fixture-key-not-real', 'clock': lambda: NOW}
        values.update(kwargs)
        return collect.collect(self.output, **values)

    def session(self):
        collect.write(self.output/'reviewed_for_collection.json', self.review)
        collect.write(self.output/'collection_session.json', {'plan_sha256': self.plan['plan_sha256'],
            'review_sha256': collect.digest(self.review), 'reservation_id': self.reservation_id, 'started_at_utc': NOW})

    def test_real_defaults_freeze512_originals_and_exact_peak_bound(self):
        self.assertEqual(self.original_count, 256)
        self.assertEqual(collect.CAPS, {'concise': 1024, 'thinking': 4096})
        self.assertEqual(collect.COST_BOUND, Decimal('6.5421312'))
        self.assertEqual(collect.RESERVATION, Decimal('7'))
        self.assertEqual(collect.LAUNCH_WINDOW_SECONDS, 1800)
        for request in self.requests:
            text = collect.encoded(request['payload']).decode()
            self.assertNotIn('reference_solution', text); self.assertNotIn('gold_answer', text)
            self.assertNotIn('<<3+4=7>>', text)
            self.assertEqual(request['payload']['messages'][0]['content'], contract.PREFIX+
                next(row['prompt'] for row in self.rows if row['id'] == request['question_id']))

    def test_prepare_is_immutable_and_changed_source_blocks_inspection_before_receipts(self):
        before = (self.output/'plan.json').read_bytes()
        self.assertEqual(collect.prepare(self.output, tokenizer=self.tokenizer), self.plan)
        self.assertEqual((self.output/'plan.json').read_bytes(), before)
        self.dependency.write_text('changed source\n')
        with patch.object(collect, '_history', side_effect=AssertionError('Do not inspect receipts after source mutation')):
            with self.assertRaisesRegex(ValueError, 'source, tokenizer'):
                collect.inspect_run(self.output, tokenizer=self.tokenizer)
        self.assertEqual(self.transport.call_count, 0)

    def test_candidate_and_request_tamper_fail_before_transport(self):
        target = self.output/'requests.jsonl'; target.write_bytes(target.read_bytes()+b' ')
        with self.assertRaises(ValueError): self.run_collection()
        self.assertEqual(self.transport.call_count, 0)
        self.assertFalse((self.output/'collector.lock').exists())

    def test_review_or_existing_reservation_mismatch_never_transmits(self):
        ledger = collect.read(self.ledger_path); original = json.loads(json.dumps(ledger))
        for field, value in (('reserved_usd', 6.99), ('native_reasoning_plan_sha256', '0'*64),
                ('native_reasoning_review_sha256', '0'*64), ('status', 'completed')):
            changed = json.loads(json.dumps(original)); changed['jobs'][0][field] = value
            collect.write(self.ledger_path, changed, immutable=False)
            with self.subTest(field=field), self.assertRaises(ValueError): self.run_collection()
        self.assertEqual(self.transport.call_count, 0)

    def test_explicit_collection_flag_and_worker_cap_precede_any_transmission(self):
        for args in ({'authorized': False}, {'workers': 5}, {'workers': True}):
            with self.subTest(args=args), self.assertRaises(ValueError): self.run_collection(**args)
        self.assertEqual(self.transport.call_count, 0)

    def test_success_retains_every_original_and_common_full_target_pairs(self):
        before = self.ledger_path.read_bytes(); result = self.run_collection()
        self.assertEqual(result['stage'], 'completed'); self.assertEqual(result['retained_original_outcomes'], 4)
        self.assertEqual(self.transport.call_count, 4)
        self.assertEqual(self.ledger_path.read_bytes(), before)
        pairs = collect.finalized_pairs(self.output, tokenizer=self.tokenizer)
        self.assertEqual(len(pairs), 2)
        for pair in pairs:
            self.assertEqual(set(pair), {'id','concise','thinking'})
            for mode in collect.MODES:
                self.assertTrue(pair[mode]['verified_final_answer']); self.assertFalse(pair[mode]['truncated'])
                contract.validate_encoding(pair[mode], self.tokenizer)
            self.assertIn('\u2028', pair['thinking']['reasoning_content'])
        self.assertEqual(collect.read_rows(self.output/'eligible_pairs.jsonl'), pairs)
        inventory = collect.receipt_inventory(self.output, tokenizer=self.tokenizer)
        self.assertEqual(inventory['original_intents'], 4); self.assertEqual(len(inventory['files']), 16)
        self.assertEqual(inventory['sha256'], collect.digest(inventory['files']))
        self.run_collection(); self.assertEqual(self.transport.call_count, 4)

    def test_wrong_answers_are_retained_not_filtered_from_original_outcomes(self):
        self.transport.side_effect = lambda body, key: (200, wire(body, answer='8'))
        result = self.run_collection()
        self.assertEqual(result['stage'], 'completed'); self.assertEqual(result['retained_original_outcomes'], 4)
        self.assertEqual(result['eligible_question_pairs'], 0)
        self.assertEqual(len(collect.read_rows(self.output/'teacher_results.jsonl')), 4)
        self.assertEqual(collect.finalized_pairs(self.output, tokenizer=self.tokenizer), [])

    def test_intent_fsync_precedes_transport_and_wire_fsync_precedes_parse(self):
        self.session(); request = self.requests[0]; row = next(r for r in self.rows if r['id'] == request['question_id'])
        intent, raw_path, metadata, _, _ = collect.attempt_paths(self.output, request['id'])
        def transport(body, key):
            self.assertTrue(intent.exists()); self.assertEqual(collect.read(intent)['plan_sha256'], self.plan['plan_sha256'])
            return 200, wire(body)
        original = collect.result_from_wire
        def derive(*args):
            self.assertTrue(raw_path.exists()); self.assertTrue(metadata.exists())
            self.assertEqual(raw_path.read_bytes(), args[3]); return original(*args)
        with patch.object(collect, 'result_from_wire', side_effect=derive):
            collect.call_request(self.plan, request, row, self.output, 'fixture-key', reservation_id=self.reservation_id,
                review_sha256=collect.digest(self.review), transport=transport)
        with self.assertRaises(collect.AmbiguousAttemptError):
            collect.call_request(self.plan, request, row, self.output, 'fixture-key', reservation_id=self.reservation_id,
                review_sha256=collect.digest(self.review), transport=Mock(side_effect=AssertionError('No resend')))

    def test_intent_only_ambiguity_blocks_resume_and_never_resends(self):
        self.session(); request = self.requests[0]
        marker = {'id': request['id'], 'plan_sha256': self.plan['plan_sha256'], 'request_sha256': request['request_sha256'],
            'reservation_id': self.reservation_id, 'review_sha256': collect.digest(self.review), 'started_at_utc': NOW}
        collect.write(collect.attempt_paths(self.output, request['id'])[0], marker)
        with self.assertRaises(collect.AmbiguousAttemptError): self.run_collection()
        self.assertEqual(self.transport.call_count, 0)

    def test_http_auth_rate_or_unknown_usage_stops_new_calls_and_does_not_retry(self):
        self.transport.side_effect = lambda body, key: (429, b'{"error":{"message":"PRIVATE account detail"}}')
        result = self.run_collection()
        self.assertEqual(result['stage'], 'halted'); self.assertEqual(result['retained_original_outcomes'], 1)
        self.assertEqual(result['unknown_usage_attempts'], 1); self.assertEqual(self.transport.call_count, 1)
        self.assertNotIn('PRIVATE account', json.dumps(result))
        with self.assertRaises(ValueError): self.run_collection()
        self.assertEqual(self.transport.call_count, 1)

    def test_fail_stop_drains_both_already_transmitted_workers(self):
        barrier = threading.Barrier(2)
        def transport(body, key):
            barrier.wait(timeout=15)
            return 401, b'{"error":{"message":"invented auth failure"}}'
        self.transport.side_effect = transport
        result = self.run_collection(workers=4)
        self.assertEqual(len(self.transport.call_args_list), 2, result)
        self.assertEqual(result['retained_original_outcomes'], 2)
        self.assertEqual(result['unknown_usage_attempts'], 2)
        self.assertEqual(result['stage'], 'halted')
        self.assertFalse((self.output/'collector.lock').exists())

    def test_funding_guard_stops_mid_pair_without_a_second_transmission(self):
        guard = collect.require_budget; calls = []
        def guarded(*args, **kwargs):
            calls.append(True)
            if len(calls) == 3: raise ValueError('Invented stale funding before next call')
            return guard(*args, **kwargs)
        with patch.object(collect, 'require_budget', side_effect=guarded):
            result = self.run_collection()
        self.assertEqual(self.transport.call_count, 1)
        self.assertEqual(result['retained_original_outcomes'], 1)
        self.assertEqual(result['halt_reason'], 'funding_guard_failed_no_new_calls')

    def test_oversized_original_wire_is_preserved_and_halts_without_parsing(self):
        raw = b'x'*(collect.MAX_RESPONSE_BYTES+1)
        self.transport.side_effect = lambda body, key: (200, raw)
        result = self.run_collection()
        self.assertEqual(self.transport.call_count, 1)
        self.assertEqual(result['unknown_usage_attempts'], 1)
        originals = list((self.output/'attempts').glob('*.wire'))
        self.assertEqual(len(originals), 1); self.assertEqual(originals[0].read_bytes(), raw)

    def test_transport_timeout_retains_unknown_liability_and_never_resends(self):
        self.transport.side_effect = TimeoutError('PRIVATE secret-like text must never be persisted')
        result = self.run_collection()
        self.assertEqual(result['stage'], 'halted'); self.assertEqual(result['unknown_usage_attempts'], 1)
        self.assertEqual(self.transport.call_count, 1)
        serialized = b''.join(path.read_bytes() for path in (self.output/'attempts').iterdir())
        self.assertNotIn(b'PRIVATE secret-like', serialized)
        with self.assertRaises(ValueError): self.run_collection()
        self.assertEqual(self.transport.call_count, 1)

    def test_error_receipt_cannot_be_forged_into_eligible_success_before_projection(self):
        self.session(); request = self.requests[0]; row = next(r for r in self.rows if r['id'] == request['question_id'])
        with self.assertRaises(TimeoutError):
            collect.call_request(self.plan, request, row, self.output, 'fixture-key',
                reservation_id=self.reservation_id, review_sha256=collect.digest(self.review),
                transport=Mock(side_effect=TimeoutError('invented')))
        _, _, _, derived, error_path = collect.attempt_paths(self.output, request['id'])
        self.assertFalse(derived.exists()); original = collect.read(error_path)
        mutations = [dict(original, failed=False), dict(original, finish_reason='stop'),
            dict(original, raw={'usage': {'prompt_tokens': 40, 'completion_tokens': 30}}),
            dict(original, response='#### 7'), dict(original, unknown_provider_usage=False),
            dict(original, question_id=self.rows[1]['id'] if row['id'] == self.rows[0]['id'] else self.rows[0]['id']),
            dict(original, failed=False, finish_reason='stop', response='#### 7',
                raw={'usage': {'prompt_tokens': 40, 'completion_tokens': 30}}, teacher_revision='deepseek-v4-pro')]
        for forged in mutations:
            collect.write(error_path, forged, immutable=False)
            with self.subTest(fields=[k for k in forged if forged[k] != original.get(k)]), self.assertRaises(ValueError):
                collect.recover_attempt(self.plan, request, row, self.output)
            self.assertFalse(derived.exists())
        collect.write(error_path, original, immutable=False)
        recovered = collect.recover_attempt(self.plan, request, row, self.output)
        verified = collect.verify_result(recovered, row, self.tokenizer)
        self.assertTrue(verified['failed']); self.assertFalse(verified['provider_usage_known']); self.assertFalse(verified['eligible'])
        with self.assertRaises(ValueError): self.run_collection()
        self.assertEqual(self.transport.call_count, 0)

    def test_explicit_unknown_usage_cannot_be_overridden_by_attached_token_numbers(self):
        request = self.requests[0]; row = next(r for r in self.rows if r['id'] == request['question_id'])
        original = wire(request['payload']); marker = {'started_at_utc': NOW}
        metadata = {'completed_at_utc': NOW, 'elapsed_seconds': .1, 'http_status': 200}
        result = collect.result_from_wire(self.plan, request, row, original, marker, metadata)
        self.assertTrue(collect.verify_result(result, row, self.tokenizer)['provider_usage_known'])
        unknown = collect.verify_result(dict(result, unknown_provider_usage=True), row, self.tokenizer)
        self.assertFalse(unknown['provider_usage_known']); self.assertFalse(unknown['eligible'])
        self.assertIn('unknown_provider_usage', unknown['rejection_reasons'])

    def test_malformed200_choice_and_message_shapes_become_durable_failed_values(self):
        request = self.requests[0]; row = next(r for r in self.rows if r['id'] == request['question_id'])
        metadata = {'completed_at_utc': NOW, 'elapsed_seconds': .1, 'http_status': 200}
        malformed = [None, [], 7]
        responses = [dict(model='deepseek-v4-pro', choices=[{'message': shape, 'finish_reason': 'stop'}],
            usage={'prompt_tokens': 30, 'completion_tokens': 20}) for shape in malformed]
        responses += [dict(model='deepseek-v4-pro', choices=[shape]) for shape in malformed]
        responses += [None, [], 7]
        for response in responses:
            original = collect.encoded(response)
            with self.subTest(response=response):
                value = collect.result_from_wire(self.plan, request, row, original,
                    {'started_at_utc': NOW}, metadata)
                self.assertTrue(value['failed']); self.assertIsNone(value['raw'])
                self.assertEqual(value['wire_sha256'], collect.sha(original))
                self.assertFalse(collect.verify_result(value, row, self.tokenizer)['eligible'])

    def test_entire_wire_tree_must_be_utf8_finite_duplicate_free_and_bounded_recursion(self):
        request = self.requests[0]; row = next(r for r in self.rows if r['id'] == request['question_id'])
        metadata = {'completed_at_utc': NOW, 'elapsed_seconds': .1, 'http_status': 200}
        base = json.loads(wire(request['payload']))
        bodies = []
        for key in ('content', 'reasoning_content'):
            bad = json.loads(json.dumps(base)); bad['choices'][0]['message'][key] = '\ud800'
            bodies.append(json.dumps(bad, ensure_ascii=True).encode())
        for key in ('model', 'system_fingerprint', 'unrelated_extra_field'):
            bad = json.loads(json.dumps(base)); bad[key] = '\udfff'
            bodies.append(json.dumps(bad, ensure_ascii=True).encode())
        bad = json.loads(json.dumps(base)); bad['\ud800'] = 'invalid key'
        bodies.append(json.dumps(bad, ensure_ascii=True).encode())
        bodies.extend([b'{"extra":NaN}', b'{"extra":Infinity}', b'{"extra":-Infinity}',
            b'{"extra":1e400}', b'{"model":"one","model":"two"}', b'['*2000+b'0'+b']'*2000])
        for index, original in enumerate(bodies):
            with self.subTest(body=index):
                value = collect.result_from_wire(self.plan, request, row, original,
                    {'started_at_utc': NOW}, metadata)
                self.assertTrue(value['failed']); self.assertIsNone(value['raw']); self.assertTrue(value['unknown_provider_usage'])
                self.assertEqual(value['wire_sha256'], collect.sha(original)); collect.encoded(value)
                verified = collect.verify_result(value, row, self.tokenizer)
                self.assertFalse(verified['eligible']); self.assertFalse(verified['provider_usage_known'])

    def test_escaped_surrogate_wire_is_retained_without_poisoning_halted_history(self):
        body = json.loads(wire(self.requests[0]['payload'])); body['system_fingerprint'] = '\ud800'
        original = json.dumps(body, ensure_ascii=True).encode()
        self.transport.side_effect = lambda payload, key: (200, original)
        result = self.run_collection()
        self.assertEqual(result['stage'], 'halted'); self.assertEqual(result['retained_original_outcomes'], 1)
        self.assertEqual(result['unknown_usage_attempts'], 1)
        history = collect.read_rows(self.output/'teacher_results.jsonl')
        self.assertEqual(len(history), 1); self.assertIsNone(history[0]['raw'])
        self.assertEqual(collect.read(self.output/'teacher_summary.json'), result)
        raw = next((self.output/'attempts').glob('*.wire')); self.assertEqual(raw.read_bytes(), original)
        self.assertEqual(collect.inspect_run(self.output, tokenizer=self.tokenizer)['retained_original_outcomes'], 1)
        with self.assertRaises(ValueError): self.run_collection()
        self.assertEqual(self.transport.call_count, 1)

    def test_malformed200_drains_original_workers_saves_halted_outcomes_and_never_resends(self):
        barrier = threading.Barrier(2)
        malformed = collect.encoded({'model': 'deepseek-v4-pro',
            'choices': [{'message': None, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 30, 'completion_tokens': 20}})
        def transport(body, key):
            barrier.wait(timeout=15)
            return 200, malformed
        self.transport.side_effect = transport
        result = self.run_collection(workers=4)
        self.assertEqual(len(self.transport.call_args_list), 2, result)
        self.assertEqual(result['stage'], 'halted'); self.assertEqual(result['retained_original_outcomes'], 2)
        self.assertEqual(len(collect.read_rows(self.output/'teacher_results.jsonl')), 2)
        self.assertEqual(collect.read(self.output/'teacher_summary.json'), result)
        for raw in (self.output/'attempts').glob('*.wire'): self.assertEqual(raw.read_bytes(), malformed)
        with self.assertRaises(ValueError): self.run_collection()
        self.assertEqual(len(self.transport.call_args_list), 2)

    def test_dynamic_matched_teacher_prefix_dependency_is_frozen_and_rechecked(self):
        matched = self.root/'matched_teacher.py'; matched.write_text('PREFIX = "fixture prefix"\n')
        self.assertIn(matched, self.real_dependencies())
        output = self.root/'runs/matched-dependency-fixture'
        with patch.object(collect, 'dependencies', return_value=[self.dependency, matched]):
            plan = collect.prepare(output, tokenizer=self.tokenizer)
            self.assertEqual(plan['protocol']['source_code_hashes'][matched.relative_to(self.root.parent).as_posix()], collect.sha(matched.read_bytes()))
            matched.write_text('PREFIX = "changed prefix"\n')
            with patch.object(collect, '_history', side_effect=AssertionError('Source mismatch must precede receipt recovery')):
                with self.assertRaisesRegex(ValueError, 'source, tokenizer'):
                    collect.inspect_run(output, tokenizer=self.tokenizer)

    def test_changed_wire_or_derived_result_rejected_without_http(self):
        self.run_collection(); request = self.requests[0]
        _, raw, _, result, _ = collect.attempt_paths(self.output, request['id'])
        original = raw.read_bytes(); raw.write_bytes(original+b' ')
        with self.assertRaisesRegex(ValueError, 'wire metadata/hash'): collect.inspect_run(self.output, tokenizer=self.tokenizer)
        raw.write_bytes(original); value = collect.read(result); value['response'] = '#### 123'
        collect.write(result, value, immutable=False)
        with self.assertRaisesRegex(ValueError, 'Derived result'): collect.finalized_pairs(self.output, tokenizer=self.tokenizer)
        self.assertEqual(self.transport.call_count, 4)

    def test_missing_derived_receipt_recovers_from_exact_wire_without_resend(self):
        self.run_collection(); request = self.requests[0]
        result = collect.attempt_paths(self.output, request['id'])[3]; expected = result.read_bytes(); result.unlink()
        summary = collect.inspect_run(self.output, tokenizer=self.tokenizer)
        self.assertEqual(summary['stage'], 'completed'); self.assertEqual(result.read_bytes(), expected)
        self.assertEqual(self.transport.call_count, 4)

    def test_receipt_inventory_rejects_cross_plan_and_orphan_files(self):
        self.run_collection(); request = self.requests[0]; marker_path = collect.attempt_paths(self.output, request['id'])[0]
        marker = collect.read(marker_path); collect.write(marker_path, dict(marker, plan_sha256='0'*64), immutable=False)
        with self.assertRaises(ValueError): collect.finalized_pairs(self.output, tokenizer=self.tokenizer)
        collect.write(marker_path, marker, immutable=False); collect.write(self.output/'attempts/unknown.json', {})
        with self.assertRaises(ValueError): collect.receipt_inventory(self.output, tokenizer=self.tokenizer)
        self.assertEqual(self.transport.call_count, 4)

    def test_expired_original_launch_window_cannot_reset_on_resume(self):
        self.session(); session = collect.read(self.output/'collection_session.json')
        collect.write(self.output/'collection_session.json', dict(session, started_at_utc='2026-11-03T22:00:00+00:00'), immutable=False)
        result = self.run_collection()
        self.assertEqual(result['stage'], 'halted'); self.assertEqual(result['retained_original_outcomes'], 0)
        self.assertEqual(self.transport.call_count, 0)

    def test_final_owner_metadata_blocks_question_bytes_before_exclusion_read(self):
        owner = self.root/'runs/sealed-owner'; owner.mkdir()
        metadata = owner/'plan.json'; metadata.write_bytes(collect.encoded({'protocol': {'role': 'final_eval_only'}}))
        question_path = owner/'questions.jsonl'; question_path.write_bytes(b'OFFICIAL_BYTES_MUST_STAY_UNREAD')
        original = Path.read_bytes
        def guarded(path):
            if path == question_path: raise AssertionError('Official source content was opened')
            return original(path)
        with patch.object(collect.source, 'exclusion_artifacts', return_value=[question_path]), \
             patch.object(Path, 'read_bytes', guarded):
            records, artifacts = self.real_load_exclusions(self.output)
        self.assertEqual((records, artifacts), ([], []))
        self.assertEqual(self.transport.call_count, 0)


if __name__ == '__main__': unittest.main()
