"""Unpaid evidence audit for a narrow same-protocol feature continuation.

No running worker is changed. A completed earlier checkpoint and a verified
later snapshot/partial store are required; sixteen initial calibration features
alone never justify replaying an infeasible full workload.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path,PurePosixPath
import threading
import time

from cloud.gradient_feature_contract import canonical,sha,validate_input,validate_feature

ROOT=Path(__file__).resolve().parent
SOURCE_FILES={'modal_gradient_features.py','gradient_feature_contract.py','gradient_valuation.py',
    'modal_train.py','student_valuation.py','valuation_contract.py'}
MAX_BYTES=250*1024*1024


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def file_sha(path):return sha(Path(path).read_bytes())


def terminal_identity(folder):
    plan=read(folder/'plan.json');launch=read(folder/'launch.json');terminal=read(folder/'terminal.json')
    if (not launch.get('call_id') or terminal.get('call_id')!=launch['call_id']
            or terminal.get('confirmed_terminal') is not True or terminal.get('stage')=='completed'):
        raise ValueError('Confirm this exact feature call is terminal and incomplete first')
    validate_input(read(folder/'input.json'),plan)
    return plan,launch,terminal


def verify_execution_sources(folder):
    folder=Path(folder);plan=read(folder/'plan.json')
    path=folder/'execution_sources.json';manifest=read(path)
    if manifest.get('protocol_hash')!=plan['protocol_hash'] or set(manifest.get('files_sha256',{}))!=SOURCE_FILES:
        raise ValueError('Preserved execution-source manifest differs from the feature protocol')
    if plan.get('execution_sources_sha256'):
        if file_sha(path)!=plan['execution_sources_sha256']:
            raise ValueError('Copied execution-source provenance changed')
    elif manifest.get('call_id')!=read(folder/'launch.json').get('call_id'):
        raise ValueError('Execution-source capture belongs to another call')
    for name,expected in manifest['files_sha256'].items():
        if file_sha(folder/'execution_sources'/name)!=expected or file_sha(ROOT/name)!=expected:
            raise ValueError('Preserved/current compute source changed: '+name)
    return manifest


def download_evidence(folder,*,volume=None):
    """Read terminal private Volume files only; stream-hash tensors, copy JSON."""
    started=time.monotonic();deadline=started+240
    folder=Path(folder);plan,launch,terminal=terminal_identity(folder)
    verify_execution_sources(folder)
    if terminal['stage']!='calibration_refused':
        raise ValueError('This continuation audit is only for terminal calibration refusal')
    output=folder/'recovery_artifacts';inventory=folder/'recovery_remote_manifest.json'
    if inventory.exists():
        assess_continuation(folder)
        return {'existing':True,'paid_work_launched':False}
    if volume is None:
        import modal
        volume=modal.Volume.from_name('granite-query-training-artifacts')
    entries=volume.listdir(folder.name,recursive=True)
    if len(entries)>5000:raise ValueError('Terminal artifact file-count cap exceeded')
    wanted=[]
    for entry in entries:
        relative=PurePosixPath(entry.path.lstrip('/')).relative_to(PurePosixPath(folder.name))
        name=relative.as_posix()
        selected=(name in {'plan.json','projection.json','parameter_layout.json','calibration.json','result.json','status.json'}
            or name.startswith('features/') and name.endswith('.json') or name.startswith('snapshots/'))
        if not selected or int(entry.type)!=1:continue
        if '..' in relative.parts:raise ValueError('Unsafe terminal artifact path')
        wanted.append((entry,name))
    if sum(entry.size for entry,_ in wanted)>MAX_BYTES:raise ValueError('Terminal recovery read cap exceeded')
    output.mkdir(exist_ok=True);receipts=folder/'recovery_read_receipts';receipts.mkdir(exist_ok=True)
    byte_count=0;guard=threading.Lock()
    def collect(item):
        nonlocal byte_count
        if time.monotonic()>deadline:raise TimeoutError('Bounded terminal recovery read deadline reached; cached receipts remain')
        entry,name=item;digest=hashlib.sha256();content=[];size=0
        copy_json=name.endswith('.json')
        identity={'call_id':launch['call_id'],'name':name,'size':entry.size,'mtime':entry.mtime}
        receipt_path=receipts/(sha(name.encode())+'.json')
        target=(output/name).resolve()
        if receipt_path.exists():
            saved=read(receipt_path)
            if all(saved.get(key)==value for key,value in identity.items()):
                if not copy_json or target.is_file() and file_sha(target)==saved.get('sha256'):
                    return name,saved['sha256'],entry.size
        for chunk in volume.read_file(entry.path):
            if time.monotonic()>deadline:raise TimeoutError('Bounded terminal recovery read deadline reached; cached receipts remain')
            size+=len(chunk);digest.update(chunk)
            with guard:
                byte_count+=len(chunk)
                if byte_count>MAX_BYTES:raise ValueError('Terminal recovery stream cap exceeded')
            if copy_json:
                if size>2*1024*1024:raise ValueError('Individual recovery JSON cap exceeded')
                content.append(chunk)
        if size!=entry.size:raise ValueError('Terminal artifact changed during read')
        if copy_json:
            if not target.is_relative_to(output.resolve()):raise ValueError('Unsafe recovery copy path')
            target.parent.mkdir(parents=True,exist_ok=True);raw=b''.join(content)
            if target.exists() and target.read_bytes()!=raw:raise ValueError('Preserved recovery JSON changed')
            if not target.exists():
                with target.open('xb') as handle:handle.write(raw)
        temporary=receipt_path.with_suffix('.tmp')
        temporary.write_bytes(canonical(dict(identity,sha256=digest.hexdigest())));temporary.replace(receipt_path)
        return name,digest.hexdigest(),size
    with ThreadPoolExecutor(max_workers=8) as executor:downloaded=list(executor.map(collect,wanted))
    manifest={'schema_version':1,'run_id':folder.name,'call_id':launch['call_id'],
        'protocol_hash':plan['protocol_hash'],'terminal_stage':terminal['stage'],
        'captured_at_utc':datetime.now(timezone.utc).isoformat(),'verified_stream_bytes':byte_count,
        'verified_total_source_bytes':sum(size for _,_,size in downloaded),'read_deadline_seconds':240,
        'files_sha256':{name:digest for name,digest,_ in downloaded},
        'file_sizes':{name:size for name,_,size in downloaded},
        'note':'Authenticated terminal Volume read; binary checkpoint files were stream-hashed, not loaded or executed.'}
    with inventory.open('x',encoding='utf-8') as handle:json.dump(manifest,handle,indent=2)
    decision=assess_continuation(folder)
    return dict(decision,paid_work_launched=False)


def assess_continuation(folder):
    folder=Path(folder);plan,launch,terminal=terminal_identity(folder)
    verify_execution_sources(folder)
    if terminal['stage']!='calibration_refused':raise ValueError('Narrow continuation requires terminal calibration_refused')
    config=validate_input(read(folder/'input.json'),plan);data=read(folder/'input.json')
    inventory=read(folder/'recovery_remote_manifest.json');root=folder/'recovery_artifacts'
    if (inventory.get('call_id')!=launch['call_id'] or inventory.get('protocol_hash')!=plan['protocol_hash']
            or inventory.get('terminal_stage')!='calibration_refused'):
        raise ValueError('Terminal recovery evidence belongs to another call/protocol')
    hashes=inventory['files_sha256']
    for name,expected in hashes.items():
        if name.endswith('.json'):
            path=(root/name).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file() or file_sha(path)!=expected:
                raise ValueError('Downloaded terminal recovery JSON changed: '+name)
    if read(root/'plan.json')!=plan:raise ValueError('Remote and local feature plans differ')
    projection=read(root/'projection.json');layout=read(root/'parameter_layout.json')
    if (sha(canonical(layout['layout']))!=layout['sha256'] or projection['parameter_layout_sha256']!=layout['sha256']
            or projection['dimension']!=config['projection_dimension'] or projection['seed']!=config['projection_seed']
            or projection['family']!=config['projection_family']):
        raise ValueError('Preserved layout/projection changed')
    ready=[];counts={};elapsed=[];timings={};per_checkpoint=len(data['candidates'])+len(data['targets'])
    for step in config['checkpoint_updates']:
        base=f'snapshots/update{step:03}';ready_path=root/base/'READY.json'
        if not ready_path.exists():continue
        snapshot=read(ready_path)
        if (snapshot.get('protocol_hash')!=plan['protocol_hash'] or snapshot.get('updates')!=step
                or snapshot.get('layout_sha256')!=layout['sha256']
                or snapshot.get('supervised_tokens')!=step*config['tokens_per_update']):
            raise ValueError('Saved warmup snapshot identity differs')
        files=snapshot['files_sha256']
        if not {'optimizer.pt','adapter/adapter_config.json','adapter/adapter_model.safetensors'}<=set(files):
            raise ValueError('Saved warmup adapter/optimizer snapshot is incomplete')
        for name,expected in files.items():
            if '..' in PurePosixPath(name).parts or hashes.get(base+'/'+name)!=expected:
                raise ValueError('Saved warmup checkpoint file missing or changed')
        ready.append(step);counts[step]=0
        for role,records in (('candidate',data['candidates']),('target',data['targets'])):
            for row in records:
                name=f'features/update{step:03}/{role}/{sha(row["id"].encode())}.json'
                path=root/name
                if not path.exists():continue
                value=read(path)
                if name not in hashes:raise ValueError('Feature was not included in verified terminal read')
                validate_feature(value,row,f'update{step:03}',layout['sha256'],projection['mapping_sha256'],projection['dimension'])
                if (value.get('protocol_hash')!=plan['protocol_hash'] or value.get('role')!=role
                        or value.get('gradient_type')!=('less_adam' if role=='candidate' else 'sgd')):
                    raise ValueError('Preserved gradient role/protocol changed')
                timing=value.get('elapsed_seconds')
                if not isinstance(timing,(int,float)) or not math.isfinite(timing) or timing<=0:
                    raise ValueError('Preserved feature timing cannot support a bounded continuation')
                elapsed.append(timing);timings[(step,role,row['id'])]=timing;counts[step]+=1
    if not ready:raise ValueError('No verified ready warmup snapshot for continuation')
    latest=max(ready);earlier=[step for step in config['checkpoint_updates'] if step<latest]
    if latest!=config['checkpoint_updates'][-1]:
        raise ValueError('Final ready warmup snapshot is missing; do not replay an infeasible full workload')
    if not earlier or any(counts.get(step)!=per_checkpoint for step in earlier):
        raise ValueError('A complete earlier checkpoint is required; initial calibration alone is insufficient')
    if counts[latest]<config['calibration_examples'] or counts[latest]>=per_checkpoint:
        raise ValueError('Require real partial later-checkpoint features to continue')
    calibration=read(root/'calibration.json');result=read(root/'result.json')
    completed=sum(counts.values());total=per_checkpoint*len(config['checkpoint_updates'])
    public=result.get('public_summary',{})
    if (result.get('stage')!='calibration_refused' or result.get('protocol_hash')!=plan['protocol_hash']
            or public.get('completed_features')!=completed or public.get('total_features')!=total
            or calibration.get('protocol_hash')!=plan['protocol_hash']
            or calibration.get('checkpoint_id')!=f'update{latest:03}'
            or calibration.get('decision')!='refuse_full_collection'
            or calibration.get('actual_samples')!=config['calibration_examples']
            or calibration.get('margin')!=config['calibration_margin']):
        raise ValueError('Terminal counts/calibration differ from real preserved artifacts')
    for key in data['calibration_ids']:
        path=root/f'features/update{latest:03}/candidate/{sha(key.encode())}.json'
        if not path.exists():raise ValueError('Later checkpoint calibration features are missing')
    mean,p75=calibration['mean_seconds'],calibration['p75_seconds']
    if any(not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0 for v in (mean,p75)):
        raise ValueError('Invalid calibration speed evidence')
    actual_times=[timings[(latest,'candidate',key)] for key in data['calibration_ids']]
    if (not math.isclose(mean,math.fsum(actual_times)/len(actual_times),rel_tol=1e-12)
            or not math.isclose(p75,sorted(actual_times)[math.ceil(.75*len(actual_times))-1],rel_tol=1e-12)):
        raise ValueError('Calibration timing does not match preserved later-checkpoint features')
    observed_p75=sorted(elapsed)[math.ceil(.75*len(elapsed))-1]
    effective=max(mean,p75,observed_p75)*config['calibration_margin']
    remaining=total-completed
    # The current worker resumes only from its latest ready snapshot. Earlier
    # features are complete, so it skips them; no warmup replay is necessary here.
    warmup_remaining=config['checkpoint_updates'][-1]-latest
    if warmup_remaining:raise ValueError('Continuation must already have the final warmup snapshot')
    startup=config['startup_timeout_seconds'];io=config['calibration_io_allowance_seconds']
    forecast=startup+remaining*effective+io
    if forecast>config['calibration_finish_limit_seconds']:
        raise ValueError('Remaining verified features do not fit a fresh bounded call')
    return {'stage':'same_protocol_continuation_permitted','protocol_hash':plan['protocol_hash'],
        'latest_verified_snapshot':latest,'completed_features':completed,'remaining_features':remaining,
        'completed_checkpoint_counts':{str(k):v for k,v in counts.items()},
        'calibration_p75_seconds':p75,'observed_feature_p75_seconds':observed_p75,
        'margin':config['calibration_margin'],'startup_allowance_seconds':startup,'io_allowance_seconds':io,
        'forecast_fresh_call_seconds':forecast,'allowed_collection_seconds':config['calibration_finish_limit_seconds'],
        'source_capture_timing':read(folder/'execution_sources.json').get('capture_timing'),
        'root_review_required':True,'new_reservation_required':True,'paid_work_launched':False}
