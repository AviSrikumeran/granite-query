"""Single acknowledged native dispatch from an already held controller lease."""
import json
import os
from pathlib import Path
from cloud import native_reasoning_control_v2 as control
from cloud import modal_native_reasoning_v2 as worker

app=worker.app

def preflight(folder):
    folder=control.safe(folder);output=folder.parents[1]
    jobs=control.load_jobs(output)
    job=next(j for j in jobs if j['folder_path']==folder)
    owner=control.read(folder/'controller_owner.json')
    lease=control.safe(control.STATE/'gpu_launch.lock')
    if not lease.is_file() or lease.read_text()!=str(owner.get('pid')):
        raise ValueError('Parent controller must own the global GPU launch lease')
    dispatch=control.Controller(output)._dispatch(job)
    if owner.get('claim_id')!=dispatch['claim_id']:raise ValueError('Controller owner claim differs')
    if (folder/'launch.json').exists() or (folder/'cli_spawn_started.json').exists():
        raise ValueError('Already acknowledged or ambiguous transmission; never respawn')
    ledger=control.read(control.STATE/'budget.json');control.fresh_funding(ledger)
    control.validate_migration(output,ledger)
    entries=[j for j in ledger['jobs'] if j['run_id']==job['run_id']]
    if len(entries)!=1 or entries[0].get('service')!='modal':
        raise ValueError('One unique Modal funding child required')
    entry=entries[0]
    if (entry.get('status')!='spawning' or entry.get('reserved_usd')!=1.75
        or entry.get('native_claim_id')!=dispatch['claim_id']
        or entry.get('native_intent_sha256')!=dispatch['intent_sha256']
        or entry.get('native_design_sha256')!=control.sha(output/'design.json')):
        raise ValueError('Exact prebound native budget claim required')
    if any(j['run_id']!=job['run_id'] for j in control.active_jobs(ledger)):
        raise ValueError('Another active or unknown GPU liability blocks launch')
    if ledger['limits']['modal']-ledger['estimated_spend']['modal']-ledger['reserved']['modal']<5:
        raise ValueError('Final/API protection no longer fits')
    phase='baseline' if job['role']=='baseline' else 'pair'
    review=control.review(output,phase)
    if review.get('study_manifest_sha256')!=control.sha(output/'study_manifest.json'):
        raise ValueError('Phase review does not bind actual study plans')
    if phase=='pair':
        calibration=control.Controller(output).calibrate()
        if not calibration['pair_runtime_feasible'] or review.get('calibration_sha256')!=control.sha(output/'calibration.json'):
            raise ValueError('Pair requires actual measured baseline calibration')
    worker.validate_dispatch(job['data'],job['plan'],dispatch)
    worker.verify_sources(dispatch['source_sha256'])
    return job,dispatch

@app.local_entrypoint()
def launch(folder:str):
    job,dispatch=preflight(Path(folder));folder=job['folder_path']
    apps=control.Backend().apps()
    if any(type(a.get('tasks')) not in (int,str) or not str(a['tasks']).isdigit() or int(a['tasks'])>0 for a in apps):
        raise ValueError('Current Modal task inventory is active or unrecognized')
    control.write(folder/'cli_spawn_started.json',{'run_id':job['run_id'],'claim_id':dispatch['claim_id'],
        'intent_sha256':dispatch['intent_sha256'],'started_at_utc':control.now(),'cli_pid':os.getpid()},immutable=True)
    call=worker.execute.spawn(job['data'],job['plan'],dispatch)
    value={'run_id':job['run_id'],'claim_id':dispatch['claim_id'],'intent_sha256':dispatch['intent_sha256'],
        'call_id':call.object_id}
    control.write(folder/'launch.json',value,immutable=True)
    print(json.dumps(value),flush=True)
