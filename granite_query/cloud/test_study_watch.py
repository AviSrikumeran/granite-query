"""Fake clocks/core ticks only; no watch or provider work runs against production."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import study_watch as watch
from cloud import study_runner as core
from test_study_runner import fixture


class Clock:
    def __init__(self):self.value=0;self.sleeps=[]
    def time(self):return self.value
    def sleep(self,value):self.sleeps.append(value);self.value+=value


class FakeRunner:
    def __init__(self,grid,*,review=None,state_dir=None,statuses):
        self.real=core.StudyRunner(grid,review=review,state_dir=state_dir,backend=object(),verifier=lambda _:None,journal=lambda *a:None)
        self.jobs=[];self.review_path=self.real.review_path;self.statuses=list(statuses);self.calls=0
    def load(self):self.real.load();self.jobs=self.real.jobs
    def review(self):return self.real.review()
    def tick(self,advance=False):
        assert advance is True
        self.calls+=1
        if getattr(self,'on_tick',None):self.on_tick(self)
        item=self.statuses[min(self.calls-1,len(self.statuses)-1)]
        if isinstance(item,Exception):raise item
        return dict(item)


class StudyWatchTests(unittest.TestCase):
    def temporary(self):
        parent=core.ROOT/'runs/local_check_tmp';parent.mkdir(parents=True,exist_ok=True)
        return tempfile.TemporaryDirectory(dir=parent)
    def run_watch(self,grid,state,statuses,**kwargs):
        clock=Clock();holders=[];regenerations=[];events=[]
        on_tick=kwargs.pop('on_tick',None)
        def factory(*a,**k):
            value=FakeRunner(*a,**k,statuses=statuses);value.on_tick=on_tick;holders.append(value);return value
        value=watch.watch(grid,state_dir=state,runner_factory=factory,
            identity_fn=lambda _:dict(alive=True,created_at_utc='fixture'),clock=clock.time,sleep=clock.sleep,
            interval_seconds=30,max_seconds=kwargs.pop('max_seconds',61),
            regenerator=kwargs.pop('regenerator',lambda _:regenerations.append(1)),journal=lambda *args:events.append(args),**kwargs)
        return value,clock,holders,regenerations,events

    def test_completion_and_actionable_errors_stop_without_another_tick(self):
        for terminal in ('approved_grid_completed','action_required','budget_refresh_blocked'):
            with self.temporary() as temporary:
                grid,state,_=fixture(Path(temporary))
                result,clock,owners,_,_=self.run_watch(grid,state,[{'stage':terminal}])
                self.assertEqual(result['stop_reason'],terminal);self.assertEqual(owners[0].calls,1)
                self.assertEqual(clock.sleeps,[]);self.assertFalse((state/'study_watch.lock').exists())

    def test_budget_or_gpu_wait_is_bounded_and_unchanged_counters_stay_quiet(self):
        with self.temporary() as temporary:
            grid,state,_=fixture(Path(temporary))
            result,clock,owners,regenerations,_=self.run_watch(grid,state,[{'stage':'waiting_for_protected_phase_funding'}])
            self.assertEqual(result['stop_reason'],'maximum_runtime_reached')
            self.assertEqual(owners[0].calls,3);self.assertEqual(clock.value,61)
            # First state plus final stop only; repeated identical waits do not regenerate.
            self.assertEqual(len(regenerations),2)

    def test_owned_or_stale_lock_is_never_removed_or_overwritten(self):
        for alive,created,stage in ((True,'fixture','another_watch_running'),
                (False,'fixture','stale_watch_lock_requires_review'),(True,'reused-pid','stale_watch_lock_requires_review')):
            with self.temporary() as temporary:
                grid,state,_=fixture(Path(temporary));path=state/'study_watch.lock'
                core.write(path,{'watcher_pid':123,'created_at_utc':'fixture'})
                original=path.read_bytes()
                result=watch.watch(grid,state_dir=state,identity_fn=lambda _:dict(alive=alive,created_at_utc=created))
                self.assertEqual(result['stage'],stage);self.assertEqual(path.read_bytes(),original)
                self.assertFalse((grid/'study_watch_state.json').exists())

    def test_tick_exception_and_supervisor_failure_stop_with_private_error_type(self):
        with self.temporary() as temporary:
            grid,state,_=fixture(Path(temporary))
            result,_,owners,_,_=self.run_watch(grid,state,[RuntimeError('PRIVATE-DO-NOT-SERIALIZE')])
            self.assertEqual(result['stop_reason'],'watch_error');self.assertEqual(owners[0].calls,1)
            self.assertNotIn('PRIVATE-DO-NOT-SERIALIZE',(grid/'study_watch_state.json').read_text())
        with self.temporary() as temporary:
            grid,state,_=fixture(Path(temporary))
            def failed(_):raise RuntimeError('Local failure')
            result,_,owners,_,_=self.run_watch(grid,state,[{'stage':'owned_call_running'}],regenerator=failed)
            self.assertEqual(result['stop_reason'],'local_supervisor_failed');self.assertEqual(owners[0].calls,1)

    def test_review_scope_change_stops_before_next_paid_gate(self):
        with self.temporary() as temporary:
            grid,state,_=fixture(Path(temporary));changed=[]
            def regenerate(_):
                if not changed:
                    value=core.read(grid/'reviewed_for_launch.json');value['new_field']='scope changed';core.write(grid/'reviewed_for_launch.json',value);changed.append(1)
            result,_,owners,_,_=self.run_watch(grid,state,[{'stage':'owned_call_running'}],regenerator=regenerate)
            self.assertEqual(result['stop_reason'],'frozen_scope_or_runner_changed');self.assertEqual(owners[0].calls,1)

    def test_unapproved_expansion_beyond_twelve_jobs_is_blocked_before_first_tick(self):
        with self.temporary() as temporary:
            grid,state,_=fixture(Path(temporary),budgets=(32768,65536,131072))
            result,_,owners,_,_=self.run_watch(grid,state,[{'stage':'spawned'}])
            self.assertEqual(result['stop_reason'],'watch_error');self.assertEqual(result['approved_jobs'],18)
            self.assertEqual(owners[0].calls,0);self.assertFalse((state/'study_watch.lock').exists())

    def test_transient_local_state_lock_retries_persistence_only(self):
        with self.temporary() as temporary:
            target=Path(temporary)/'state.json';original=core.write;attempts=[]
            def locked(path,value):
                attempts.append(path)
                if len(attempts)==1:raise PermissionError('Invented sync lock')
                return original(path,value)
            with patch.object(core,'write',locked),patch.object(watch.time,'sleep') as pause:
                watch.write_state(target,{'stage':'saved'})
            self.assertEqual(len(attempts),2);pause.assert_called_once_with(.05)
            self.assertEqual(core.read(target),{'stage':'saved'})

    def test_progress_counters_regenerate_even_when_core_stage_is_unchanged(self):
        with self.temporary() as temporary:
            grid,state,_=fixture(Path(temporary))
            def progress(owner):
                core.write(owner.jobs[0]['folder_path']/'remote_status.json',{'stage':'training','updates':owner.calls,'total_updates':32})
            result,_,owners,regenerations,_=self.run_watch(grid,state,[{'stage':'owned_call_running'}],on_tick=progress)
            self.assertEqual(owners[0].calls,3)
            self.assertEqual(len(regenerations),4)
            self.assertEqual(result['current']['counters'][0]['progress']['updates'],3)


if __name__=='__main__':unittest.main()
