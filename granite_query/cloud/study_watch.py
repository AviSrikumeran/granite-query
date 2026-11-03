"""Bounded local watcher for one reviewed grid; not started by import.

No GitHub publishing, teacher, endpoint or official-test work is included. Every
paid decision remains inside StudyRunner. A deadline stops new iterations; an
in-flight tick retains the core's finite provider/subprocess timeouts.
"""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from cloud import study_runner as core
from cloud.funding_watch import process_identity

ERROR_STAGES={'awaiting_valid_root_review_or_immutable_sources','budget_refresh_blocked',
    'app_monitoring_blocked','phase_allocation_blocked','awaiting_prepared_grid'}
CONTINUE_STAGES={'spawned','owned_call_running','waiting_for_tick_or_budget_lock','waiting_for_budget_lock',
    'waiting_for_gpu_launch_lock','waiting_for_outside_modal_task','waiting_for_protected_phase_funding'}


def timestamp():return datetime.now(timezone.utc).isoformat()


def write_state(path,value):
    # OneDrive can briefly lock an existing destination. Retry local persistence
    # only, never the completed core tick or its possible paid dispatch.
    for attempt in range(4):
        try:core.write(path,value);return
        except PermissionError:
            if attempt==3:raise
            time.sleep(.05*(2**attempt))


def existing_owner(path,identity_fn):
    """Never remove another watcher's lock, including a confirmed stale one."""
    try:
        owner=core.read(path);pid=int(owner['watcher_pid']);identity=identity_fn(pid)
    except Exception:return {'stage':'unverifiable_watch_lock_requires_review'}
    if identity.get('alive') and identity.get('created_at_utc')==owner.get('created_at_utc'):
        return {'stage':'another_watch_running','watcher_pid':pid}
    return {'stage':'stale_watch_lock_requires_review','watcher_pid':pid}


def counters(jobs):
    values=[]
    for job in jobs:
        folder=job['folder_path'];item={'run_id':job['run_id']}
        terminal=folder/'study_terminal.json';launch=folder/'launch.json';remote=folder/'remote_status.json'
        if terminal.exists():item['terminal_kind']=core.read(terminal)['kind']
        if launch.exists():item['call_id']=core.read(launch).get('call_id')
        if remote.exists():
            status=core.read(remote)
            # Omit wall clock and arbitrary error text: unchanged work stays quiet.
            item['progress']={key:status[key] for key in ('stage','updates','total_updates',
                'supervised_tokens','completed','total') if key in status}
        values.append(item)
    return values


