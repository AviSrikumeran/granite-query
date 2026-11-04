"""Invented ledger-only fixtures; never opens state or contacts providers."""
import copy
import unittest
from unittest.mock import patch
from cloud import final_scale_funding as funding
from cloud import final_scale_contract as contract_api
from cloud.test_final_scale_contract import complete_contract, calibration

STAMP='2026-11-03T22:59:00+00:00'
NOW='2026-11-03T23:00:00+00:00'
SEAL='e'*64


def ledger():
    value={'limits':{'modal':30,'deepseek':20},'estimated_spend':{'modal':0,'deepseek':0},
        'reserved':{'modal':0,'deepseek':0},'jobs':[],
        'modal_observation':{'queried_at_utc':STAMP},'deepseek_wallet_observation':{'queried_at_utc':STAMP}}
    for service in ('modal','deepseek'):
        value[service+'_budget_accounting']={'basis':(
            'provider_observed_metered_plus_collection_buffer_and_open_liabilities' if service=='modal'
            else 'user_declared_funding_minus_observed_wallet'),
            'estimated_spend_usd':0,'active_reservations_usd':0,'issues':[],'new_paid_launches_allowed':True}
    value['deepseek_budget_accounting'].update(status='conditional_wallet_inference',funding_history_ambiguous=False)
    return value


def fixture(count=1000):
    contract=complete_contract(count);observed=ledger();cal=calibration(contract)
    review=contract_api.review_template(contract)
    review.update(reviewed=True,no_tuning_after_access_acknowledged=True,
        complete_denominator_acknowledged=True,all_source_roles_reviewed=True,
        calibration_sha256=cal['calibration_sha256'],funding_snapshot_sha256=contract_api.digest(funding.snapshot(observed,as_of_utc=NOW)))
    return observed,contract,review,cal


def allocated(count=1000):
    value,contract,review,cal=fixture(count)
    result=funding.allocate(value,contract,review,seal_sha256=SEAL,bundle_id='fixture-final',
        as_of_utc=NOW,actual_source_hashes=contract['protocol']['source_hashes'],calibration_record=cal)
    return result,contract,review


def transfer(value,contract,*,run='fixture-base-000',shard='shard000',recovery=False,checkpoint='base'):
    return funding.transfer(value,contract,bundle_id='fixture-final',seal_sha256=SEAL,
        run_id=run,intent_sha256='a'*64,claim_sha256='b'*64,as_of_utc=NOW,
        checkpoint=checkpoint,shard_id=shard,is_recovery=recovery)


