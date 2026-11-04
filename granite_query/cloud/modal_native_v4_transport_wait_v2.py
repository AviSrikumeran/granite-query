"""Unique V2 local entrypoint; all heavy proof work precedes fresh live checks."""
from pathlib import Path
import json
import os
from cloud import native_v4_transport_wait_v2 as transport

app=transport.base.frozen_cli.app


@app.local_entrypoint()
def repair_launch_v2(folder:str):
    context=transport.delegated_preflight_v2(Path(folder));job,dispatch=context['job'],context['dispatch'];folder=job['folder_path']
    r=context['reviews']['base_review'];own_app_id=app.app_id
    evidence=transport.WaitBackend().absence(job['run_id'],[r['original_owner_pid'],r['original_venv_launcher_pid']])
    # No teacher/source rederivation occurs after this actual provider read.
    with transport.control.exclusive(transport.control.STATE/'budget_reconcile.lock'):
        ancestry=transport.final_guard(context,evidence,own_app_id=own_app_id)
        transport.control.write(folder/'transport_cli_reconciliation_v2.json',evidence,immutable=True)
        transport.control.write(folder/'transport_cli_process_ancestry_v2.json',ancestry,immutable=True)
        transport.control.write(folder/'transport_cli_spawn_started_v2.json',{'version':transport.VERSION,
            'claim_id':dispatch['claim_id'],'intent_sha256':dispatch['intent_sha256'],'cli_identity':ancestry['cli'],
            'wait_review_sha256':transport.control.sha(folder.parents[1]/'transport_wait_review_v2.json'),
            'fresh_reconciliation_sha256':transport.control.sha(folder/'transport_cli_reconciliation_v2.json'),
            'ancestry_sha256':transport.control.sha(folder/'transport_cli_process_ancestry_v2.json'),
            'wait_source_sha256':transport.source_hashes(),'app_id':own_app_id,'started_at_utc':transport.control.now()},immutable=True)
        call=transport.base.frozen_cli.worker.execute.spawn(job['data'],job['plan'],dispatch)
        value={'run_id':job['run_id'],'claim_id':dispatch['claim_id'],'intent_sha256':dispatch['intent_sha256'],'call_id':call.object_id}
        transport.control.write(folder/'launch.json',value,immutable=True)
    print(json.dumps(value),flush=True)
