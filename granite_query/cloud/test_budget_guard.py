from datetime import datetime,timedelta,timezone
import unittest
from cloud.comparison_control import require_fresh_modal_budget


class BudgetGuardTests(unittest.TestCase):
    def ledger(self,minutes=0):
        return {'modal_budget_accounting':{'new_paid_launches_allowed':True,'collection_lag_minutes':15,'issues':[]},
                'modal_observation':{'queried_at_utc':(datetime.now(timezone.utc)-timedelta(minutes=minutes)).isoformat()},
                'estimated_spend':{'modal':3},'reserved':{'modal':3},'limits':{'modal':30}}

    def test_stale_provider_observation_blocks_new_work(self):
        with self.assertRaises(RuntimeError):
            require_fresh_modal_budget(self.ledger(16))

    def test_fully_reserved_budget_can_launch_already_funded_job(self):
        ledger=self.ledger()
        ledger['reserved']['modal']=27
        ledger['modal_budget_accounting']['new_paid_launches_allowed']=False
        require_fresh_modal_budget(ledger)
        with self.assertRaises(RuntimeError):
            require_fresh_modal_budget(ledger,new_reservation=True)

    def test_overcommitted_or_unknown_budget_blocks_launch(self):
        ledger=self.ledger()
        ledger['reserved']['modal']=28
        with self.assertRaises(RuntimeError):
            require_fresh_modal_budget(ledger)
        ledger=self.ledger()
        ledger['modal_budget_accounting']['issues']=['unknown paid job']
        with self.assertRaises(RuntimeError):
            require_fresh_modal_budget(ledger)


if __name__=='__main__':
    unittest.main()
