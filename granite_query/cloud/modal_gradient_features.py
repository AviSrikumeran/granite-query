"""Separate bounded LESS-inspired CountSketch feature worker. Not launched here.

One A10080GB, <=4CPU/32GiB host memory,1800s maximum; no automatic retries. The
local entrypoint refuses without reviewed protocol, fresh saved reservation, and
no active Modal task. Raw traces/features stay in the private artifact Volume.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import traceback

import modal
from .modal_train import image,artifacts,state
from .gradient_feature_contract import (MODEL,REVISION,PROJECTION_FAMILY,canonical,sha,
    validate_input,validate_resume,validate_feature,labels_for,mapping_bytes,countsketch_mapping)

app=modal.App('granite-query-gradient-features',include_source=False)
# The shared image already ends with a startup source mount. Modal prohibits
# appending image build steps after that mount; set process flags before imports.
feature_image=image


class BoundedStop(Exception):
    pass


def safe_run(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',value):
        raise ValueError('Unsafe artifact run ID')
    return value


def read(path):
    return json.loads(Path(path).read_text())


def write(path,value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_bytes(canonical(value)); temporary.replace(path)


@app.function(image=feature_image,gpu='A100-80GB',cpu=(4,4),memory=(32768,32768),
    timeout=1800,startup_timeout=120,retries=0,max_containers=1,min_containers=0,
    buffer_containers=0,scaledown_window=2,volumes={'/artifacts':artifacts})
def collect(data:dict,plan:dict):
    os.environ.update({'OMP_NUM_THREADS':'4','MKL_NUM_THREADS':'4','CUBLAS_WORKSPACE_CONFIG':':4096:8'})
    started=time.monotonic(); run_id=safe_run(plan['run_id'])
    folder=Path('/artifacts')/run_id; folder.mkdir(parents=True,exist_ok=True)
    call_id=modal.current_function_call_id()
    completed_features=0; config=validate_input(data,plan)
    total_features=len(config['checkpoint_updates'])*(len(data['candidates'])+len(data['targets']))
    def checkpoint(stage,commit=False,**details):
        value=dict(run_id=run_id,call_id=call_id,stage=stage,elapsed_seconds=round(time.monotonic()-started,3),
            completed_features=completed_features,total_features=total_features,**details)
        state[run_id]=value; write(folder/'status.json',value)
        if commit:
            artifacts.commit()
        print(json.dumps(value),flush=True)
    def stopped(stage,**details):
        public=dict(stage=stage,method=config['method'],projected_features_complete=False,
            candidates=len(data['candidates']),selection_development_targets=len(data['targets']),
            completed_features=completed_features,total_features=total_features,
            projection_family=PROJECTION_FAMILY,projection_dimension=config['projection_dimension'],
            official_test_used=False,accuracy_improvement_measured=False,**details)
        result=dict(run_id=run_id,stage=stage,projected_features_complete=False,
                    protocol_hash=plan['protocol_hash'],public_summary=public)
        write(folder/'result.json',result); checkpoint(stage,commit=True,**details)
        return result
    try:
        if not state.put('gradient-owner:'+run_id,dict(call_id=call_id,protocol_hash=plan['protocol_hash']),skip_if_exists=True):
            raise ValueError('Existing attempt owns this feature run; reconcile and prepare a new resume')
        previous=None
        if plan.get('resume_from'):
            previous=Path('/artifacts')/safe_run(plan['resume_from'])
            validate_resume(read(previous/'plan.json'),plan)
            for name in ('snapshots','features'):
                if (previous/name).exists():
                    shutil.copytree(previous/name,folder/name)
            if (previous/'calibration.json').exists():
                shutil.copyfile(previous/'calibration.json',folder/'calibration.json')
        write(folder/'plan.json',plan); write(folder/'input.json',data)
        checkpoint('loading_model',commit=True)
        import importlib.metadata
        import torch
        from transformers import AutoTokenizer,AutoModelForCausalLM,set_seed
        from peft import LoraConfig,get_peft_model,PeftModel
        torch.set_num_threads(4); set_seed(config['seed'])
        torch.backends.cuda.matmul.allow_tf32=False
        torch.backends.cudnn.allow_tf32=False
        # CPU projection avoids nondeterministic CUDA scatter-add reduction.
        # Floating-point model numerics can still vary across hardware/toolchains.
        tokenizer=AutoTokenizer.from_pretrained(MODEL,revision=REVISION)
        from .student_valuation import encode_example
        for row in data['candidates']+data['targets']:
            actual=encode_example(row,tokenizer)
            if actual['prefix_ids']!=row['prefix_ids'] or actual['answer_ids']!=row['answer_ids']:
                raise ValueError('Runtime tokenizer/prompt differs from frozen input')
            if sha(row['response'].encode())!=row['raw_response_sha256']:
                raise ValueError('Original teacher trace changed')
        backend=tokenizer.backend_tokenizer
        expected_tokenizer=plan['protocol']['sources']['tokenizer']
        if sha(backend.to_str().encode())!=expected_tokenizer['backend_sha256'] or sha(str(tokenizer.chat_template).encode())!=expected_tokenizer['chat_template_sha256']:
            raise ValueError('Pinned tokenizer or chat template changed')
        base=AutoModelForCausalLM.from_pretrained(MODEL,revision=REVISION,torch_dtype=torch.bfloat16,
                                               attn_implementation='sdpa').to('cuda')
        base.config.use_cache=False
        snapshots=folder/'snapshots'; snapshots.mkdir(exist_ok=True)
        ready=[]
        for step in config['checkpoint_updates']:
            root=snapshots/f'update{step:03}'
            if (root/'READY.json').exists():
                manifest=read(root/'READY.json')
                if manifest['protocol_hash']!=plan['protocol_hash'] or manifest['updates']!=step:
                    raise ValueError('Saved warmup checkpoint identity changed')
                for filename,expected in manifest['files_sha256'].items():
                    if sha((root/filename).read_bytes())!=expected:
                        raise ValueError('Saved warmup checkpoint file changed')
                ready.append(step)
        latest=max(ready,default=0)
        if latest:
            model=PeftModel.from_pretrained(base,snapshots/f'update{latest:03}'/'adapter',is_trainable=True)
        else:
            model=get_peft_model(base,LoraConfig(r=8,lora_alpha=16,lora_dropout=0.0,
                target_modules=['q_proj','v_proj'],bias='none',task_type='CAUSAL_LM'))
        named=sorted((name,p) for name,p in model.named_parameters() if p.requires_grad)
        if any('lora_' not in name for name,_ in named):
            raise ValueError('Only LoRA weights may require gradients')
        layout=[dict(name=name,shape=list(p.shape),numel=p.numel()) for name,p in named]
        parameter_count=sum(p.numel() for _,p in named); layout_hash=sha(canonical(layout))
        if parameter_count!=2621440:
            raise ValueError('Pinned q/v LoRA parameter count differs from reviewed2621440')
        optimizer=torch.optim.AdamW([p for _,p in named],lr=config['learning_rate'],weight_decay=0.0,
            betas=(config['beta1'],config['beta2']),eps=config['eps'])
        history=[]; warmup_done=0
        if latest:
            saved=torch.load(snapshots/f'update{latest:03}'/'optimizer.pt',map_location='cpu',weights_only=False)
            if saved['layout_sha256']!=layout_hash or saved['updates']!=latest:
                raise ValueError('Saved optimizer parameter order/layout changed')
            optimizer.load_state_dict(saved['optimizer']); history=saved['history']; warmup_done=latest
        write(folder/'parameter_layout.json',dict(layout=layout,sha256=layout_hash,parameters=parameter_count))
        write(folder/'packages.json',{d.metadata['Name']:d.version for d in importlib.metadata.distributions()})
        raw_map=mapping_bytes(parameter_count,config['projection_seed'])
        map_hash=sha(raw_map); dimension=config['projection_dimension']
        # One5-byte hash-stream entry per parameter: uint32 little-endian bucket
        # word + sign bit. No P-by-d matrix, no GPU mapping, O(P+d) workspace.
        table=torch.frombuffer(bytearray(raw_map),dtype=torch.uint8).view(parameter_count,5)
        buckets=(table[:,0].long()+table[:,1].long()*256+table[:,2].long()*65536+table[:,3].long()*16777216)%dimension
        signs=(table[:,4].bitwise_and(1).float()*2-1)
        check_buckets,check_signs,_=countsketch_mapping(min(64,parameter_count),dimension,config['projection_seed'])
        if buckets[:64].tolist()!=check_buckets or signs[:64].tolist()!=check_signs:
            raise ValueError('Vectorized projection differs from dependency-free reference')
        del table,raw_map
        projection=dict(family=PROJECTION_FAMILY,dimension=dimension,seed=config['projection_seed'],
            parameter_layout_sha256=layout_hash,mapping_sha256=map_hash,device='cpu',dtype='float32',
            limitation='One-bucket CountSketch adaptation; not LESS dense Rademacher JL and not a causal estimator')
        write(folder/'projection.json',projection)
        by_id={row['id']:row for row in data['candidates']}
        def forward_backward(row,start=0,end=None):
            model.zero_grad(set_to_none=True)
            ids=torch.tensor([row['prefix_ids']+row['answer_ids']],device='cuda')
            labels=torch.tensor([labels_for(row,start,end)],device='cuda')
            loss=model(input_ids=ids,labels=labels).loss
            if not torch.isfinite(loss):
                raise ValueError('Nonfinite warmup/feature loss')
            return loss
        def save_snapshot(step):
            root=snapshots/f'update{step:03}'; root.mkdir(parents=True,exist_ok=True)
            if (root/'READY.json').exists():
                raise ValueError('Never overwrite an immutable ready warmup checkpoint')
            model.save_pretrained(root/'adapter')
            temporary=root/'optimizer.pt.tmp'
            torch.save(dict(optimizer=optimizer.state_dict(),updates=step,history=history,layout_sha256=layout_hash),temporary)
            temporary.replace(root/'optimizer.pt')
            files={p.relative_to(root).as_posix():sha(p.read_bytes()) for p in sorted(root.rglob('*')) if p.is_file()}
            manifest=dict(protocol_hash=plan['protocol_hash'],updates=step,
                          supervised_tokens=step*config['tokens_per_update'],layout_sha256=layout_hash,files_sha256=files,
                          checkpoint_weight=math.fsum(r['learning_rate'] for r in history[-4:])/4)
            write(root/'READY.json',manifest)
            artifacts.commit()
            return manifest
        def feature_path(step,role,key):
            return folder/'features'/f'update{step:03}'/role/(sha(key.encode())+'.json')
        def saved_features(step,role,records):
            found={}
            for row in records:
                path=feature_path(step,role,row['id'])
                if path.exists():
                    value=read(path)
                    validate_feature(value,row,f'update{step:03}',layout_hash,map_hash,dimension)
                    if value.get('protocol_hash')!=plan['protocol_hash'] or value.get('role')!=role:
                        raise ValueError('Saved feature protocol/role changed')
                    found[row['id']]=value
            return found
        for step in config['checkpoint_updates']:
            completed_features+=len(saved_features(step,'candidate',data['candidates']))+len(saved_features(step,'target',data['targets']))
        for step in config['checkpoint_updates']:
            candidate_features=saved_features(step,'candidate',data['candidates'])
            target_features=saved_features(step,'target',data['targets'])
            if step<warmup_done:
                if len(candidate_features)!=len(data['candidates']) or len(target_features)!=len(data['targets']):
                    raise ValueError('Older warmup checkpoint has missing features despite a later snapshot')
                continue
            model.eval() # Gradients remain enabled; disables stochastic dropout.
            for update in data['warmup']['updates'][warmup_done:step]:
                if time.monotonic()-started>config['collection_guard_seconds']:
                    raise BoundedStop('Warmup deadline; last ready snapshot remains resumable')
                before=time.monotonic(); optimizer.zero_grad(set_to_none=True)
                learning_rate=config['learning_rate']*min(1,(update['index']+1)/config['lr_warmup_updates'])
                for group in optimizer.param_groups:
                    group['lr']=learning_rate
                weighted_loss=0.0
                # Do not zero gradients between microbatches of one effective batch.
                for window in update['microbatches']:
                    row=by_id[window['id']]
                    ids=torch.tensor([row['prefix_ids']+row['answer_ids']],device='cuda')
                    labels=torch.tensor([labels_for(row,window['answer_start'],window['answer_end'])],device='cuda')
                    loss=model(input_ids=ids,labels=labels).loss
                    if not torch.isfinite(loss):
                        raise ValueError('Nonfinite warmup loss')
                    (loss*window['loss_weight']).backward(); weighted_loss+=float(loss.detach())*window['loss_weight']
                torch.nn.utils.clip_grad_norm_([p for _,p in named],config['max_grad_norm'])
                optimizer.step(); warmup_done=update['index']+1
                torch.cuda.synchronize()
                history.append(dict(update=warmup_done,supervised_tokens=1024,weighted_loss=weighted_loss,
                    learning_rate=learning_rate,elapsed_seconds=time.monotonic()-before))
                checkpoint('selector_warmup',updates=warmup_done,supervised_tokens=warmup_done*1024)
            root=snapshots/f'update{step:03}'
            snapshot=read(root/'READY.json') if (root/'READY.json').exists() else save_snapshot(step)
            moments=torch.cat([optimizer.state[p]['exp_avg'].detach().float().reshape(-1) for _,p in named])
            second_moments=torch.cat([optimizer.state[p]['exp_avg_sq'].detach().float().reshape(-1) for _,p in named])
            checkpoint_id=f'update{step:03}'
            def feature(row,role):
                nonlocal completed_features
                if time.monotonic()-started>config['collection_guard_seconds']:
                    raise BoundedStop('Collection deadline; committed features remain incomplete')
                before=time.monotonic(); loss=forward_backward(row); loss.backward()
                vector=torch.cat([p.grad.detach().float().reshape(-1) if p.grad is not None else torch.zeros(p.numel(),device='cuda') for _,p in named])
                if role=='candidate':
                    vector=(.9*moments+.1*vector)/torch.sqrt(.999*second_moments+.001*vector.square()+1e-8)
                if not torch.isfinite(vector).all():
                    raise ValueError('Nonfinite model gradient/Adam proxy')
                full_norm=float(torch.linalg.vector_norm(vector))
                cpu_values=vector.detach().cpu()
                sketch=torch.zeros(dimension,dtype=torch.float32,device='cpu')
                sketch.scatter_add_(0,buckets,cpu_values*signs)
                projected_norm=float(torch.linalg.vector_norm(sketch))
                if not math.isfinite(projected_norm) or projected_norm<=1e-15:
                    raise ValueError('CountSketch produced a zero/nonfinite gradient feature')
                record=dict(id=row['id'],source_split='train',question_sha256=row['question_sha256'],
                    raw_response_sha256=row['raw_response_sha256'],verified_final_answer=True,
                    checkpoint_id=checkpoint_id,parameter_layout_sha256=layout_hash,projection_mapping_sha256=map_hash,
                    protocol_hash=plan['protocol_hash'],role=role,gradient_type='less_adam' if role=='candidate' else 'sgd',
                    feature=sketch.tolist(),gradient_norm=full_norm,projected_norm=projected_norm,
                    mean_response_nll=float(loss.detach()),response_tokens=len(row['answer_ids']),
                    reference_type=row.get('reference_type'),
                    reference_match_is_independent_gold=row.get('reference_match_is_independent_gold',False),
                    elapsed_seconds=time.monotonic()-before)
                if role=='target':
                    record['group']=row['group']
                record['record_sha256']=sha(canonical(record))
                validate_feature(record,row,checkpoint_id,layout_hash,map_hash,dimension)
                write(feature_path(step,role,row['id']),record)
                completed_features+=1; model.zero_grad(set_to_none=True)
                return record
            # First16 candidates span sequence-length quantiles; they are retained
            # as real features rather than duplicated calibration passes.
            for key in data['calibration_ids']:
                if key not in candidate_features:
                    candidate_features[key]=feature(by_id[key],'candidate')
            artifacts.commit()
            times=[candidate_features[key]['elapsed_seconds'] for key in data['calibration_ids']]
            mean=math.fsum(times)/len(times); p75=sorted(times)[math.ceil(.75*len(times))-1]
            effective=max(mean,p75)*config['calibration_margin']
            warmup_remaining=(config['checkpoint_updates'][-1]-warmup_done)*max(r['elapsed_seconds'] for r in history)*1.25
            forecast=(time.monotonic()-started)+(total_features-completed_features)*effective+warmup_remaining+config['calibration_io_allowance_seconds']
            calibration=dict(protocol_hash=plan['protocol_hash'],checkpoint_id=checkpoint_id,
                actual_samples=len(times),mean_seconds=mean,p75_seconds=p75,margin=config['calibration_margin'],
                projected_finish_seconds=forecast,allowed_finish_seconds=config['calibration_finish_limit_seconds'],
                decision='proceed' if forecast<=config['calibration_finish_limit_seconds'] else 'refuse_full_collection')
            write(folder/'calibration.json',calibration)
            checkpoint('calibration',commit=True,projected_finish_seconds=round(forecast,2),decision=calibration['decision'])
            if forecast>config['calibration_finish_limit_seconds']:
                return stopped('calibration_refused',projected_finish_seconds=round(forecast,2))
            since_commit=0
            for role,records,found in [('candidate',data['candidates'],candidate_features),('target',data['targets'],target_features)]:
                for row in records:
                    if row['id'] in found:
                        continue
                    found[row['id']]=feature(row,role); since_commit+=1
                    if since_commit>=config['commit_interval']:
                        checkpoint('collecting_'+role,commit=True,checkpoint=checkpoint_id)
                        since_commit=0
            checkpoint('checkpoint_features_completed',commit=True,checkpoint=checkpoint_id)
            del moments,second_moments
        payload=dict(schema_version=1,method=config['method'],model={'name':MODEL,'revision':REVISION},
            protocol_hash=plan['protocol_hash'],official_test_used=False,target_role='selection_development',
            projection=projection,checkpoints=[])
        for step in config['checkpoint_updates']:
            snapshot=read(snapshots/f'update{step:03}'/'READY.json')
            candidates=saved_features(step,'candidate',data['candidates']); targets=saved_features(step,'target',data['targets'])
            if len(candidates)!=len(data['candidates']) or len(targets)!=len(data['targets']):
                raise ValueError('Incomplete feature store cannot be exported as completed')
            payload['checkpoints'].append(dict(id=f'update{step:03}',weight=snapshot['checkpoint_weight'],
                candidate_gradient_type='less_adam',target_gradient_type='sgd',
                candidates=[candidates[r['id']] for r in data['candidates']],targets=[targets[r['id']] for r in data['targets']]))
        if time.monotonic()-started>config['application_guard_seconds']:
            raise BoundedStop('Export deadline; complete per-record features preserved')
        write(folder/'features_payload.json',payload)
        public=dict(stage='completed',method=config['method'],projected_features_complete=True,
            candidates=len(data['candidates']),selection_development_targets=len(data['targets']),
            completed_features=completed_features,total_features=total_features,checkpoints=len(config['checkpoint_updates']),
            projection_family=PROJECTION_FAMILY,projection_dimension=dimension,selector_warmup_tokens=8192,
            official_test_used=False,accuracy_improvement_measured=False,
            elapsed_seconds=round(time.monotonic()-started,3),
            limitation='Completed CountSketch gradient proxies, not observed causal value or student accuracy gains')
        result=dict(run_id=run_id,stage='completed',projected_features_complete=True,protocol_hash=plan['protocol_hash'],
            feature_payload_sha256=sha((folder/'features_payload.json').read_bytes()),public_summary=public)
        write(folder/'result.json',result); checkpoint('completed',commit=True)
        return result
    except BoundedStop as error:
        write(folder/'bounded_stop.json',dict(reason=str(error),protocol_hash=plan['protocol_hash']))
        return stopped('bounded_stop')
    except Exception as error:
        (folder/'failure.txt').write_text(traceback.format_exc())
        checkpoint('failed',commit=True,error_type=type(error).__name__)
        raise


@app.local_entrypoint()
def launch(folder:str):
    local=Path(folder).resolve(); runtime=Path(__file__).resolve().parent/'runs/supervisor'
    lock=runtime/'gpu_launch.lock'; fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    try:
        os.write(fd,str(os.getpid()).encode())
        if (local/'launch.json').exists():
            raise ValueError('Existing launch record: reconcile instead of duplicating')
        plan=read(local/'plan.json'); data=read(local/'input.json'); validate_input(data,plan)
        review=read(local/'reviewed_for_launch.json')
        if review.get('reviewed') is not True or review.get('protocol_hash')!=plan['protocol_hash'] or review.get('stage')!='gradient_feature_collection':
            raise ValueError('Root/supervisor must review this exact prepared feature protocol before launch')
        ledger=read(runtime/'budget.json')
        from .comparison_control import require_fresh_modal_budget
        require_fresh_modal_budget(ledger)
        job=next((j for j in ledger['jobs'] if j['run_id']==plan['run_id'] and j.get('service')=='modal'),None)
        if not job or job.get('status')!='reserved' or job.get('reserved_usd',0)<3:
            raise ValueError('A new saved$3 Modal reservation is required')
        env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1')
        listed=subprocess.run([sys.executable,'-m','modal','app','list','--json'],capture_output=True,
                              env=env,timeout=30,check=True)
        apps=json.loads(listed.stdout.decode('utf-8'))
        if any(str(item.get('tasks','0')).isdigit() and int(item.get('tasks','0'))>0 for item in apps):
            raise ValueError('Another Modal task is active; preserve the one-GPU policy')
        write(local/'launch.json',dict(run_id=plan['run_id'],status='spawning',protocol_hash=plan['protocol_hash']))
        call=collect.spawn(data,plan)
        value=dict(run_id=plan['run_id'],status='spawned',call_id=call.object_id,protocol_hash=plan['protocol_hash'])
        write(local/'launch.json',value); print(json.dumps(value),flush=True)
    finally:
        os.close(fd); lock.unlink()
