"""Reviewed local transport repair; frozen model/protocol sources never change.

Only a positively reconciled, never-transmitted existing claim may delegate
its obsolete host owner to a new actual process. Unknown transmission is never
retried. Future fresh claims use the correct frozen V4 CLI from the start.
"""
from datetime import datetime,timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from cloud import native_reasoning_batch_control_v4 as control
from cloud import modal_native_batch_launch_v4 as frozen_cli

VERSION='native-v4-reviewed-local-transport-v1'
NORMAL_CLI='cloud.modal_native_batch_launch_v4'
REPAIR_CLI='cloud.modal_native_v4_transport_launch::repair_launch'
STATE=control.STATE
PROVIDER_PROOF=STATE/'native_v4_wrong_route_provider_reconciliation.json'
HOST_PROOF=STATE/'native_v4_wrong_route_host_exit.json'
ADVANCE_PROOF=STATE/'native_v4_baseline_advance_process.json'
PROCESS_PROOF=STATE/'native_v4_baseline_host_process.json'
SOURCES=('native_v4_transport.py','modal_native_v4_transport_launch.py')


def source_hashes():return {name:control.sha(control.ROOT/name) for name in SOURCES}


def launch_args(folder,*,repair=False):
    return [sys.executable,'-m','modal','run','--detach','-m',REPAIR_CLI if repair else NORMAL_CLI,'--folder',str(control.safe(folder))]


def _bytes(path,limit=4*1024*1024):
    path=control.safe(path)
    if not path.is_file() or not 0<path.stat().st_size<=limit:raise ValueError('Bounded original evidence required')
    return path.read_bytes()


def _immutable_bytes(path,raw):
    path=control.safe(path);path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with path.open('xb') as h:h.write(raw);h.flush();os.fsync(h.fileno())
    except FileExistsError:
        if path.read_bytes()!=raw:raise ValueError('Immutable transport artifact differs')


def _original(output):
    output=control.safe(output);jobs=control.load_jobs(output);job=jobs[0];folder=job['folder_path']
    dispatch=control.Controller(output)._dispatch(job);owner=control.read(folder/'controller_owner.json')
    receipt=control.read(folder/'launch_receipt.private.json');error=_bytes(folder/'launch.stderr.private.log')
    _bytes(folder/'launch.stdout.private.log')
    if (job['role']!='baseline' or owner.get('claim_id')!=dispatch['claim_id'] or type(owner.get('pid')) is not int
            or type(receipt.get('return_code')) is not int or receipt['return_code']!=1
            or 'cloud.modal_native_launch_v3' not in control.ROOT.joinpath('native_reasoning_batch_control_v4.py').read_text(encoding='utf-8')
            or b'modal_native_launch_v3.py' not in error or b'preflight' not in error
            or b'Native study design or frozen sources changed' not in error):
        raise ValueError('Exact known wrong-route pre-spawn evidence required')
    return job,dispatch,owner,receipt