class FundingTests(unittest.TestCase):
    def test_pure_allocation_preserves_original_and_reserves_whole_bundle(self):
        original,contract,review,cal=fixture();saved=copy.deepcopy(original)
        with patch('builtins.open',side_effect=AssertionError('No I/O')):
            result=funding.allocate(original,contract,review,seal_sha256=SEAL,bundle_id='fixture-final',
                as_of_utc=NOW,actual_source_hashes=contract['protocol']['source_hashes'],calibration_record=cal)
        self.assertEqual(original,saved)
        self.assertEqual(result['reserved'],{'modal':12.25,'deepseek':5.})
        self.assertEqual(result['estimated_spend'],original['estimated_spend'])
        self.assertTrue(all(j['reservation_is_not_paid_charge'] for j in result['jobs']))

    def test_full1319_allowance_retains_explicit_recovery(self):
        value,_,_=allocated(1319)
        self.assertEqual(value['reserved'],{'modal':15.75,'deepseek':7.})

    def test_stale_future_or_unsupported_observations_rejected(self):
        for mutation in ('stale','future','unsupported','ambiguous','issues','not_allowed','spend_mismatch'):
            value=ledger()
            if mutation=='stale':value['modal_observation']['queried_at_utc']='2026-11-03T22:00:00+00:00'
            elif mutation=='future':value['deepseek_wallet_observation']['queried_at_utc']='2026-11-03T23:01:00+00:00'
            elif mutation=='unsupported':value['modal_budget_accounting']['basis']='allowance_only'
            elif mutation=='ambiguous':value['deepseek_budget_accounting']['funding_history_ambiguous']=True
            elif mutation=='issues':value['modal_budget_accounting']['issues']=['unknown_call']
            elif mutation=='not_allowed':value['deepseek_budget_accounting']['new_paid_launches_allowed']=False
            else:value['estimated_spend']['modal']=1
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):funding.snapshot(value,as_of_utc=NOW)

    def test_old_unknown_liabilities_are_preserved_and_can_prevent_allocation(self):
        value,contract,review,cal=fixture()
        value['reserved']['modal']=20
        value['jobs'].append({'run_id':'unknown-old','service':'modal','status':'unknown','reserved_usd':20})
        review['funding_snapshot_sha256']=contract_api.digest(funding.snapshot(value,as_of_utc=NOW))
        with self.assertRaises(ValueError):
            funding.allocate(value,contract,review,seal_sha256=SEAL,bundle_id='fixture-final',
                as_of_utc=NOW,actual_source_hashes=contract['protocol']['source_hashes'],calibration_record=cal)
        self.assertEqual(value['jobs'][0]['status'],'unknown')

    def test_duplicate_bundle_never_reserves_twice(self):
        value,contract,review=allocated()
        # Even a freshly rebuilt review cannot allocate the same durable owner twice.
        review['funding_snapshot_sha256']=contract_api.digest(funding.snapshot(value,as_of_utc=NOW))
        with self.assertRaises(ValueError):
            funding.allocate(value,contract,review,seal_sha256=SEAL,bundle_id='fixture-final',as_of_utc=NOW,
                actual_source_hashes=contract['protocol']['source_hashes'],calibration_record=calibration(contract))

    def test_transfer_keeps_total_reserved_and_ambiguous_child_liability(self):
        value,contract,_=allocated();result=transfer(value,contract)
        self.assertEqual(result['reserved'],value['reserved'])
        self.assertEqual(result['estimated_spend'],value['estimated_spend'])
        escrow=result['jobs'][0];child=result['jobs'][-1]
        self.assertEqual((escrow['reserved_usd'],escrow['transferred_usd']),(10.5,1.75))
        self.assertEqual(child['status'],'spawning')
        for run in ('fixture-base-000','another-run'):
            with self.subTest(run=run),self.assertRaises(ValueError):transfer(result,contract,run=run)

    def test_exactly_one_global_recovery_and_no_duplicate_original(self):
        value,contract,_=allocated();value=transfer(value,contract)
        value['jobs'][-1].update(status='failed',call_id='fc-invented-parent')
        with self.assertRaises(ValueError):transfer(value,contract,run='duplicate-original')
        value=transfer(value,contract,run='fixture-base-000-recovery',recovery=True)
        value['jobs'][-1]['status']='completed'
        value=transfer(value,contract,run='fixture-chosen-000',checkpoint='chosen')
        value['jobs'][-1]['status']='failed'
        with self.assertRaises(ValueError):transfer(value,contract,run='second-global-recovery',checkpoint='chosen',recovery=True)

    def test_running_missing_or_completed_parent_cannot_recover(self):
        for status in (None,'spawning','running','completed'):
            value,contract,_=allocated()
            if status:
                value=transfer(value,contract);value['jobs'][-1]['status']=status
            with self.subTest(status=status),self.assertRaises(ValueError):transfer(value,contract,run='recovery',recovery=True)

    def test_broken_transfer_conservation_and_lost_protection_fail(self):
        for change in ('escrow','transferred','recovery','protection'):
            value,contract,_=allocated();value=transfer(value,contract);value['jobs'][-1]['status']='completed'
            if change=='escrow':value['jobs'][0]['reserved_usd']-=1
            elif change=='transferred':value['jobs'][0]['transferred_usd']=0
            elif change=='recovery':value['jobs'][0]['recovery_claimed']=True
            else:
                value['estimated_spend']['modal']=14;value['modal_budget_accounting']['estimated_spend_usd']=14
            with self.subTest(change=change),self.assertRaises(ValueError):
                funding.validate_escrow(value,contract,bundle_id='fixture-final',seal_sha256=SEAL,as_of_utc=NOW)

    def test_malformed_ids_caps_roles_and_review_cannot_allocate_or_transfer(self):
        value,contract,review,cal=fixture();review['reviewed']=False
        with self.assertRaises(ValueError):funding.allocate(value,contract,review,seal_sha256=SEAL,bundle_id='fixture-final',
            as_of_utc=NOW,actual_source_hashes=contract['protocol']['source_hashes'],calibration_record=cal)
        value,contract,_=allocated()
        for keyword,val in (('run_id','../bad'),('checkpoint','teacher'),('shard_id','shard999'),('is_recovery',1)):
            args=dict(bundle_id='fixture-final',seal_sha256=SEAL,run_id='safe',intent_sha256='a'*64,
                claim_sha256='b'*64,as_of_utc=NOW,checkpoint='base',shard_id='shard000',is_recovery=False)
            args[keyword]=val
            with self.subTest(keyword=keyword),self.assertRaises(ValueError):funding.transfer(value,contract,**args)


if __name__=='__main__':unittest.main()
