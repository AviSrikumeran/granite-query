"""Synthetic CPU-delay/final-fresh-boundary checks; no providers or real state."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from cloud import native_v4_transport_wait_v2 as transport
from cloud import test_native_v4_transport as original


class Fixture(original.Fixture):
    def __init__(self):
        super().__init__()
        transport.control.write(self.folder/'plan.json',{'INVENTED':'fixed2048plan'})
        transport.control.write(self.folder/'input.json',{'INVENTED':'fixed200inputs'})
        transport.control.write(self.output/'transport_wait_review_v2.json',dict(transport.policy_template(self.output),reviewed=True))
    def stage(self,*,age=600):
        observed=datetime.now(timezone.utc)-timedelta(seconds=age)
        evidence=deepcopy(self.evidence);evidence['observed_at_utc']=observed.isoformat()
        delegation={'version':transport.base.VERSION,'new_driver':self.identity,
            'launcher_executable':str(Path(sys.executable).absolute()),
            'original_owner_sha256':transport.control.sha(self.folder/'controller_owner.json'),
            'claim_id':self.dispatch['claim_id'],'transport_review_sha256':transport.control.sha(self.output/'transport_review.json')}
        transport.control.write(self.folder/'transport_never_transmitted.json',evidence)
        transport.control.write(self.folder/'transport_delegation.json',delegation)
        intent={'version':transport.base.VERSION,'created_at_utc':(observed+timedelta(seconds=10)).isoformat(),
            'delegation_sha256':transport.control.sha(self.folder/'transport_delegation.json'),
            'dispatch_sha256':transport.control.sha(self.folder/'dispatch.json'),
            'fresh_reconciliation_sha256':transport.control.sha(self.folder/'transport_never_transmitted.json'),
            'original_failed_receipt_sha256':transport.control.sha(self.folder/'launch_receipt.private.json'),
            'transport_source_sha256':transport.base.source_hashes()}
        transport.control.write(self.folder/'transport_repair_intent.json',intent)
        transport.control.write(self.folder/'transport_wait_policy_claim_v2.json',{'version':transport.VERSION,
            'wait_review_sha256':transport.control.sha(self.output/'transport_wait_review_v2.json'),
            'base_intent_sha256':transport.control.sha(self.folder/'transport_repair_intent.json'),
            'dispatch_sha256':transport.control.sha(self.folder/'dispatch.json'),'wait_source_sha256':transport.source_hashes(),
            'module':transport.REPAIR_CLI,'local_cli_wait_seconds':900,'new_reservation_created':False})
        return evidence,intent
    def context(self):
        with patch.object(transport.base,'observe_cli_ancestry',return_value={'depth':1}),\
                patch.object(transport.control,'review',return_value=transport.control.read(self.output/'review_baseline.json')),\
                patch.object(transport.base.frozen_cli.worker,'validate_dispatch',return_value=True),\
                patch.object(transport.base.frozen_cli.worker,'verify_sources',return_value={}):
            return transport.delegated_preflight_v2(self.folder)


class WaitTests(unittest.TestCase):
    def setUp(self):self.f=Fixture();self.addCleanup(self.f.close)
    def test_cpu_delay_ages_historical_fact_but_final_observation_is_fresh(self):
        historical,intent=self.f.stage(age=600)
        with self.assertRaises(ValueError):transport.base._fresh_absence(historical,self.f.job)
        with transport.control.exclusive(self.f.state/'gpu_launch.lock'):
            context=self.f.context()
            fresh=self.f.backend.absence(self.f.job['run_id'],[21432,32920])
            fresh['apps'].append({'app_id':'ap-INVENTEDcurrent','state':'ephemeral','tasks':0})
            with patch.object(transport.base,'observe_cli_ancestry',return_value={'depth':1}),\
                    patch.object(transport.base,'validate_transport_review',side_effect=AssertionError('No heavy review after fresh read')),\
                    patch.object(transport.control,'load_jobs',side_effect=AssertionError('No teacher replay after fresh read')),\
                    patch.object(transport.control,'validate_stage_funding',side_effect=AssertionError('No heavy funding replay after fresh read')):
                self.assertEqual(transport.final_guard(context,fresh,own_app_id='ap-INVENTEDcurrent'),{'depth':1})
                old=deepcopy(fresh);old['observed_at_utc']=(datetime.now(timezone.utc)-timedelta(seconds=121)).isoformat()
                with self.assertRaises(ValueError):transport.final_guard(context,old,own_app_id='ap-INVENTEDcurrent')
    def test_final_guard_checks_original_owner_and_input_plan_bytes(self):
        self.f.stage()
        with transport.control.exclusive(self.f.state/'gpu_launch.lock'):
            context=self.f.context();fresh=self.f.backend.absence(self.f.job['run_id'],[21432,32920])
            for name in ('controller_owner.json','plan.json','input.json','transport_never_transmitted.json'):
                path=self.f.folder/name;before=path.read_bytes();path.write_bytes(before+b' ')
                try:
                    with self.subTest(name=name),self.assertRaises(ValueError):transport.final_guard(context,fresh,own_app_id='ap-INVENTEDcurrent')
                finally:path.write_bytes(before)
    def test_wait_policy_claim_precedes_actual900second_subprocess(self):
        self.f.stage()
        def actual(args,**kwargs):
            self.assertTrue((self.f.folder/'transport_wait_policy_claim_v2.json').exists())
            self.assertEqual(kwargs['timeout'],900);self.assertIn(transport.REPAIR_CLI,args)
            return SimpleNamespace(returncode=0,stdout=b'ap-INVENTED-correct\n',stderr=b'')
        with patch.object(transport.subprocess,'run',side_effect=actual):
            result=transport.WaitBackend().run_cli(self.f.folder,repair=True)
        self.assertEqual(result['local_cli_wait_seconds'],900)
        self.assertFalse((self.f.folder/'launch.json').exists())
    def test_final_guard_rejects_changed_funding_without_historical_asof(self):
        self.f.stage()
        with transport.control.exclusive(self.f.state/'gpu_launch.lock'):
            context=self.f.context();fresh=self.f.backend.absence(self.f.job['run_id'],[21432,32920])
            ledger=transport.control.read(self.f.state/'budget.json');ledger['estimated_spend']['modal']=25
            transport.control.write(self.f.state/'budget.json',ledger)
            with patch.object(transport.base,'observe_cli_ancestry',return_value={'depth':1}),self.assertRaises(ValueError):
                transport.final_guard(context,fresh,own_app_id='ap-INVENTEDcurrent')


if __name__=='__main__':unittest.main()