def regenerate(grid):
    result=subprocess.run([sys.executable,str(ROOT/'supervisor.py')],cwd=ROOT.parent,capture_output=True,
        env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1'),timeout=60)
    (grid/'study_watch_supervisor.stdout.private.log').write_bytes(result.stdout)
    (grid/'study_watch_supervisor.stderr.private.log').write_bytes(result.stderr)
    if result.returncode:raise RuntimeError('Local supervisor regeneration failed; inspect private logs')


def watch(grid,*,review=None,state_dir=None,interval_seconds=45,max_seconds=7200,
          runner_factory=core.StudyRunner,identity_fn=process_identity,clock=time.monotonic,
          sleep=time.sleep,regenerator=regenerate,journal=None):
    if not 30<=interval_seconds<=60 or not 1<=max_seconds<=7200:
        raise ValueError('Watch interval must be 30–60 seconds and runtime at most 7200 seconds')
    grid=Path(grid).resolve();state_dir=Path(state_dir or ROOT/'runs/supervisor').resolve()
    if not grid.is_relative_to((ROOT/'runs').resolve()) or not state_dir.is_relative_to((ROOT/'runs').resolve()):
        raise ValueError('Watcher state must remain under ignored cloud/runs')
    state_dir.mkdir(parents=True,exist_ok=True);lock=state_dir/'study_watch.lock'
    try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:return existing_owner(lock,identity_fn)
    claimed_file=os.fstat(fd)
    pid=os.getpid();lease=None;started=clock();state=None;regeneration_failed=False
    if journal is None:
        from cloud.progress import record
        journal=lambda kind,title,detail,key:record(kind,title,detail,key)

    def save(**changes):
        state.update(changes,updated_at_utc=timestamp(),elapsed_seconds=round(clock()-started,3))
        write_state(grid/'study_watch_state.json',state)

    try:
        identity=identity_fn(pid)
        if not identity.get('alive'):raise ValueError('Cannot establish this watcher process identity')
        lease={'watcher_pid':pid,'created_at_utc':identity['created_at_utc'],'lease_id':uuid.uuid4().hex,
            'grid':str(grid),'started_at_utc':timestamp()}
        os.write(fd,json.dumps(lease).encode());os.fsync(fd)
        if grid.is_dir():
            state={'schema_version':1,'stage':'starting','watcher_pid':pid,'lease_id':lease['lease_id'],
                'started_at_utc':lease['started_at_utc'],'iterations':0,'regenerations':0,
                'interval_seconds':interval_seconds,'maximum_seconds':max_seconds,'phase':'validating_root_review'}
            save()
        runner=runner_factory(grid,review=review,state_dir=state_dir)
        runner.jobs=[];runner.load();approval=runner.review()
        approved=[job for job in runner.jobs if job['token_budget'] in approval['approved_token_budgets']]
        if state is not None:save(approved_jobs=len(approved))
        if not 1<=len(approved)<=12:raise ValueError('This watcher is limited to at most12 explicitly approved study jobs')
        scope={'grid_sha256':core.sha(grid/'grid_manifest.json'),'review_sha256':core.sha(runner.review_path),
            'core_runner_sha256':core.sha(Path(core.__file__)),'watch_source_sha256':core.sha(Path(__file__)),
            'approved_run_ids':[job['run_id'] for job in approved]}
        state={'schema_version':1,'stage':'watching','watcher_pid':pid,'lease_id':lease['lease_id'],
            'started_at_utc':lease['started_at_utc'],'scope':scope,'interval_seconds':interval_seconds,
            'maximum_seconds':max_seconds,'iterations':0,'regenerations':0,'protected_modal_usd':5,
            'deadline_policy':'No new tick after deadline; an in-flight tick keeps the core operation timeouts.',
            'github_publishing':False,'teacher_or_test_or_endpoint_work':False}
        save()
        journal('in_progress','Bounded reviewed study watcher started',
            'A local bounded watcher advances only the approved grid through the reviewed one-tick runner. Paid gates and global GPU/budget locks remain in that runner. Local reports regenerate on meaningful changes; public synchronization remains scheduled separately.',
            grid.name+'-study-watch-start-'+lease['lease_id'])
        previous=None;reason='maximum_runtime_reached'
        while clock()-started<max_seconds:
            if (core.sha(grid/'grid_manifest.json')!=scope['grid_sha256']
                    or core.sha(runner.review_path)!=scope['review_sha256']
                    or core.sha(Path(core.__file__))!=scope['core_runner_sha256']
                    or core.sha(Path(__file__))!=scope['watch_source_sha256']):
                reason='frozen_scope_or_runner_changed';break
            result=runner.tick(advance=True)
            current={'result':result,'counters':counters(approved)}
            # Deliberately include state and counters, never elapsed-time changes.
            changed=json.dumps(current,sort_keys=True)!=previous
            save(iterations=state['iterations']+1,current=current)
            if changed:
                try:regenerator(grid)
                except Exception:
                    regeneration_failed=True;reason='local_supervisor_failed';break
                save(regenerations=state['regenerations']+1)
                previous=json.dumps(current,sort_keys=True)
            stage=result.get('stage','unknown')
            if stage=='approved_grid_completed':reason=stage;break
            if stage.startswith('action_required') or stage in ERROR_STAGES:
                reason=stage;break
            if stage not in CONTINUE_STAGES:
                reason='unexpected_core_status';break
            remaining=max_seconds-(clock()-started)
            if remaining<=0:break
            sleep(min(interval_seconds,remaining))
        save(stage='stopped',stop_reason=reason,stopped_at_utc=timestamp())
        kind='completed' if reason=='approved_grid_completed' else ('in_progress' if reason=='maximum_runtime_reached' else 'failed')
        journal(kind,'Bounded study watcher stopped',
            'The local watcher stopped: '+reason.replace('_',' ')+'. Existing detached calls are preserved. No watcher was restarted, no endpoint deployed and no extra protocol approved.',
            grid.name+'-study-watch-stop-'+lease['lease_id'])
        if not regeneration_failed:
            try:regenerator(grid);save(regenerations=state['regenerations']+1)
            except Exception:save(final_regeneration_error=True)
        return state
    except Exception as error:
        # Never serialize provider bodies, credentials, environment or exception text.
        if state is not None:
            save(stage='stopped',stop_reason='watch_error',error_type=type(error).__name__,stopped_at_utc=timestamp())
            journal('failed','Bounded study watcher stopped on an error',
                'The local watcher stopped safely; inspect its private state and existing call receipts before further work.',
                grid.name+'-study-watch-error-'+lease['lease_id'])
            try:regenerator(grid)
            except Exception:pass
            return state
        return {'stage':'watch_start_blocked','error_type':type(error).__name__,'watcher_pid':pid}
    finally:
        os.close(fd)
        if lease is not None:
            try:
                if core.read(lock)==lease:lock.unlink()
            except (OSError,ValueError):pass
        else:
            # Identity failed before the lease was written. Remove only this
            # still-empty exclusive file, never a populated/replaced owner lock.
            try:
                current=lock.stat()
                if current.st_size==0 and (current.st_dev,current.st_ino)==(claimed_file.st_dev,claimed_file.st_ino):lock.unlink()
            except OSError:pass


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--grid',type=Path,required=True);parser.add_argument('--review',type=Path)
    parser.add_argument('--interval-seconds',type=int,default=45);parser.add_argument('--max-seconds',type=int,default=7200)
    args=parser.parse_args()
    result=watch(args.grid,review=args.review,interval_seconds=args.interval_seconds,max_seconds=args.max_seconds)
    print(json.dumps({key:result.get(key) for key in ('stage','stop_reason','watcher_pid','iterations')}),flush=True)
