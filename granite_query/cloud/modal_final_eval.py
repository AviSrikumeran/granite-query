"""Unlaunched separate final base/chosen evaluator; hashes precede model load."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import time
import traceback
import modal
from .modal_train import image,artifacts,state
from . import final_eval_control as seal
from . import final_test_loader as loader
from .final_eval_jobs import validate_payload,validate_saved,validate_batch,validated_adapter,DEPS
from .valuation_contract import trim_generation

app=modal.App('granite-query-sealed-final',include_source=False)
ROOT=Path(__file__).resolve().parent


@app.function(image=image,gpu='A100-80GB',cpu=(4,4),memory=(32768,32768),timeout=1800,
    startup_timeout=120,retries=0,max_containers=1,min_containers=0,buffer_containers=0,
    scaledown_window=2,volumes={'/artifacts':artifacts})
def evaluate(payload:dict,plan:dict,manifest:dict):
    started=time.monotonic();rows=validate_payload(payload,plan,manifest)
    loader.require_role(manifest,'granite_evaluator',Path(__file__),dependencies=[ROOT/name for name in DEPS])
    loader.require_packaged_sources(manifest)
    if not seal.safe_name(plan['run_id']):raise ValueError('Unsafe final artifact run ID')
    folder=Path('/artifacts')/plan['run_id'];folder.mkdir(parents=True,exist_ok=True)
    call_id=modal.current_function_call_id();evaluations=[]
    def checkpoint(stage,**details):
        status=dict(stage=stage,run_id=plan['run_id'],call_id=call_id,completed=len(evaluations),requested=256,
            elapsed_seconds=round(time.monotonic()-started,3),**details)
        loader.atomic(folder/'status.json',status);state[plan['run_id']]=status;artifacts.commit()
    try:
        if not state.put('final-owner:'+plan['run_id'],{'call_id':call_id,'protocol_hash':plan['protocol_hash']},skip_if_exists=True):
            raise ValueError('Existing attempt owns this final run; use reviewed terminal recovery')
        if plan.get('resume_from'):
            if not seal.safe_name(plan['resume_from']):raise ValueError('Unsafe recovery run ID')
            old=Path('/artifacts')/plan['resume_from']
            if seal.load(old/'plan.json')['protocol_hash']!=plan['protocol_hash']:raise ValueError('Final recovery protocol changed')
            if (old/'batches').exists():
                for path in sorted((old/'batches').glob('batch*.json')):
                    value=seal.load(path)
                    if value.get('start')!=len(evaluations):raise ValueError('Recovery batches are not a contiguous saved prefix')
                    evaluations.extend(validate_batch(value,rows,plan,manifest))
                validate_saved(evaluations,rows,manifest['freeze_sha256'])
                shutil.copytree(old/'batches',folder/'batches')
        (folder/'batches').mkdir(exist_ok=True)
        loader.atomic(folder/'plan.json',plan);loader.atomic(folder/'seal.json',manifest)
        if plan['checkpoint']=='chosen':
            adapter=validated_adapter('/artifacts',manifest)
        checkpoint('loading_model')
        import torch
        from transformers import AutoTokenizer,AutoModelForCausalLM,set_seed
        from peft import PeftModel
        torch.set_num_threads(4);set_seed(plan['seed'])
        tokenizer=AutoTokenizer.from_pretrained(seal.MODEL,revision=seal.REVISION)
        tokenizer.pad_token=tokenizer.eos_token;tokenizer.padding_side='left'
        model=AutoModelForCausalLM.from_pretrained(seal.MODEL,revision=seal.REVISION,
            torch_dtype=torch.bfloat16,attn_implementation='sdpa').to('cuda')
        if plan['checkpoint']=='chosen':model=PeftModel.from_pretrained(model,adapter)
        model.eval()
        eos=model.generation_config.eos_token_id;eos_ids=list(eos) if isinstance(eos,(tuple,list)) else [eos]
        eos_ids.append(tokenizer.eos_token_id)
        prefix=manifest['protocol']['inference']['user_prefix']
        def render(row):return tokenizer.apply_chat_template([{'role':'user','content':prefix+row['prompt']}],
            tokenize=False,add_generation_prompt=True,enable_thinking=False)
        for offset in range(len(evaluations),256,8):
            if time.monotonic()-started>1600:
                checkpoint('bounded_stop');return {'stage':'bounded_stop','completed':len(evaluations),'protocol_hash':plan['protocol_hash']}
            batch=rows[offset:offset+8]
            inputs=tokenizer([render(row) for row in batch],padding=True,return_tensors='pt',add_special_tokens=False).to('cuda')
            if inputs['input_ids'].shape[1]>2048:raise ValueError('Final question exceeds frozen context; never resample')
            width=inputs['input_ids'].shape[1];torch.cuda.synchronize();before=time.monotonic()
            with torch.no_grad():outputs=model.generate(**inputs,max_new_tokens=512,do_sample=False,use_cache=True,pad_token_id=tokenizer.pad_token_id)
            torch.cuda.synchronize();elapsed=time.monotonic()-before
            for row,output in zip(batch,outputs):
                tail,truncated=trim_generation(output[width:].tolist(),eos_ids,512)
                evaluations.append({'id':row['id'],'gold_answer':row['gold_answer'],'response':tokenizer.decode(tail,skip_special_tokens=True),
                    'generated_tokens':len(tail),'truncated':truncated,'elapsed_seconds':elapsed/8,
                    'batch_elapsed_seconds':elapsed,'batch_size':8,'freeze_sha256':manifest['freeze_sha256']})
            saved=evaluations[offset:offset+8]
            loader.atomic(folder/'batches'/f'batch{offset:03}.json',{'start':offset,'rows':saved,
                'rows_sha256':loader.sha_bytes(loader.encoded(saved)),'freeze_sha256':manifest['freeze_sha256'],
                'protocol_hash':plan['protocol_hash']})
            checkpoint('evaluation')
        result={'stage':'completed','run_id':plan['run_id'],'checkpoint':plan['checkpoint'],'plan':plan,
            'freeze_sha256':manifest['freeze_sha256'],'evaluations':{plan['checkpoint']:evaluations},
            'official_test_used':True,'sample_count':256,'full_test_evaluation':False,
            'elapsed_seconds':time.monotonic()-started,'latency_measurement':'amortized batch8 GPU generation'}
        loader.atomic(folder/'result.json',result);checkpoint('completed');return result
    except Exception as error:
        (folder/'failure.txt').write_text(traceback.format_exc());checkpoint('failed',error_type=type(error).__name__);raise


@app.local_entrypoint()
def launch(folder:str):
    local=Path(folder);runtime=ROOT/'runs/supervisor';lock=runtime/'gpu_launch.lock'
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    try:
        os.write(fd,str(os.getpid()).encode())
        if (local/'launch.json').exists():raise ValueError('Existing final launch must be reconciled, never duplicated')
        plan=seal.load(local/'plan.json');payload=seal.load(local/'input.json');manifest=seal.load(local/'seal.json')
        validate_payload(payload,plan,manifest)
        current=seal.verify(plan['final_folder_path'])
        if current['freeze_sha256']!=manifest['freeze_sha256']:raise ValueError('Final selection seal changed')
        _,sample,raw,_=loader.load_prepared(plan['final_folder_path'],plan['input_folder_path'])
        if sample!=payload['sample_manifest'] or raw.decode('utf-8')!=payload['sample_jsonl']:
            raise ValueError('Final job no longer matches the persisted sealed dataset receipt')
        loader.require_role(manifest,'granite_evaluator',Path(__file__),dependencies=[ROOT/name for name in DEPS])
        ledger=seal.load(runtime/'budget.json')
        from .comparison_control import require_fresh_modal_budget
        require_fresh_modal_budget(ledger)
        job=next((j for j in ledger['jobs'] if j['run_id']==plan['run_id'] and j.get('service')=='modal'),None)
        if not job or job.get('status')!='reserved' or job.get('reserved_usd',0)<3:raise ValueError('Final call requires its own fresh saved reservation')
        env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1')
        listed=subprocess.run([sys.executable,'-m','modal','app','list','--json'],capture_output=True,env=env,timeout=30,check=True)
        if any(int(item.get('tasks',0))>0 for item in json.loads(listed.stdout.decode('utf-8'))):raise ValueError('Another Modal task remains active')
        seal.write_once(local/'launch.json',{'stage':'spawning','run_id':plan['run_id']})
        call=evaluate.spawn(payload,plan,manifest)
        value={'stage':'spawned','run_id':plan['run_id'],'call_id':call.object_id}
        loader.atomic(local/'launch.json',value);print(json.dumps(value),flush=True)
    finally:os.close(fd);lock.unlink()
