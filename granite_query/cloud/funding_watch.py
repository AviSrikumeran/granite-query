"""Bounded, read-only provider refreshes for one already funded teacher collector.

This watcher never generates model responses, reserves money, restarts a
collector or launches a GPU. Private run state records its own PID and outcomes.
"""
import argparse
import ctypes
from datetime import datetime,timedelta,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent
STATE=ROOT/'runs/supervisor'
sys.path.insert(0,str(ROOT.parent))
from cloud.budget_reconcile import utc
from cloud.deepseek_reconcile import require_fresh_deepseek_budget
from cloud.matched_teacher import _write
from cloud.progress import record


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def process_identity(pid):
    """Query only liveness/creation time; never signal or terminate a process."""
    if os.name!='nt':
        raise RuntimeError('This local collector watcher requires Windows process identity')
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype=wintypes.BOOL
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE,*[ctypes.POINTER(wintypes.FILETIME)]*4]
    kernel.GetProcessTimes.restype=wintypes.BOOL
    handle=kernel.OpenProcess(0x1000,False,int(pid))
    if not handle:
        code=ctypes.get_last_error()
        if code in (87,1168):
            return {'alive':False,'created_at_utc':None}
        raise RuntimeError('Collector process identity unavailable; Windows error '+str(code))
    try:
        exit_code=wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle,ctypes.byref(exit_code)):
            raise RuntimeError('Collector liveness query failed')
        created,exited,kernel_time,user_time=[wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle,ctypes.byref(created),ctypes.byref(exited),ctypes.byref(kernel_time),ctypes.byref(user_time)):
            raise RuntimeError('Collector creation-time query failed')
        ticks=(created.dwHighDateTime<<32)|created.dwLowDateTime
        start=datetime.fromtimestamp((ticks-116444736000000000)/10000000,tz=timezone.utc).isoformat()
        return {'alive':exit_code.value==259,'created_at_utc':start}
    finally:
        kernel.CloseHandle(handle)


def collector_state(folder,*,identity_fn=process_identity,expected_pid=None,expected_created=None):
    summary=read(folder/'teacher_summary.json') if (folder/'teacher_summary.json').exists() else {}
    result={'stage':summary.get('stage','starting'),'completed':summary.get('completed',0),
        'requested':summary.get('requested',0)}
    if result['stage'] in ('completed','halted'):
        return dict(result,stop_reason='collector_'+result['stage'])
    lock=folder/'collector.lock'
    if not lock.exists():
        return dict(result,stop_reason='collector_lock_released')
    pid=int(lock.read_text(encoding='ascii').strip())
    if expected_pid is not None and pid!=expected_pid:
        return dict(result,stop_reason='collector_owner_changed')
    identity=identity_fn(pid)
    if not identity['alive']:
        return dict(result,stop_reason='collector_process_terminated')
    if expected_created is not None and identity['created_at_utc']!=expected_created:
        return dict(result,stop_reason='collector_pid_reused')
    return dict(result,stop_reason=None,pid=pid,created_at_utc=identity['created_at_utc'])


def refresh_once(state_dir,job_id,reserved_usd,*,runner=subprocess.run,sleep=time.sleep,attempts=4):
    """Retry only local ledger-lock contention, never provider/auth failures."""
    env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1')
    for attempt in range(attempts):
        if (state_dir/'budget_reconcile.lock').exists():
            if attempt+1<attempts:
                sleep(.5)
                continue
            return {'status':'budget_busy','failure_kind':None}
        try:
            run=runner([sys.executable,'-m','cloud.deepseek_reconcile','--refresh'],
                cwd=str(ROOT.parent),capture_output=True,text=True,encoding='utf-8',
                env=env,timeout=60)
        except subprocess.TimeoutExpired:
            return {'status':'failed','failure_kind':'provider_refresh_timeout'}
        if run.returncode:
            # A race acquiring the same local lock can happen after precheck.
            local_lock_error=('FileExistsError' in run.stderr and 'budget_reconcile.lock' in run.stderr)
            if local_lock_error:
                if attempt+1<attempts:
                    sleep(.5)
                    continue
                return {'status':'budget_busy','failure_kind':None}
            return {'status':'failed','failure_kind':'provider_refresh_failed','return_code':run.returncode}
        ledger=read(state_dir/'budget.json')
        jobs=[job for job in ledger['jobs'] if job.get('run_id')==job_id and job.get('service')=='deepseek']
        if len(jobs)!=1 or jobs[0].get('reserved_usd')!=reserved_usd:
            return {'status':'failed','failure_kind':'reservation_changed'}
        try:
            require_fresh_deepseek_budget(ledger)
        except (ValueError,RuntimeError):
            return {'status':'failed','failure_kind':'funding_or_account_guard'}
        account=ledger.get('deepseek_budget_accounting',{})
        if account.get('status')!='conditional_wallet_inference' or account.get('issues'):
            return {'status':'failed','failure_kind':'funding_ambiguity'}
        return {'status':'refreshed','failure_kind':None,
            'queried_at_utc':ledger['deepseek_wallet_observation']['queried_at_utc']}
    raise AssertionError('Unreachable refresh loop')