def review_template(output=control.DEFAULT,*,provider_path=PROVIDER_PROOF,host_path=HOST_PROOF,advance_path=ADVANCE_PROOF,process_path=PROCESS_PROOF):
    output=control.safe(output);job,dispatch,owner,receipt=_original(output);folder=job['folder_path']
    provider_path,host_path=control.safe(provider_path),control.safe(host_path)
    advance_path,process_path=control.safe(advance_path),control.safe(process_path)
    provider,host,advance,process=control.read(provider_path),control.read(host_path),control.read(advance_path),control.read(process_path)
    stamp=lambda value:datetime.fromisoformat(value.replace('Z','+00:00'))
    if (advance.get('action')!='advance_baseline_once' or advance.get('actual_python_pid')!=owner['pid']
            or type(advance.get('actual_python_pid')) is not int or advance.get('run_id')!=output.name
            or advance.get('design_sha256')!=control.sha(output/'design.json')
            or advance.get('manifest_sha256')!=control.sha(output/'study_manifest.json')
            or process.get('pid')!=owner['pid'] or type(process.get('parent_pid')) is not int
            or process.get('parent_pid')!=host.get('original_venv_launcher',{}).get('pid')
            or stamp(advance['creation_utc'])!=stamp(process['creation_utc'])
            or stamp(process['creation_utc'])!=stamp(host['original_controller']['creation_utc'])
            or host.get('queried_pids')!=[owner['pid'],process['parent_pid']]
            or not {'actual_remote_owner','actual_remote_progress'}<=provider.keys()
            or provider.get('run_id')!=job['run_id'] or provider.get('actual_remote_owner') is not None
            or provider.get('actual_remote_progress') is not None or provider.get('volume')!={'exists':False,'provider_exception':'NotFoundError'}
            or provider.get('failed_cli_receipt')!=receipt
            or host.get('provider_reconciliation_sha256')!=control.sha(provider_path)
            or host.get('original_controller',{}).get('pid')!=owner['pid']
            or not isinstance(host['original_controller'].get('creation_utc'),str)
            or host.get('observed_processes')!=[] or host.get('both_queried_pids_absent') is not True
            or host.get('modal_cli_child_pid_not_recorded') is not True
            or host.get('original_venv_launcher',{}).get('creation_time_was_not_captured') is not True
            or host['original_venv_launcher'].get('creation_utc') is not None):
        raise ValueError('Typed original positive provider/host reconciliation required')
    _zero_apps(provider.get('apps'))
    return {'version':VERSION,'reviewed':False,'phase':'never_transmitted_transport_delegation',
        'transport_source_sha256':source_hashes(),'frozen_source_sha256':control.verify_design(output)['source_sha256'],
        'design_sha256':control.sha(output/'design.json'),'manifest_sha256':control.sha(output/'study_manifest.json'),
        'funding_sha256':control.sha(output/'funding.json'),'dispatch_sha256':control.sha(folder/'dispatch.json'),
        'claim_id':dispatch['claim_id'],'original_owner_sha256':control.sha(folder/'controller_owner.json'),
        'original_owner_pid':owner['pid'],'original_venv_launcher_pid':host['original_venv_launcher']['pid'],
        'original_modal_cli_pid_recorded':False,'wrong_cli_receipt_sha256':control.sha(folder/'launch_receipt.private.json'),
        'wrong_cli_stdout_sha256':control.sha(folder/'launch.stdout.private.log'),'wrong_cli_stderr_sha256':control.sha(folder/'launch.stderr.private.log'),
        'provider_proof_path':str(provider_path),'provider_proof_sha256':control.sha(provider_path),
        'host_proof_path':str(host_path),'host_proof_sha256':control.sha(host_path),
        'advance_proof_path':str(advance_path),'advance_proof_sha256':control.sha(advance_path),
        'process_proof_path':str(process_path),'process_proof_sha256':control.sha(process_path),
        'normal_cli':NORMAL_CLI,'repair_cli':REPAIR_CLI,'same_dispatch_and_allowance':True,
        'new_reservation_created':False,'allowance_usd':1.75,'automatic_retries':0,'fresh_evidence_max_age_seconds':120}


def validate_transport_review(output=control.DEFAULT):
    output=control.safe(output);r=control.read(output/'transport_review.json')
    expected=dict(review_template(output,provider_path=r['provider_proof_path'],host_path=r['host_proof_path'],
        advance_path=r['advance_proof_path'],process_path=r['process_proof_path']),reviewed=True)
    if r!=expected or r.get('reviewed') is not True or r.get('same_dispatch_and_allowance') is not True or r.get('new_reservation_created') is not False:
        raise ValueError('Exact independent transport/source/delegation review required')
    return r


def _zero_apps(apps,*,own_app_id=None):
    if own_app_id is not None and not re.fullmatch(r'ap-[A-Za-z0-9]+',str(own_app_id)):
        raise ValueError('Supported exact current app identity required')
    if not isinstance(apps,list) or any(not isinstance(a,dict) or type(a.get('tasks')) not in (int,str)
            or not str(a['tasks']).isdigit() or int(a['tasks'])!=0
            or (a.get('state')!='stopped' and (own_app_id is None or a.get('app_id')!=own_app_id or not isinstance(a.get('state'),str) or not a['state'])) for a in apps):
        raise ValueError('Supported all-stopped zero-task inventory required')


