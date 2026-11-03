import copy
from datetime import datetime,timezone
import unittest
from budget_reconcile import reconcile

NOW=datetime(2026,11,3,18,40,tzinfo=timezone.utc)
SNAPSHOT={'start_utc':'2026-11-01T00:00:00+00:00','end_utc':'2026-12-01T00:00:00+00:00',
    'metered_cost':'2.31593967','billed_cost':'0','queried_at_utc':'2026-11-03T18:40:00+00:00'}


def ledger():
    return {'limits':{'modal':30,'deepseek':20},'estimated_spend':{'modal':12,'deepseek':0.75},
        'reserved':{'modal':9,'deepseek':0},'jobs':[
            {'run_id':'old','service':'modal','status':'completed','reserved_usd':3,'accounted_upper_estimate_usd':3,'app_id':'ap-old'},
            {'run_id':'active','service':'modal','status':'spawned','reserved_usd':3},
            {'run_id':'teacher','service':'deepseek','status':'completed','reserved_usd':4}]}


class BudgetReconcileTests(unittest.TestCase):
    def test_provider_observed_replaces_fake_charges_but_retains_buffer(self):
        original=ledger()
        out=reconcile(original,SNAPSHOT,now=NOW,apps=[{'app_id':'ap-old','state':'stopped','tasks':'0','stopped_at':'2026-11-03T18:00:00+00:00'}])
        self.assertEqual(out['observed_modal_spend'],2.31593967)
        self.assertEqual(out['estimated_spend']['modal'],5.32)
        self.assertEqual(out['reserved']['modal'],3)
        self.assertEqual(out['estimated_spend']['deepseek'],0.75)
        self.assertEqual(out['jobs'][0]['accounted_upper_estimate_usd'],3)
        self.assertEqual(original['estimated_spend']['modal'],12)
        self.assertEqual(out['modal_budget_accounting']['observed_billed_usd'],0)

    def test_recent_terminal_job_keeps_separate_liability(self):
        out=reconcile(ledger(),SNAPSHOT,now=NOW,apps=[{'app_id':'ap-old','state':'stopped','tasks':'0','stopped_at':'2026-11-03T18:35:00+00:00'}])
        self.assertEqual(out['reserved']['modal'],6)
        self.assertEqual(out['modal_budget_accounting']['pending_terminal_liability_usd'],3)
        self.assertEqual(out['modal_budget_accounting']['active_reservations_usd'],3)
        self.assertEqual(out['modal_budget_accounting']['estimated_spend_usd'],5.32)

    def test_unknown_stop_does_not_invent_runtime_or_release(self):
        out=reconcile(ledger(),SNAPSHOT,now=NOW)
        self.assertEqual(out['reserved']['modal'],6)
        self.assertEqual(out['jobs'][0]['budget_liability']['kind'],'terminal_usage_pending_collection')

    def test_idempotent_and_collection_window_releases_without_fake_spend(self):
        apps=[{'app_id':'ap-old','state':'stopped','tasks':'0','stopped_at':'2026-11-03T18:00:00+00:00'}]
        first=reconcile(ledger(),SNAPSHOT,now=NOW,apps=apps)
        second=reconcile(first,SNAPSHOT,now=NOW,apps=apps)
        self.assertEqual(first,second)
        self.assertEqual(len(second['accounting_audit']),1)

    def test_stale_snapshot_blocks_new_launches(self):
        snapshot=dict(SNAPSHOT,queried_at_utc='2026-11-03T18:00:00+00:00')
        out=reconcile(ledger(),snapshot,now=NOW)
        self.assertFalse(out['modal_budget_accounting']['new_paid_launches_allowed'])

    def test_verified_stop_survives_app_disappearing_from_recent_list(self):
        apps=[{'app_id':'ap-old','state':'stopped','tasks':'0','stopped_at':'2026-11-03T18:00:00+00:00'}]
        first=reconcile(ledger(),SNAPSHOT,now=NOW,apps=apps)
        second=reconcile(first,SNAPSHOT,now=NOW,apps=[])
        self.assertEqual(second['reserved']['modal'],3)

    def test_fully_reserved_safe_job_can_launch_at_exact_ceiling(self):
        value=ledger()
        value['limits']['modal']=8.32
        apps=[{'app_id':'ap-old','state':'stopped','tasks':'0','stopped_at':'2026-11-03T18:00:00+00:00'}]
        out=reconcile(value,SNAPSHOT,now=NOW,apps=apps)
        self.assertEqual(out['modal_budget_accounting']['budget_remaining_usd'],0)
        self.assertTrue(out['modal_budget_accounting']['new_paid_launches_allowed'])

    def test_nonfinite_or_negative_provider_values_rejected(self):
        for bad in ('-1','NaN','Infinity'):
            with self.assertRaises(ValueError):
                reconcile(ledger(),dict(SNAPSHOT,metered_cost=bad),now=NOW)


if __name__=='__main__':
    unittest.main()