def watch(folder,*,interval_seconds=300,max_seconds=7200,identity_fn=process_identity,
          refresh_fn=refresh_once,sleep=time.sleep,clock=time.monotonic):
    folder=Path(folder).resolve()
    if not folder.is_relative_to((ROOT/'runs').resolve()):
        raise ValueError('Watcher artifacts must remain under ignored cloud/runs')
    if not 30<=interval_seconds<=300 or not 1<=max_seconds<=7200:
        raise ValueError('Refresh at most every five minutes and stop within two hours')
    state_dir=STATE
    if not (state_dir/'deepseek_funding_baseline.json').exists():
        raise RuntimeError('An existing documented funding baseline is required')
    plan=read(folder/'plan.json')
    plan_hash=hashlib.sha256((folder/'plan.json').read_bytes()).hexdigest()
    job_id=plan['budget_job_id']; allowance=plan['reserved_usd_required']
    first=collector_state(folder,identity_fn=identity_fn)
    if first.get('stop_reason'):
        # A completed/terminated collector needs no background process or refresh.
        result=dict(stage='stopped',stop_reason=first['stop_reason'],collector=first,stopped_at_utc=timestamp())
        _write(folder/'funding_watch_state.json',result)
        return result
    launch=read(folder/'launch.json')
    if first['pid']!=launch.get('worker_pid',launch.get('pid')):
        raise RuntimeError('Collector lock does not match its saved launch owner')
    lock=folder/'funding_watch.lock'
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    started=clock(); pid=os.getpid(); busy_cycles=0
    state={'schema_version':1,'run_id':folder.name,'watcher_pid':pid,'collector_pid':first['pid'],
        'collector_created_at_utc':first['created_at_utc'],'started_at_utc':timestamp(),
        'stage':'starting','interval_seconds':interval_seconds,'maximum_seconds':max_seconds,
        'refresh_count':0,'local_lock_skips':0,'reservation_amount_unchanged':allowance,
        'paid_generation_launched':False,'gpu_launched':False}

    def save(event,**details):
        state.update(details,updated_at_utc=timestamp())
        _write(folder/'funding_watch_state.json',state)
        with (folder/'funding_watch.events.jsonl').open('a',encoding='utf-8') as handle:
            handle.write(json.dumps(dict(event=event,at_utc=timestamp(),**details))+'\n')
            handle.flush();os.fsync(handle.fileno())

    try:
        os.write(fd,json.dumps({'watcher_pid':pid,'collector_pid':first['pid'],'started_at_utc':state['started_at_utc']}).encode())
        os.fsync(fd)
        save('started')
        record('in_progress','Bounded teacher funding watcher started',
            'A local watcher refreshes only the supported balance observation every five minutes while the existing teacher collector is active. It creates no paid generations or GPU work, preserves the reservation, and stops on collector termination, account ambiguity, provider failure or its two-hour limit.',folder.name+'-funding-watch-started')
        next_refresh=started
        while True:
            observed=collector_state(folder,identity_fn=identity_fn,expected_pid=first['pid'],expected_created=first['created_at_utc'])
            reason=observed.get('stop_reason')
            if reason:
                break
            if clock()-started>=max_seconds:
                reason='maximum_runtime_reached';break
            if hashlib.sha256((folder/'plan.json').read_bytes()).hexdigest()!=plan_hash:
                reason='collector_plan_changed';break
            if clock()>=next_refresh:
                refreshed=refresh_fn(state_dir,job_id,allowance)
                if refreshed['status']=='failed':
                    reason=refreshed['failure_kind'];save('refresh_failed',failure_kind=reason);break
                if refreshed['status']=='budget_busy':
                    busy_cycles+=1
                    save('local_lock_skipped',stage='waiting_for_local_budget_lock',local_lock_skips=state['local_lock_skips']+1)
                    if busy_cycles>=3:
                        reason='local_budget_lock_persisted';break
                else:
                    busy_cycles=0
                    save('refreshed',stage='watching',refresh_count=state['refresh_count']+1,
                        last_refresh_at_utc=refreshed['queried_at_utc'],collector=observed)
                next_refresh=clock()+interval_seconds
            sleep(min(10,max(.01,next_refresh-clock()),max(.01,max_seconds-(clock()-started))))
        save('stopped',stage='stopped',stop_reason=reason,collector=observed,stopped_at_utc=timestamp())
        record('completed' if reason=='collector_completed' else 'failed','Teacher funding watcher stopped',
            'The bounded local watcher stopped: '+reason.replace('_',' ')+'. No collector was killed or restarted and no reservation was increased. Inspect durable collector state before any paid resumption.',folder.name+'-funding-watch-'+reason)
        return state
    except Exception as error:
        save('stopped',stage='stopped',stop_reason='watcher_failure',error_type=type(error).__name__,stopped_at_utc=timestamp())
        record('failed','Teacher funding watcher failed','The unpaid funding watcher stopped safely; inspect its private durable state. The collector and frozen requests were not changed.',folder.name+'-funding-watch-failed')
        raise
    finally:
        os.close(fd)
        lock.unlink()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',type=Path,required=True)
    parser.add_argument('--interval-seconds',type=int,default=300)
    parser.add_argument('--max-seconds',type=int,default=7200)
    args=parser.parse_args()
    result=watch(args.folder,interval_seconds=args.interval_seconds,max_seconds=args.max_seconds)
    print(json.dumps({'stage':result['stage'],'stop_reason':result['stop_reason']}),flush=True)
