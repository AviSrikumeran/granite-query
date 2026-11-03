import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import funding_watch as watcher


class FundingWatchTests(unittest.TestCase):
    def temporary(self):
        parent=watcher.ROOT/'runs/local_check_tmp';parent.mkdir(parents=True,exist_ok=True)
        return tempfile.TemporaryDirectory(dir=parent)

    def test_completed_halted_and_reused_pid_stop_without_touching_collector(self):
        with self.temporary() as temporary:
            root=Path(temporary)
            for stage in ('completed','halted'):
                (root/'teacher_summary.json').write_text(json.dumps({'stage':stage,'completed':4,'requested':4}))
                result=watcher.collector_state(root,identity_fn=lambda _:self.fail('Terminal collector queried'))
                self.assertEqual(result['stop_reason'],'collector_'+stage)
            (root/'teacher_summary.json').write_text(json.dumps({'stage':'collecting'}))
            (root/'collector.lock').write_text('123')
            result=watcher.collector_state(root,identity_fn=lambda _:dict(alive=True,created_at_utc='new'),expected_pid=123,expected_created='old')
            self.assertEqual(result['stop_reason'],'collector_pid_reused')
            self.assertEqual((root/'collector.lock').read_text(),'123')

    def test_budget_lock_retry_is_local_and_bounded(self):
        with self.temporary() as temporary:
            root=Path(temporary);(root/'budget_reconcile.lock').write_text('other-owner')
            pauses=[]
            result=watcher.refresh_once(root,'job',13,runner=lambda *a,**k:self.fail('Provider must not be read under existing lock'),sleep=pauses.append)
            self.assertEqual(result['status'],'budget_busy')
            self.assertEqual(pauses,[.5,.5,.5])

    def test_provider_failure_is_not_retried(self):
        with self.temporary() as temporary:
            calls=[]
            def run(*args,**kwargs):
                calls.append(args);return subprocess.CompletedProcess(args,1,'','RuntimeError: DeepSeek balance HTTP 401')
            result=watcher.refresh_once(Path(temporary),'job',13,runner=run,sleep=lambda _:self.fail('Auth failure retried'))
            self.assertEqual(result['failure_kind'],'provider_refresh_failed')
            self.assertEqual(len(calls),1)

    def test_refresh_requires_unchanged_funded_job_and_safe_guard(self):
        with self.temporary() as temporary:
            root=Path(temporary)
            ledger={'jobs':[{'run_id':'job','service':'deepseek','reserved_usd':13}],
                'deepseek_budget_accounting':{'status':'conditional_wallet_inference','issues':[]},
                'deepseek_wallet_observation':{'queried_at_utc':'2026-11-03T19:00:00+00:00'}}
            (root/'budget.json').write_text(json.dumps(ledger))
            run=lambda *a,**k:subprocess.CompletedProcess(a,0,'{}','')
            with patch.object(watcher,'require_fresh_deepseek_budget'):
                result=watcher.refresh_once(root,'job',13,runner=run)
                self.assertEqual(result['status'],'refreshed')
                changed=watcher.refresh_once(root,'job',14,runner=run)
                self.assertEqual(changed['failure_kind'],'reservation_changed')
            with patch.object(watcher,'require_fresh_deepseek_budget',side_effect=RuntimeError('Ambiguous')):
                result=watcher.refresh_once(root,'job',13,runner=run)
                self.assertEqual(result['failure_kind'],'funding_or_account_guard')

    def test_runtime_limit_releases_only_own_lock_and_never_restarts_collector(self):
        with self.temporary() as temporary:
            root=Path(temporary)
            (root/'plan.json').write_text(json.dumps({'budget_job_id':'job','reserved_usd_required':13}))
            (root/'launch.json').write_text(json.dumps({'worker_pid':123}))
            (root/'collector.lock').write_text('123')
            (root/'teacher_summary.json').write_text(json.dumps({'stage':'collecting','completed':8,'requested':1800}))
            (root/'deepseek_funding_baseline.json').write_text('{}')
            ticks=[0];refreshes=[]
            def sleep(seconds):ticks[0]+=seconds
            def refresh(*args):
                refreshes.append(args)
                return {'status':'refreshed','queried_at_utc':'2026-11-03T19:00:00+00:00'}
            with patch.object(watcher,'record'),patch.object(watcher,'STATE',root):
                result=watcher.watch(root,interval_seconds=30,max_seconds=31,
                    identity_fn=lambda _:dict(alive=True,created_at_utc='same'),
                    refresh_fn=refresh,clock=lambda:ticks[0],sleep=sleep)
            self.assertEqual(result['stop_reason'],'maximum_runtime_reached')
            self.assertEqual(len(refreshes),2)
            self.assertFalse((root/'funding_watch.lock').exists())
            self.assertEqual((root/'collector.lock').read_text(),'123')
            self.assertFalse(result['paid_generation_launched'])

    def test_existing_watcher_lock_prevents_duplicate_refreshes(self):
        with self.temporary() as temporary:
            root=Path(temporary)
            (root/'plan.json').write_text(json.dumps({'budget_job_id':'job','reserved_usd_required':13}))
            (root/'launch.json').write_text(json.dumps({'worker_pid':123}))
            (root/'collector.lock').write_text('123')
            (root/'funding_watch.lock').write_text('existing-owner')
            (root/'deepseek_funding_baseline.json').write_text('{}')
            with patch.object(watcher,'STATE',root),self.assertRaises(FileExistsError):
                watcher.watch(root,identity_fn=lambda _:dict(alive=True,created_at_utc='same'),
                    refresh_fn=lambda *a:self.fail('Duplicate watcher refreshed provider'))
            self.assertEqual((root/'funding_watch.lock').read_text(),'existing-owner')


if __name__=='__main__':
    unittest.main()
