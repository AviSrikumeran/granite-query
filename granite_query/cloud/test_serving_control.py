"""Focused quota/selection checks; no network, GPU, data, or actual deployment."""
from concurrent.futures import ThreadPoolExecutor
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import threading
import unittest
import uuid

import serving_control as sc


class AtomicStore:
    """Same get/conditional-put semantics as the documented Modal Dict primitive."""
    def __init__(self):
        self.values, self.lock = {}, threading.Lock()

    def get(self, key, default=None):
        with self.lock:
            return copy.deepcopy(self.values.get(key, default))

    def put(self, key, value, *, skip_if_exists=False):
        with self.lock:
            if skip_if_exists and key in self.values:
                return False
            self.values[key] = copy.deepcopy(value)
            return True


class ServingTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 3, 20, 0, tzinfo=timezone.utc)
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent/'runs')
        self.root = Path(self.temp.name)
        self.selection = dict(final_choice=True, checkpoint_id='final-example-v1',
            model=sc.MODEL, revision=sc.REVISION,
            artifact=dict(run_id='example-trained-v1', adapter_subpath='adapter',
                          files_sha256={'adapter_config.json':'a'*64,'adapter_model.safetensors':'b'*64}),
            evaluation=dict(stage='completed', n=64, correct=58, split_role='development_monitoring',
                            artifact_sha256='c'*64,
                            report_url='https://avisrikumeran.github.io/granite-query/results.html'))
        self.budget = dict(limits={'modal':30}, estimated_spend={'modal':20}, reserved={'modal':1},
            jobs=[dict(run_id='api-final-v1', service='modal', reserved_usd=1,status='reserved')])
        self.clearance = dict(research_phase_closed=True,active_gpu_call_ids=[],checked_at_utc=sc.stamp(self.now))
        self.manifest = self.prepare()

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self, filename='manifest.json'):
        for name,value in (('selection',self.selection),('budget',self.budget),('clearance',self.clearance)):
            (self.root/(name+'.json')).write_text(json.dumps(value),encoding='utf-8')
        return sc.prepare(self.root/'selection.json',self.root/'budget.json',self.root/'clearance.json',
                          self.root/filename,reservation_id='api-final-v1',now=self.now)

    def body(self, request_id=None):
        return dict(prompt='What is 2 plus 2?',max_new_tokens=64,request_id=request_id or str(uuid.uuid4()))

    def test_concurrent_admission_has_twenty_permanent_slots(self):
        store = AtomicStore()
        gate = sc.Admission(store,self.manifest)
        gate.initialize(now=self.now)
        def attempt(_):
            try:
                return gate.claim(self.body(),now=self.now)
            except sc.ServingRefused:
                return None
        with ThreadPoolExecutor(max_workers=16) as pool:
            tickets = [x for x in pool.map(attempt,range(100)) if x]
        self.assertEqual(20,len(tickets))
        self.assertEqual(set(range(20)),{x['slot'] for x in tickets})
        self.assertEqual(20,gate.used())
        # Restart/redeploy under the same namespace never initializes empty quota.
        restarted = sc.Admission(store,self.manifest)
        self.assertFalse(restarted.initialize(now=self.now)['new'])
        with self.assertRaises(sc.ServingRefused):
            restarted.claim(self.body(),now=self.now)

    def test_duplicate_nonce_and_ambiguous_dispatch_do_not_retry(self):
        store = AtomicStore()
        gate = sc.Admission(store,self.manifest)
        gate.initialize(now=self.now)
        body = self.body()
        ticket = gate.claim(body,now=self.now)
        gate.mark_dispatch(ticket,body,now=self.now)
        # A lost response/process crash after dispatch cannot refund the permit.
        with self.assertRaises(sc.ServingRefused):
            gate.mark_dispatch(ticket,body,now=self.now)
        with self.assertRaises(sc.ServingRefused):
            gate.claim(body,now=self.now)
        self.assertEqual(1,gate.used())
        with self.assertRaises(sc.ServingRefused):
            gate.mark_dispatch(ticket,dict(body,prompt='Changed question'),now=self.now)

    def test_refuses_missing_final_measurement_reservation_or_gpu_clearance(self):
        for field,value in (('final_choice',False),('evaluation',{'stage':'running'})):
            original = self.selection[field]
            self.selection[field] = value
            with self.assertRaises(sc.ServingRefused):
                self.prepare('invalid.json')
            self.selection[field] = original
        self.budget['jobs'].append(dict(run_id='active-research',service='modal',status='spawned'))
        with self.assertRaises(sc.ServingRefused):
            self.prepare('active.json')
        self.budget['jobs'].pop()
        self.budget['jobs'][0]['status'] = 'completed'
        with self.assertRaises(sc.ServingRefused):
            self.prepare('no-reserve.json')
        self.budget['jobs'][0]['status'] = 'reserved'
        self.clearance['research_phase_closed'] = False
        with self.assertRaises(sc.ServingRefused):
            self.prepare('not-final.json')
        self.assertLess(sc.estimated_slot_compute_usd(),sc.Decimal('0.05'))

    def test_manifest_immutable_expiry_disabled_and_public_allowlist(self):
        with self.assertRaises(FileExistsError):
            self.prepare()
        changed = copy.deepcopy(self.manifest)
        changed['selection']['artifact']['run_id'] = 'different-adapter'
        with self.assertRaises(sc.ServingRefused):
            sc.validate_manifest(changed,now=self.now)
        with self.assertRaises(sc.ServingRefused):
            sc.validate_manifest(self.manifest,now=self.now+timedelta(hours=24))
        store = AtomicStore()
        gate = sc.Admission(store,self.manifest)
        with self.assertRaises(sc.ServingRefused):
            gate.claim(self.body(),now=self.now)
        gate.initialize(now=self.now)
        store.put(gate.prefix+'control',{'manifest_sha256':self.manifest['manifest_sha256'],'enabled':False})
        with self.assertRaises(sc.ServingRefused):
            gate.claim(self.body(),now=self.now)
        public = json.dumps(sc.public_model(self.manifest))
        for private in ('quota_namespace','reserved_usd','files_sha256','adapter_subpath','sources_sha256'):
            self.assertNotIn(private,public)
        self.assertIn('58',public)
        self.assertIn('development_monitoring',public)

    def test_invalid_input_never_consumes_permit(self):
        gate = sc.Admission(AtomicStore(),self.manifest)
        gate.initialize(now=self.now)
        for body in (self.body()|{'prompt':'x'*2401},self.body()|{'max_new_tokens':257},
                     self.body()|{'request_id':'bad'},self.body()|{'model':'other-model'}):
            with self.assertRaises(sc.ServingRefused):
                gate.claim(body,now=self.now)
        self.assertEqual(0,gate.used())


if __name__ == '__main__':
    unittest.main()
