"""Private invented refresh transactions; no actual provider or ledger I/O."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from cloud import native_batch_budget_refresh_v4 as refresh


class RefreshTests(unittest.TestCase):
    def setUp(self):
        parent = refresh.control.PRIVATE / 'local_check_tmp'; parent.mkdir(parents=True,exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assertTrue(self.root.resolve().is_relative_to(refresh.control.PRIVATE.resolve()))
        self.state, self.run = self.root/'state', self.root/'run'
        self.state.mkdir(); self.run.mkdir()
        self.ledger = {'limits':{'modal':30,'deepseek':20},'estimated_spend':{'modal':0,'deepseek':2},
            'reserved':{'modal':1.75,'deepseek':7},'jobs':[
                {'run_id':'invented_current_v4','service':'modal','status':'running','reserved_usd':1.75,'app_id':'ap-INVENTED'},
                {'run_id':'invented_teacher_hold','service':'deepseek','status':'reserved','reserved_usd':7}]}
        self.apps = [{'app_id':'ap-INVENTED','state':'detached','tasks':1}]
        self.snapshot = {'queried_at_utc':datetime.now(timezone.utc).isoformat(),
            'start_utc':(datetime.now(timezone.utc)-timedelta(days=1)).isoformat(),
            'metered_cost':'4.25','billed_cost':'0','source':'Invented supported observation fixture'}
        for name, value in (('budget.json',self.ledger),('modal_billing_snapshot.json',self.snapshot),
                ('modal_app_status_snapshot.json',{'apps':self.apps})):
            (self.state/name).write_bytes(refresh.encode(value))
        self.proof = Mock(return_value={'run_id':self.run.name,'fixture':True})
        self.recheck = Mock()
        self.fetch = Mock(return_value=(deepcopy(self.snapshot),deepcopy(self.apps)))

    def call(self, **kwargs):
        return refresh.refresh_budget(self.run,state=self.state,fetch_provider=self.fetch,
            proof_validator=self.proof,proof_recheck=self.recheck,**kwargs)

    def bytes(self): return {name:(self.state/name).read_bytes() for name in refresh.FILES}
    def locks(self): return [self.state/name for name in ('native_batch_budget_refresh.lock','gpu_launch.lock','budget_reconcile.lock')]

    def test_default_saved_dry_read_has_no_fetch_or_filesystem_changes(self):
        before = {path.relative_to(self.root):path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        value = self.call()
        self.fetch.assert_not_called(); self.proof.assert_called_once()
        self.assertFalse(value['wrote']); self.assertFalse(value['refreshed'])
        self.assertEqual(before,{path.relative_to(self.root):path.read_bytes() for path in self.root.rglob('*') if path.is_file()})

    def test_refresh_commits_budget_last_allows_active_app_and_preserves_deepseek7(self):
        original = refresh._atomic_replace; order = []
        self.snapshot['metered_cost']='4.50'
        def write(path, raw):
            self.assertTrue(all(lock.exists() for lock in self.locks()))
            if Path(path).parent==self.state: order.append(Path(path).name)
            return original(path,raw)
        def fetch():
            self.assertFalse(any(lock.exists() for lock in self.locks()))
            return deepcopy(self.snapshot),deepcopy(self.apps)
        self.fetch.side_effect = fetch
        with patch.object(refresh,'_atomic_replace',side_effect=write): value = self.call(refresh=True,write=True)
        self.assertEqual(order,list(refresh.FILES))
        self.fetch.assert_called_once(); self.assertTrue(value['wrote'])
        self.assertFalse(any(lock.exists() for lock in self.locks()))
        ledger = refresh.parse((self.state/'budget.json').read_bytes())
        self.assertEqual(ledger['reserved']['deepseek'],7)
        self.assertEqual(ledger['estimated_spend']['deepseek'],2)
        self.assertEqual(refresh._history(ledger),refresh._history(self.ledger))
        self.assertEqual(ledger['jobs'][0]['status'],'running')
        self.assertEqual(ledger['jobs'][0]['reserved_usd'],1.75)
        self.assertTrue(ledger['modal_budget_accounting']['new_paid_launches_allowed'])
        directory = self.state/refresh.TRANSACTIONS/value['transaction_id']
        self.assertTrue((directory/'committed.json').is_file())
        self.assertEqual(refresh.recover_transaction(directory,state=self.state)['stage'],'already_committed')

    def test_unknown_state_is_held_and_malformed_apps_or_physical_proof_do_not_write(self):
        self.ledger['jobs'].append({'run_id':'invented_unknown','service':'modal','status':'unrecognized','reserved_usd':2})
        (self.state/'budget.json').write_bytes(refresh.encode(self.ledger))
        value = self.call(write=True)
        self.assertFalse(value['new_paid_launches_allowed'])
        ledger = refresh.parse((self.state/'budget.json').read_bytes())
        self.assertEqual(ledger['jobs'][-1]['status'],'unrecognized')
        self.assertEqual(ledger['jobs'][-1]['reserved_usd'],2)
        self.assertEqual(ledger['reserved']['modal'],3.75)
        before = self.bytes()
        self.fetch.return_value = (self.snapshot,[dict(self.apps[0],tasks='?')])
        with self.assertRaises(ValueError): self.call(refresh=True,write=True)
        self.assertEqual(self.bytes(),before)
        self.proof.side_effect = ValueError('Invented frozen source/parent/funding mismatch')
        with self.assertRaises(ValueError): self.call(write=True)
        self.assertEqual(self.bytes(),before)
        self.assertFalse(any(lock.exists() for lock in self.locks()))

    def test_caught_replace_failure_rolls_back_exact_bytes_without_fetch_retry(self):
        before = self.bytes(); original = refresh._atomic_replace; failed = False
        def write(path, raw):
            nonlocal failed
            if Path(path).name=='modal_app_status_snapshot.json' and not failed:
                failed = True; raise PermissionError('Invented local sync contention')
            return original(path,raw)
        # Make the fetched snapshots differ, so an interrupted multi-file commit is exercised.
        changed = deepcopy(self.snapshot); changed['metered_cost']='4.5'
        self.fetch.return_value=(changed,self.apps)
        with patch.object(refresh,'_atomic_replace',side_effect=write):
            with self.assertRaises(PermissionError): self.call(refresh=True,write=True)
        self.assertEqual(self.bytes(),before); self.fetch.assert_called_once()
        self.assertFalse(any(lock.exists() for lock in self.locks()))
        directories = list((self.state/refresh.TRANSACTIONS).iterdir())
        self.assertEqual(len(directories),1)
        self.assertTrue((directories[0]/'rolled_back.json').is_file())

    def test_python_interrupt_after_first_real_replace_never_unlocks_mixed_files(self):
        before=self.bytes(); original=refresh._atomic_replace; interrupted=False
        changed=deepcopy(self.snapshot); changed['metered_cost']='4.80'
        self.fetch.return_value=(changed,self.apps)
        def write(path,raw):
            nonlocal interrupted
            original(path,raw)
            if Path(path).name=='modal_billing_snapshot.json' and not interrupted:
                interrupted=True; raise KeyboardInterrupt('Invented process interruption after canonical replacement')
        with patch.object(refresh,'_atomic_replace',side_effect=write):
            with self.assertRaises(KeyboardInterrupt): self.call(refresh=True,write=True)
        self.assertEqual(self.bytes(),before)
        self.assertFalse(any(lock.exists() for lock in self.locks()))
        self.fetch.assert_called_once()
        directory=next((self.state/refresh.TRANSACTIONS).iterdir())
        self.assertTrue((directory/'rolled_back.json').is_file())

    def test_actual_physical_gate_and_pins_cover_input_source_parent_and_funding(self):
        for name in ('design.json','study_manifest.json','funding.json'):
            (self.run/name).write_bytes(refresh.encode({'fixture':name}))
        jobs=[]
        for index in range(3):
            folder=self.run/'arms'/str(index); folder.mkdir(parents=True)
            for name in ('input.json','plan.json'): (folder/name).write_bytes(refresh.encode({'fixture':name}))
            jobs.append({'run_id':f'invented{index}','folder_path':folder})
        sources={'invented_frozen_source.py':'a'*64}
        with patch.object(refresh.control,'load_jobs',return_value=jobs) as load, \
                patch.object(refresh.control,'validate_stage_funding') as funding, \
                patch.object(refresh.control,'source_inventory',return_value=sources):
            proof=refresh.physical_proof(self.run,self.ledger)
            load.assert_called_once_with(self.run); funding.assert_called_once_with(self.run,self.ledger)
            refresh.recheck_proof(self.run,proof)
            (jobs[1]['folder_path']/'input.json').write_bytes(refresh.encode({'changed':True}))
            with self.assertRaises(ValueError): refresh.recheck_proof(self.run,proof)

    def test_private_hard_crash_recovery_accepts_only_exact_old_or_new_hashes(self):
        old = self.bytes(); new = dict(old)
        changed = deepcopy(self.snapshot); changed['metered_cost']='4.75'
        new['modal_billing_snapshot.json']=refresh.encode(changed)
        directory, manifest = refresh._stage(self.state,old,new,{'fixture':True})
        (self.state/'modal_billing_snapshot.json').write_bytes(new['modal_billing_snapshot.json'])
        result = refresh.recover_transaction(directory,state=self.state)
        self.assertEqual(result['stage'],'rolled_back'); self.assertEqual(self.bytes(),old)
        self.assertFalse(any(lock.exists() for lock in self.locks()))
        directory, manifest = refresh._stage(self.state,old,new,{'fixture':True})
        foreign = refresh.encode({'third_party':'never overwrite'})
        (self.state/'budget.json').write_bytes(foreign)
        with self.assertRaises(refresh.RecoveryRequired): refresh.recover_transaction(directory,state=self.state)
        self.assertEqual((self.state/'budget.json').read_bytes(),foreign)
        self.assertTrue(all(lock.exists() for lock in self.locks()))
        self.fetch.assert_not_called()

    def test_existing_foreign_shared_lock_and_state_cas_block_updates(self):
        before = self.bytes(); lock = self.state/'gpu_launch.lock'; lock.write_bytes(b'999999')
        with self.assertRaises(FileExistsError): self.call(write=True)
        self.assertEqual(lock.read_bytes(),b'999999'); self.assertEqual(self.bytes(),before)
        lock.unlink()
        foreign = refresh.encode(dict(self.ledger,third_party_update=True))
        def validator(run,ledger):
            (self.state/'budget.json').write_bytes(foreign)
            return {'run_id':run.name}
        self.proof.side_effect = validator
        with self.assertRaises(ValueError): self.call(write=True)
        self.assertEqual((self.state/'budget.json').read_bytes(),foreign)
        self.assertFalse(any(item.exists() for item in self.locks()))

    def test_staged_payload_tamper_is_never_used_for_recovery(self):
        old=self.bytes(); directory,_=refresh._stage(self.state,old,old,{'fixture':True})
        (directory/'old/budget.json').write_bytes(refresh.encode({'tampered':True}))
        with self.assertRaises(ValueError): refresh.recover_transaction(directory,state=self.state)
        self.assertEqual(self.bytes(),old)
        self.assertTrue(all(lock.exists() for lock in self.locks()))


if __name__=='__main__': unittest.main()
