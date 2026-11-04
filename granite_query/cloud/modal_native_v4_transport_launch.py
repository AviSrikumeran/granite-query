"""One-shot reviewed owner delegation, using the exact frozen V4 worker."""
from pathlib import Path
import json
import os
from cloud import native_v4_transport as transport
from cloud import modal_native_batch_launch_v4 as frozen_cli

app=frozen_cli.app


@app.local_entrypoint()
def repair_launch(folder:str):
    job,dispatch=transport.delegated_preflight(Path(folder));folder=job['folder_path']
    review=transport.validate_transport_review(folder.parents[1])
    evidence=transport.TransportBackend().absence(job['run_id'],[review['original_owner_pid'],review['original_venv_launcher_pid']])
    own_app_id=frozen_cli.app.app_id
    transport._fresh_absence(evidence,job,own_app_id=own_app_id)
    transport.control.write(folder/'transport_cli_reconciliation.json',evidence,immutable=True)
    cli=transport.process_identity(os.getpid())
    if cli is None:raise ValueError('Actual CLI process creation identity required')
    ancestry=transport.observe_cli_ancestry(transport.control.read(folder/'transport_delegation.json'))
    transport.control.write(folder/'transport_cli_process_ancestry.json',ancestry,immutable=True)
    transport.control.write(folder/'transport_cli_spawn_started.json',{'version':transport.VERSION,
        'claim_id':dispatch['claim_id'],'intent_sha256':dispatch['intent_sha256'],'cli_identity':cli,
        'delegation_sha256':transport.control.sha(folder/'transport_delegation.json'),
        'fresh_reconciliation_sha256':transport.control.sha(folder/'transport_cli_reconciliation.json'),
        'ancestry_sha256':transport.control.sha(folder/'transport_cli_process_ancestry.json'),'app_id':own_app_id,
        'transport_source_sha256':transport.source_hashes(),'started_at_utc':transport.control.now()},immutable=True)
    call=frozen_cli.worker.execute.spawn(job['data'],job['plan'],dispatch)
    value={'run_id':job['run_id'],'claim_id':dispatch['claim_id'],'intent_sha256':dispatch['intent_sha256'],'call_id':call.object_id}
    transport.control.write(folder/'launch.json',value,immutable=True)
    print(json.dumps(value),flush=True)