def process_identity(pid):
    if type(pid) is not int or pid<=0:raise ValueError('Positive process identity required')
    script=f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}'; if($p){{[pscustomobject]@{{pid=[int]$p.ProcessId;creation_utc=$p.CreationDate.ToUniversalTime().ToString('o');parent_pid=[int]$p.ParentProcessId;executable_path=[string]$p.ExecutablePath}} | ConvertTo-Json -Compress}}"
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],capture_output=True,check=True,timeout=20)
    raw=result.stdout.decode('utf-8-sig').strip()
    if not raw:return None
    value=json.loads(raw)
    if value.get('pid')!=pid or not isinstance(value.get('creation_utc'),str) or not isinstance(value.get('executable_path'),str) or not value['executable_path']:
        raise ValueError('Actual process creation identity unavailable')
    return value


def validate_cli_ancestry(driver,cli,redirector,launcher_executable):
    """Pure exact direct or one known Windows venv-redirector ancestry."""
    def stamp(value):
        if not isinstance(value,dict) or type(value.get('pid')) is not int or type(value.get('parent_pid')) is not int:
            raise ValueError('Actual bounded process identity required')
        result=datetime.fromisoformat(value['creation_utc'].replace('Z','+00:00'))
        if result.tzinfo is None:raise ValueError('Actual zoned process creation required')
        return result
    born_driver,born_cli=stamp(driver),stamp(cli)
    if driver['pid']==cli['pid'] or born_cli<born_driver:raise ValueError('CLI must be a new real child identity')
    if cli['parent_pid']==driver['pid']:
        if redirector is not None:raise ValueError('Unexpected extra process in direct ancestry')
        depth=1
    else:
        born_redirector=stamp(redirector)
        if (cli['parent_pid']!=redirector['pid'] or redirector['parent_pid']!=driver['pid']
                or not born_driver<=born_redirector<=born_cli
                or os.path.normcase(os.path.abspath(redirector.get('executable_path','')))!=os.path.normcase(os.path.abspath(launcher_executable))):
            raise ValueError('Only the exact current venv launcher may bridge driver and CLI')
        depth=2
    return {'depth':depth,'driver':driver,'cli':cli,'redirector':redirector,'launcher_executable':launcher_executable}


def observe_cli_ancestry(delegation):
    cli=process_identity(os.getpid())
    if cli is None:raise ValueError('Current actual CLI identity missing')
    redirector=None if cli['parent_pid']==delegation['new_driver']['pid'] else process_identity(cli['parent_pid'])
    return validate_cli_ancestry(delegation['new_driver'],cli,redirector,delegation['launcher_executable'])


