"""Invented continuation receipts only; no real ledger, host, network or model."""
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cloud import native_reasoning_continuation as driver
from cloud import native_reasoning_collection as col
from cloud import test_native_reasoning_collection as fixture_tests
NOW, wire = fixture_tests.NOW, fixture_tests.wire


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_tests.NativeCollectionTests('test_real_defaults_freeze512_originals_and_exact_peak_bound')
        self.fixture.setUp(); self.addCleanup(self.fixture.tearDown)
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        # Eight invented originals exercise four concurrent question workers.
        self.stack.enter_context(patch.object(col, 'QUESTIONS', 4))
        self.stack.enter_context(patch.multiple(driver, ORIGINALS=8, PRIOR=1, PENDING=7, EXITED_PIDS=(111,222)))
        self.output = self.fixture.root/'runs/continuation-fixture'
        self.tokenizer = self.fixture.tokenizer
        self.plan = col.prepare(self.output, tokenizer=self.tokenizer)
        self.plan, self.rows, self.requests = col.validate_run(self.output, tokenizer=self.tokenizer)
        self.reservation_id = 'invented-original-teacher'
        self.original_review = dict(col.review_template(self.plan, self.reservation_id), reviewed=True)
        col.write(self.output/'reviewed_for_collection.json', self.original_review)
        col.write(self.output/'collection_session.json', {'plan_sha256': self.plan['plan_sha256'],
            'review_sha256': col.digest(self.original_review), 'reservation_id': self.reservation_id, 'started_at_utc': NOW})
        self.unknown = self.requests[0]
        self.stack.enter_context(patch.object(driver, 'UNKNOWN_ID', self.unknown['id']))
        row = next(r for r in self.rows if r['id'] == self.unknown['question_id'])
        with self.assertRaises(TimeoutError):
            col.call_request(self.plan, self.unknown, row, self.output, 'invented-key',
                reservation_id=self.reservation_id, review_sha256=col.digest(self.original_review),
                transport=Mock(side_effect=TimeoutError('invented original unknown')))
        col._history(self.output, self.plan, self.rows, self.requests, self.tokenizer, append=True)
        self.ledger_path = self.fixture.ledger_path
        ledger = col.read(self.ledger_path)
        ledger['jobs'] = [{'run_id': self.reservation_id, 'service': 'deepseek', 'status': 'collecting', 'reserved_usd': 7,
            'native_reasoning_plan_sha256': self.plan['plan_sha256'],
            'native_reasoning_requests_sha256': self.plan['requests_sha256'],
            'native_reasoning_review_sha256': col.digest(self.original_review)}]
        col.write(self.ledger_path, ledger, immutable=False)
        self.attestation = {'verified_exited': True, 'pids': [111,222], 'verified_at_utc': NOW,
            'method': 'external_host_identity_and_exit_verification'}
        self.approval = dict(driver.review_template(self.output, host_exit_attestation=self.attestation,
            tokenizer=self.tokenizer), reviewed=True)
        self.approval_path = self.output/'continuation-approval.json'; col.write(self.approval_path, self.approval)
        self.transport = Mock(side_effect=lambda body, key: (200, wire(body)))

    def collect(self, **kwargs):
        values = {'approval_path': self.approval_path, 'authorized': True, 'workers': 1,
            'tokenizer': self.tokenizer, 'transport': self.transport, 'ledger_path': self.ledger_path,
            'key': 'invented-key-not-real', 'clock': lambda: NOW}
        values.update(kwargs)
        return driver.collect(self.output, **values)

    def test_prior_unknown_is_retained_never_resent_and_old_sources_reviews_budget_unchanged(self):
        old_files = {str(path.relative_to(self.output)): path.read_bytes()
            for path in col.attempt_paths(self.output, self.unknown['id']) if path.exists()}
        old_history = (self.output/'teacher_results.jsonl').read_bytes()
        old_review = (self.output/'reviewed_for_collection.json').read_bytes()
        old_session = (self.output/'collection_session.json').read_bytes(); ledger = self.ledger_path.read_bytes()
        result = self.collect()
        self.assertEqual(result['stage'], 'completed'); self.assertEqual(result['retained_original_outcomes'], 8)
        self.assertEqual(result['unknown_usage_attempts'], 1); self.assertEqual(result['eligible_question_pairs'], 3)
        self.assertEqual(self.transport.call_count, 7)
        self.assertTrue((self.output/'teacher_results.jsonl').read_bytes().startswith(old_history))
        for relative, raw in old_files.items(): self.assertEqual((self.output/relative).read_bytes(), raw)
        self.assertEqual((self.output/'reviewed_for_collection.json').read_bytes(), old_review)
        self.assertEqual((self.output/'collection_session.json').read_bytes(), old_session)
        self.assertEqual(self.ledger_path.read_bytes(), ledger)
        self.assertEqual(len(col.finalized_pairs(self.output, tokenizer=self.tokenizer)), 3)
        for request in self.requests:
            marker = col.read(col.attempt_paths(self.output, request['id'])[0])
            self.assertEqual(marker['review_sha256'], col.digest(self.original_review))
        with self.assertRaises(ValueError): self.collect()
        self.assertEqual(self.transport.call_count, 7)

    def test_pending_list_hash_driver_and_old_source_review_tampering_block_before_http(self):
        for key, value in (('never_attempted_requests_sha256','0'*64), ('driver_source_sha256','0'*64),
                ('original_review_sha256','0'*64), ('original_source_code_hashes',{}), ('reviewed',False),
                ('original_absolute_launch_deadline_utc','2099-01-01T00:00:00+00:00')):
            bad = deepcopy(self.approval); bad[key] = value; col.write(self.approval_path, bad, immutable=False)
            with self.subTest(key=key), self.assertRaises(ValueError): self.collect()
        self.assertEqual(self.transport.call_count, 0)
        self.assertFalse((self.output/driver.FOLDER/'continuation_intent.json').exists())

    def test_ambiguous_existing_intent_is_excluded_and_cannot_be_claimed_as_unsent(self):
        request = next(r for r in self.requests if r['id'] != self.unknown['id'])
        marker = {'id': request['id'], 'plan_sha256': self.plan['plan_sha256'], 'request_sha256': request['request_sha256'],
            'reservation_id': self.reservation_id, 'review_sha256': col.digest(self.original_review), 'started_at_utc': NOW}
        col.write(col.attempt_paths(self.output, request['id'])[0], marker)
        self.assertNotIn(request, driver._pending_records(self.requests, self.output))
        with self.assertRaises(col.AmbiguousAttemptError): self.collect()
        self.assertEqual(self.transport.call_count, 0)

    def test_changed_original_timeout_error_cannot_authorize_continuation(self):
        path = col.attempt_paths(self.output, self.unknown['id'])[4]
        original = col.read(path); col.write(path, dict(original, error_type='RuntimeError'), immutable=False)
        with self.assertRaises(ValueError): self.collect()
        self.assertEqual(self.transport.call_count, 0)

    def test_original_window_is_not_reset_and_expiry_sends_nothing(self):
        expired = (datetime.fromisoformat(NOW)+timedelta(seconds=1801)).isoformat()
        ledger = col.read(self.ledger_path); ledger['deepseek_wallet_observation']['queried_at_utc'] = expired
        col.write(self.ledger_path, ledger, immutable=False)
        before = (self.output/'collection_session.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'absolute launch window'):
            self.collect(clock=lambda: expired)
        self.assertEqual((self.output/'collection_session.json').read_bytes(), before)
        self.assertEqual(self.transport.call_count, 0)

    def test_explicit_flags_and_external_host_exit_attestation_are_required(self):
        for values in ({'authorized': False}, {'workers': 5}, {'workers': True}):
            with self.subTest(values=values), self.assertRaises(ValueError): self.collect(**values)
        for update in ({'verified_exited':False}, {'pids':[111]}, {'method':'assumed_not_running'}):
            bad = deepcopy(self.approval); bad['host_exit_attestation'].update(update)
            col.write(self.approval_path, bad, immutable=False)
            with self.subTest(update=update), self.assertRaises(ValueError): self.collect()
        self.assertEqual(self.transport.call_count, 0)

    def test_four_workers_drain_new_failures_and_keep_all_original_cost_liability(self):
        barrier = threading.Barrier(4)
        def transport(body, key):
            barrier.wait(timeout=15)
            return 429, b'{"error":{"message":"invented rate limit"}}'
        self.transport.side_effect = transport
        before = self.ledger_path.read_bytes(); result = self.collect(workers=4)
        self.assertEqual(len(self.transport.call_args_list), 4, result)
        self.assertEqual(result['stage'], 'halted'); self.assertEqual(result['retained_original_outcomes'], 5)
        self.assertEqual(result['unknown_usage_attempts'], 5)
        self.assertEqual(self.ledger_path.read_bytes(), before)
        self.assertTrue(result['full_original_reservation_must_remain_held'])
        self.assertFalse((self.output/'collector.lock').exists())
        with self.assertRaises(ValueError): self.collect()
        self.assertEqual(len(self.transport.call_args_list), 4)

    def test_fresh_original_seven_dollar_guard_precedes_each_new_request(self):
        original = col.require_budget; calls = []
        def guard(*args, **kwargs):
            calls.append(True)
            if len(calls) == 3: raise ValueError('Invented funding freshness failure')
            return original(*args, **kwargs)
        with patch.object(col, 'require_budget', side_effect=guard): result = self.collect()
        self.assertEqual(self.transport.call_count, 1)
        self.assertEqual(result['retained_original_outcomes'], 2)
        self.assertEqual(result['halt_reason'], 'fresh_original_reservation_guard_failed')


if __name__ == '__main__': unittest.main()
