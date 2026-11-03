import copy
from datetime import datetime,timezone
from decimal import Decimal
import json
import unittest
from deepseek_reconcile import reconcile,user_declared_baseline,summarize_public,require_fresh_deepseek_budget

NOW=datetime(2026,11,3,18,50,tzinfo=timezone.utc)
SNAPSHOT={'queried_at_utc':'2026-11-03T18:48:00+00:00','is_available':True,
    'balance_infos':[{'currency':'USD','total_balance':'19.64','granted_balance':'0.00','topped_up_balance':'19.64'}]}


def ledger():
    return {'limits':{'deepseek':20,'modal':30},'estimated_spend':{'deepseek':.75,'modal':5.93},
        'reserved':{'deepseek':0,'modal':3},'jobs':[
            {'run_id':'first','service':'deepseek','status':'completed','reserved_usd':4,'accounted_upper_estimate_usd':.72},
            {'run_id':'gpu','service':'modal','status':'spawned','reserved_usd':3}]}


class DeepSeekReconcileTests(unittest.TestCase):
    def test_conditional_usage_peak_estimate_and_public_privacy_are_distinct(self):
        original=ledger()
        result=reconcile(original,SNAPSHOT,user_declared_baseline(SNAPSHOT),now=NOW)
        public=summarize_public(result)
        self.assertEqual(public['observed_project_usage_usd'],.36)
        self.assertEqual(public['recorded_peak_estimate_usd'],.75)
        self.assertEqual(result['estimated_spend']['deepseek'],.46)
        self.assertEqual(public['budget_remaining_usd'],19.54)
        self.assertTrue(public['new_paid_launches_allowed'])
        self.assertEqual(result['limits']['deepseek'],20)
        self.assertEqual(result['estimated_spend']['modal'],5.93)
        self.assertEqual(original['estimated_spend']['deepseek'],.75)
        for private in ('total_balance','topped_up_balance','granted_balance','19.64','user_statement_excerpt'):
            self.assertNotIn(private,json.dumps(public))

    def test_active_reservations_and_idempotence(self):
        value=ledger();value['jobs'].append({'run_id':'new','service':'deepseek','status':'in_progress','reserved_usd':4})
        baseline=user_declared_baseline(SNAPSHOT)
        first=reconcile(value,SNAPSHOT,baseline,now=NOW)
        second=reconcile(first,SNAPSHOT,baseline,now=NOW)
        self.assertEqual(first,second)
        self.assertEqual(second['reserved']['deepseek'],4)
        self.assertEqual(second['deepseek_budget_accounting']['budget_committed_usd'],4.46)
        self.assertTrue(second['deepseek_budget_accounting']['new_paid_launches_allowed'])

    def test_missing_or_changed_baseline_falls_back_without_inventing_credit(self):
        missing=reconcile(ledger(),SNAPSHOT,None,now=NOW)
        self.assertEqual(missing['estimated_spend']['deepseek'],.75)
        self.assertEqual(missing['deepseek_budget_accounting']['status'],'needs_clarification')
        self.assertFalse(missing['deepseek_budget_accounting']['new_paid_launches_allowed'])
        baseline=user_declared_baseline(SNAPSHOT)
        first=reconcile(ledger(),SNAPSHOT,baseline,now=NOW)
        changed=dict(baseline,original_funding_usd='30')
        after=reconcile(first,SNAPSHOT,changed,now=NOW)
        self.assertEqual(after['limits']['deepseek'],20)
        self.assertGreaterEqual(after['estimated_spend']['deepseek'],.75)
        self.assertFalse(after['deepseek_budget_accounting']['new_paid_launches_allowed'])

    def test_grants_additional_currency_topups_and_adjustments_fail_closed(self):
        baseline=user_declared_baseline(SNAPSHOT)
        first=reconcile(ledger(),SNAPSHOT,baseline,now=NOW)
        bad=[]
        grant=copy.deepcopy(SNAPSHOT);grant['balance_infos'][0].update(total_balance='19.65',granted_balance='.01');bad.append(grant)
        topup=copy.deepcopy(SNAPSHOT);topup['balance_infos'][0].update(total_balance='20.64',topped_up_balance='20.64');bad.append(topup)
        refund=copy.deepcopy(SNAPSHOT);refund['balance_infos'][0].update(total_balance='19.65',topped_up_balance='19.65');bad.append(refund)
        currency=copy.deepcopy(SNAPSHOT);currency['balance_infos'].append({'currency':'CNY','total_balance':'1','topped_up_balance':'1','granted_balance':'0'});bad.append(currency)
        invalid=copy.deepcopy(SNAPSHOT);invalid['balance_infos'][0]['total_balance']='19';bad.append(invalid)
        for snapshot in bad:
            after=reconcile(first,snapshot,baseline,now=NOW)
            self.assertFalse(after['deepseek_budget_accounting']['new_paid_launches_allowed'])
            self.assertGreaterEqual(after['estimated_spend']['deepseek'],.75)
            self.assertEqual(after['deepseek_wallet_observation'],first['deepseek_wallet_observation'])
            # A later clean-looking balance cannot erase a previously seen credit.
            again=reconcile(after,SNAPSHOT,baseline,now=NOW)
            self.assertFalse(again['deepseek_budget_accounting']['new_paid_launches_allowed'])

    def test_high_water_and_token_peak_update_independently(self):
        baseline=user_declared_baseline(SNAPSHOT)
        first=reconcile(ledger(),SNAPSHOT,baseline,now=NOW)
        newer=copy.deepcopy(SNAPSHOT);newer['queried_at_utc']='2026-11-03T18:49:00+00:00'
        newer['balance_infos'][0].update(total_balance='19.00',topped_up_balance='19.00')
        first['jobs'].append({'service':'deepseek','status':'completed','accounted_upper_estimate_usd':2.0})
        after=reconcile(first,newer,baseline,now=NOW)
        self.assertEqual(after['deepseek_budget_accounting']['observed_usage_high_water_usd'],1)
        self.assertEqual(after['estimated_spend']['deepseek'],1.1)
        self.assertEqual(after['deepseek_recorded_peak_estimate_usd'],2.75)

    def test_stale_unknown_unavailable_and_overcommitted_work_block_new_reservations(self):
        baseline=user_declared_baseline(SNAPSHOT)
        stale=reconcile(ledger(),SNAPSHOT,baseline,now=datetime(2026,11,3,19,10,tzinfo=timezone.utc))
        self.assertFalse(stale['deepseek_budget_accounting']['new_paid_launches_allowed'])
        value=ledger();value['jobs'].append({'service':'deepseek','status':'mystery','reserved_usd':2})
        unknown=reconcile(value,SNAPSHOT,baseline,now=NOW)
        self.assertEqual(unknown['reserved']['deepseek'],2)
        self.assertFalse(unknown['deepseek_budget_accounting']['new_paid_launches_allowed'])
        value=ledger();value['jobs'].append({'service':'deepseek','status':'reserved','reserved_usd':20})
        over=reconcile(value,SNAPSHOT,baseline,now=NOW)
        with self.assertRaises(RuntimeError):require_fresh_deepseek_budget(over,now=NOW,new_reservation=True)
        unavailable=reconcile(ledger(),dict(SNAPSHOT,is_available=False),baseline,now=NOW)
        self.assertFalse(unavailable['deepseek_budget_accounting']['new_paid_launches_allowed'])

    def test_fresh_guard_accepts_funded_work_and_blocks_stale_observation(self):
        result=reconcile(ledger(),SNAPSHOT,user_declared_baseline(SNAPSHOT),now=NOW)
        require_fresh_deepseek_budget(result,now=NOW,new_reservation=True)
        with self.assertRaises(RuntimeError):
            require_fresh_deepseek_budget(result,now=datetime(2026,11,3,19,10,tzinfo=timezone.utc))
        self.assertFalse('deepseek_budget_accounting' in ledger())
        require_fresh_deepseek_budget(ledger(),now=NOW)


if __name__=='__main__':
    unittest.main()