class TransportBackend(control.Backend):
    def launch(self,folder):
        validate_transport_review(control.safe(folder).parents[1])
        return self.run_cli(folder,repair=False)
    def run_cli(self,folder,*,repair):
        folder=control.safe(folder);prefix='transport.repair' if repair else 'transport.launch'
        try:
            result=subprocess.run(launch_args(folder,repair=repair),cwd=control.ROOT.parent,capture_output=True,timeout=210,
                env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1',MODAL_IMAGE_BUILDER_VERSION='2025.06'))
            out,err,code=result.stdout,result.stderr,result.returncode
        except subprocess.TimeoutExpired as exc:out,err,code=exc.stdout or b'',exc.stderr or b'',None
        _immutable_bytes(folder/(prefix+'.stdout.private.log'),out or b'\n')
        _immutable_bytes(folder/(prefix+'.stderr.private.log'),err or b'\n')
        app=re.search(rb'ap-[A-Za-z0-9]+',out+b'\n'+err)
        return {'return_code':code,'app_id':app.group().decode() if app else None,'transport_version':VERSION,
            'module':REPAIR_CLI if repair else NORMAL_CLI,'transport_source_sha256':source_hashes()}
    def absence(self,run_id,old_pids):
        import modal
        state=modal.Dict.from_name('granite-query-training-progress')
        owner=state.get('native-reasoning-owner:'+run_id,None);progress=state.get(run_id,None)
        try:
            list(modal.Volume.from_name('granite-query-training-artifacts').iterdir(run_id,recursive=False))
            volume={'exists':True,'provider_exception':None}
        except modal.exception.NotFoundError:volume={'exists':False,'provider_exception':'NotFoundError'}
        return {'run_id':run_id,'observed_at_utc':control.now(),'actual_remote_owner':owner,'actual_remote_progress':progress,
            'volume':volume,'apps':self.apps(),'old_processes':[process_identity(pid) for pid in old_pids]}


def _fresh_absence(evidence,job,*,own_app_id=None):
    stamp=datetime.fromisoformat(evidence['observed_at_utc'].replace('Z','+00:00'))
    age=(datetime.now(timezone.utc)-stamp).total_seconds()
    if (stamp.tzinfo is None or not 0<=age<=120 or not {'actual_remote_owner','actual_remote_progress'}<=evidence.keys()
            or evidence.get('run_id')!=job['run_id']
            or evidence.get('actual_remote_owner') is not None or evidence.get('actual_remote_progress') is not None
            or evidence.get('volume')!={'exists':False,'provider_exception':'NotFoundError'}
            or evidence.get('old_processes')!=[None,None]):raise ValueError('Fresh positive never-transmitted reconciliation required')
    _zero_apps(evidence.get('apps'),own_app_id=own_app_id)


def delegated_preflight(folder):
    """Same frozen launch checks, with one explicit reviewed live owner delegation."""
    folder=control.safe(folder);output=folder.parents[1];r=validate_transport_review(output)
    jobs=control.load_jobs(output);job=next(j for j in jobs if j['folder_path']==folder)
    dispatch=control.Controller(output)._dispatch(job);original=control.read(folder/'controller_owner.json')
    delegation=control.read(folder/'transport_delegation.json');intent=control.read(folder/'transport_repair_intent.json')
    live=process_identity(delegation['new_driver']['pid']);lease=control.safe(control.STATE/'gpu_launch.lock')
    if (delegation.get('version')!=VERSION or delegation.get('original_owner_sha256')!=control.sha(folder/'controller_owner.json')
            or original.get('claim_id')!=dispatch['claim_id'] or delegation.get('claim_id')!=dispatch['claim_id']
            or delegation.get('transport_review_sha256')!=control.sha(output/'transport_review.json')
            or not isinstance(live,dict) or live!=delegation.get('new_driver') or not lease.is_file() or lease.read_text()!=str(live['pid'])
            or intent.get('delegation_sha256')!=control.sha(folder/'transport_delegation.json')
            or intent.get('version')!=VERSION or intent.get('dispatch_sha256')!=control.sha(folder/'dispatch.json')
            or intent.get('transport_source_sha256')!=source_hashes()
            or intent.get('fresh_reconciliation_sha256')!=control.sha(folder/'transport_never_transmitted.json')
            or intent.get('original_failed_receipt_sha256')!=r['wrong_cli_receipt_sha256']):
        raise ValueError('Actual new driver identity/creation/lease and immutable claim delegation required')
    observe_cli_ancestry(delegation)
    _fresh_absence(control.read(folder/'transport_never_transmitted.json'),job)
    if any((folder/name).exists() for name in ('launch.json','cli_spawn_started.json','transport_cli_spawn_started.json')):
        raise ValueError('Known or unknown prior transmission; never retry')
    ledger=control.fresh_funding(control.read(control.STATE/'budget.json'));control.validate_stage_funding(output,ledger)
    entry=control._one(ledger,job['run_id'])
    if (entry.get('status')!='spawning' or entry.get('reserved_usd')!=1.75 or entry.get('native_claim_id')!=dispatch['claim_id']
            or entry.get('native_intent_sha256')!=dispatch['intent_sha256'] or entry.get('native_design_sha256')!=control.sha(output/'design.json')
            or any(j['run_id']!=job['run_id'] for j in control.active_jobs(ledger))
            or ledger['limits']['modal']-ledger['estimated_spend']['modal']-ledger['reserved']['modal']<5):
        raise ValueError('Same exact existing1.75 claim and protected funds required')
    review=control.review(output,'baseline')
    if job['role']!='baseline' or review.get('study_manifest_sha256')!=control.sha(output/'study_manifest.json'):
        raise ValueError('Only the reviewed never-transmitted baseline may delegate')
    frozen_cli.worker.validate_dispatch(job['data'],job['plan'],dispatch);frozen_cli.worker.verify_sources(dispatch['source_sha256'])
    return job,dispatch


def repair_existing(output=control.DEFAULT,*,backend=None):
    output=control.safe(output);r=validate_transport_review(output);backend=backend or TransportBackend()
    job,dispatch,owner,receipt=_original(output);folder=job['folder_path']
    with control.exclusive(control.STATE/'gpu_launch.lock'):
        if any((folder/n).exists() for n in ('launch.json','cli_spawn_started.json','transport_repair_intent.json','transport_cli_spawn_started.json')):
            raise ValueError('Existing repair/transmission must reconcile, never resend')
        identity=process_identity(os.getpid())
        if identity is None:raise ValueError('Actual current driver creation identity required')
        evidence=backend.absence(job['run_id'],[r['original_owner_pid'],r['original_venv_launcher_pid']]);_fresh_absence(evidence,job)
        # Check every immutable/current funding guard BEFORE one-shot intent.
        with control.exclusive(control.STATE/'budget_reconcile.lock'):
            ledger=control.fresh_funding(control.read(control.STATE/'budget.json'));control.validate_stage_funding(output,ledger)
            child=control._one(ledger,job['run_id'])
            if (child.get('status')!='spawning' or child.get('reserved_usd')!=1.75 or child.get('native_claim_id')!=dispatch['claim_id']
                    or child.get('native_intent_sha256')!=dispatch['intent_sha256']
                    or any(j['run_id']!=job['run_id'] for j in control.active_jobs(ledger))
                    or ledger['limits']['modal']-ledger['estimated_spend']['modal']-ledger['reserved']['modal']<5):
                raise ValueError('Existing same funded claim required before transport intent')
        control.write(folder/'transport_never_transmitted.json',evidence,immutable=True)
        delegation={'version':VERSION,'new_driver':identity,'launcher_executable':str(Path(sys.executable).absolute()),
            'original_owner_sha256':control.sha(folder/'controller_owner.json'),
            'claim_id':dispatch['claim_id'],'transport_review_sha256':control.sha(output/'transport_review.json')}
        control.write(folder/'transport_delegation.json',delegation,immutable=True)
        control.write(folder/'transport_repair_intent.json',{'version':VERSION,'created_at_utc':control.now(),
            'delegation_sha256':control.sha(folder/'transport_delegation.json'),'dispatch_sha256':control.sha(folder/'dispatch.json'),
            'fresh_reconciliation_sha256':control.sha(folder/'transport_never_transmitted.json'),
            'original_failed_receipt_sha256':r['wrong_cli_receipt_sha256'],'transport_source_sha256':source_hashes()},immutable=True)
        result=backend.run_cli(folder,repair=True);control.write(folder/'transport_repair_receipt.private.json',result,immutable=True)
        with control.exclusive(control.STATE/'budget_reconcile.lock'):
            ledger=control.read(control.STATE/'budget.json');child=control._one(ledger,job['run_id'])
            if child.get('native_claim_id')!=dispatch['claim_id'] or child.get('native_intent_sha256')!=dispatch['intent_sha256']:
                raise ValueError('Funded transport claim changed')
            if result.get('app_id'):child['app_id']=result['app_id']
            child['native_transport_receipt_sha256']=control.sha(folder/'transport_repair_receipt.private.json')
            if (folder/'launch.json').exists():
                launch=control.validate_launch(folder,job,dispatch,control.read(folder/'launch.json'))
                child.update(status='spawned',call_id=launch['call_id'])
            control.write(control.STATE/'budget.json',ledger)
        return {'stage':'transport_acknowledged' if (folder/'launch.json').exists() else 'transport_ambiguous_requires_reconciliation',
            'paid_work_launched':True if (folder/'launch.json').exists() else None,'new_reservation_created':False}


def safe_advance(output=control.DEFAULT,*,backend=None):
    validate_transport_review(output)
    return control.Controller(output,backend or TransportBackend()).advance()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',nargs='?',default='inspect',choices=('inspect','review-template','repair','advance','poll','calibrate'))
    p.add_argument('--run',type=Path,default=control.DEFAULT);a=p.parse_args()
    if a.action=='inspect':result=control.inspect(a.run)
    elif a.action=='review-template':result=review_template(a.run)
    elif a.action=='repair':result=repair_existing(a.run)
    elif a.action=='advance':result=safe_advance(a.run)
    else:validate_transport_review(a.run);result=getattr(control.Controller(a.run,TransportBackend()),a.action)()
    print(json.dumps(result,default=str))


if __name__=='__main__':main()
