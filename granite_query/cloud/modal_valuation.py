"""One fresh-base valuation arm per bounded call; exact tokens and batched eval."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import modal
from .modal_train import image, MODEL, REVISION, state, artifacts
from .valuation_contract import validate_arm, window_labels, trim_generation

app = modal.App('granite-query-token-valuation', include_source=False)
PREFIX = ('Solve the math problem. Explain only the necessary calculation steps concisely. '
          'Finish with #### followed by the numeric final answer.\n\n')


@app.function(image=image, gpu='A100-80GB', cpu=4, memory=32768, timeout=1800,
    startup_timeout=120, retries=0, max_containers=1, min_containers=0,
    buffer_containers=0, scaledown_window=2, volumes={'/artifacts':artifacts})
def execute(data:dict, plan:dict):
    started = time.monotonic()
    folder = Path('/artifacts')/plan['run_id']
    folder.mkdir(parents=True, exist_ok=True)
    def checkpoint(stage, *, commit=False, **details):
        value = dict(run_id=plan['run_id'], stage=stage,
                     elapsed_seconds=round(time.monotonic()-started,3), **details)
        state[plan['run_id']] = value
        (folder/'status.json').write_text(json.dumps(value,indent=2))
        if commit:
            artifacts.commit()
        print(json.dumps(value),flush=True)
    try:
        if plan['model'] != MODEL or plan['revision'] != REVISION:
            raise ValueError('Pinned checkpoint mismatch')
        dev = data['development']
        dev_ids = [row['id'] for row in dev]
        if not dev or len(dev)>256 or len(set(dev_ids)) != len(dev_ids) or dev_ids != plan['development_ids']:
            raise ValueError('Frozen evaluation IDs differ')
        if not 1 <= plan['evaluation_batch_size'] <= 16:
            raise ValueError('Unsupported evaluation batch size')
        resume = Path('/artifacts')/plan['resume_from'] if plan.get('resume_from') else None
        if resume and json.loads((resume/'plan.json').read_text())['protocol_hash'] != plan['protocol_hash']:
            raise ValueError('Resume would change frozen protocol')
        import importlib.metadata
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, set_seed
        from peft import LoraConfig, get_peft_model, PeftModel
        set_seed(plan['seed'])
        checkpoint('loading_model',commit=True)
        tokenizer = AutoTokenizer.from_pretrained(MODEL,revision=REVISION)
        def render(question):
            return tokenizer.apply_chat_template([{'role':'user','content':PREFIX+question}],
                tokenize=False,add_generation_prompt=True,enable_thinking=False)
        mode = plan.get('mode','train_evaluate')
        arm = data.get('arm')
        if mode == 'train_evaluate':
            rows = validate_arm(arm)
            if set(rows)&set(dev_ids) or arm['tokenizer']['model'] != MODEL or arm['tokenizer']['revision'] != REVISION:
                raise ValueError('Training/evaluation isolation or tokenizer mismatch')
            for row in rows.values():
                prefix = tokenizer(render(row['prompt']),add_special_tokens=False)['input_ids']
                answer = tokenizer(row['response']+tokenizer.eos_token,add_special_tokens=False)['input_ids']
                if prefix+answer != row['input_ids'] or len(prefix) != row['prefix_tokens']:
                    raise ValueError('Prepared tokens differ from pinned runtime tokenizer')
                if hashlib.sha256(row['response'].encode()).hexdigest() != row['raw_response_sha256']:
                    raise ValueError('Teacher response changed')
                if len(row['input_ids']) > plan['context_limit']:
                    raise ValueError('Context limit exceeded')
        elif mode != 'evaluate_saved':
            raise ValueError('Unknown worker mode')
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.padding_side = 'left'
        base = AutoModelForCausalLM.from_pretrained(MODEL,revision=REVISION,
            torch_dtype=torch.bfloat16,attn_implementation='sdpa').to('cuda')
        base.config.use_cache = False
        (folder/'plan.json').write_text(json.dumps(plan,indent=2))
        (folder/'packages.json').write_text(json.dumps({d.metadata['Name']:d.version for d in importlib.metadata.distributions()},indent=2))
        student_probe = None
        probes = data.get('probe_candidates',[])
        if probes:
            if len(probes)>512 or len({r['id'] for r in probes})!=len(probes) or {r['id'] for r in probes}&set(dev_ids):
                raise ValueError('Invalid student-scoring candidate pool')
            previous_scores = resume/'student_scores.json' if resume else None
            scores = json.loads(previous_scores.read_text()).get('scores',[]) if previous_scores and previous_scores.exists() else []
            scored = {r['id'] for r in scores}
            if len(scored)!=len(scores) or not scored.issubset({r['id'] for r in probes}):
                raise ValueError('Invalid saved student scores')
            base.eval()
            for row in probes:
                if row['id'] in scored:
                    continue
                # This optional diagnostic must not consume the training/eval window.
                # Partial scores remain explicitly incomplete and cannot be presented
                # as a completed candidate valuation table.
                if time.monotonic()-started>300:
                    break
                prefix = row['prefix_tokens']
                if not 0<prefix<len(row['input_ids'])<=plan['context_limit']:
                    raise ValueError('Student-scoring context invalid')
                ids = torch.tensor([row['input_ids']],device='cuda')
                labels = torch.tensor([[-100]*prefix+row['input_ids'][prefix:]],device='cuda')
                with torch.no_grad():
                    loss = base(input_ids=ids,labels=labels).loss
                if not torch.isfinite(loss):
                    raise ValueError('Non-finite candidate response NLL')
                scores.append({'id':row['id'],'normalized_response_nll':float(loss.detach()),
                    'response_tokens':len(row['input_ids'])-prefix,
                    'raw_response_sha256':row['raw_response_sha256']})
                if len(scores)%64==0:
                    (folder/'student_scores.json').write_text(json.dumps({'scores':scores,'complete':False},indent=2))
                    checkpoint('student_scoring',commit=True,completed=len(scores),total=len(probes))
            student_probe={'scores':scores,'complete':len(scores)==len(probes),
                'completed':len(scores),'requested':len(probes),
                'interpretation':'Untouched student mean teacher-forced response NLL; difficulty proxy, not causal training value or model answer correctness'}
            (folder/'student_scores.json').write_text(json.dumps(student_probe,indent=2))
            artifacts.commit()
        adapter = folder/'adapter'
        supervised = 0
        history = []
        if mode == 'train_evaluate':
            # Optional baseline scoring must not change adapter initialization.
            set_seed(plan['seed'])
            model = get_peft_model(base,LoraConfig(r=8,lora_alpha=16,lora_dropout=0.0,
                target_modules=['q_proj','v_proj'],bias='none',task_type='CAUSAL_LM'))
            parameters = [p for p in model.parameters() if p.requires_grad]
            optimizer = torch.optim.AdamW(parameters,lr=plan['learning_rate'])
            first_update = 0
            if resume and (resume/'optimizer_state.pt').exists():
                model = PeftModel.from_pretrained(model.unload(),resume/'adapter',is_trainable=True)
                parameters = [p for p in model.parameters() if p.requires_grad]
                optimizer = torch.optim.AdamW(parameters,lr=plan['learning_rate'])
                saved = torch.load(resume/'optimizer_state.pt',map_location='cuda',weights_only=False)
                optimizer.load_state_dict(saved['optimizer'])
                first_update, supervised, history = saved['updates'], saved['supervised_tokens'], saved['history']
                if first_update > len(arm['updates']) or supervised != first_update*arm['tokens_per_update']:
                    raise ValueError('Invalid training resume checkpoint')
            def save_training(completed):
                model.save_pretrained(adapter)
                tokenizer.save_pretrained(adapter)
                torch.save({'optimizer':optimizer.state_dict(),'updates':completed,
                    'supervised_tokens':supervised,'history':history},folder/'optimizer_state.pt')
                artifacts.commit()
            model.train()
            for update in arm['updates'][first_update:]:
                if time.monotonic()-started > 1400:
                    save_training(update['index'])
                    raise TimeoutError('Training guard; recover saved optimizer/adapter before any retry')
                optimizer.zero_grad(set_to_none=True)
                weighted_loss = 0.0
                for window in update['microbatches']:
                    row = rows[window['id']]
                    ids = torch.tensor([row['input_ids']],device='cuda')
                    labels = torch.tensor([window_labels(row,window)],device='cuda')
                    mask = torch.tensor([row['attention_mask']],device='cuda')
                    loss = model(input_ids=ids,attention_mask=mask,labels=labels).loss
                    if not torch.isfinite(loss):
                        raise ValueError('Non-finite training loss')
                    # Model loss is a mean over unmasked answer tokens. Weighting gives
                    # exactly the mean over the complete effective supervised-token batch.
                    (loss*window['loss_weight']).backward()
                    weighted_loss += float(loss.detach())*window['loss_weight']
                torch.nn.utils.clip_grad_norm_(parameters,1.0)
                optimizer.step()
                supervised += update['supervised_tokens']
                history.append(weighted_loss)
                completed = update['index']+1
                if completed%4 == 0 or completed == len(arm['updates']):
                    save_training(completed)
                checkpoint('training',updates=completed,total_updates=len(arm['updates']),
                    supervised_tokens=supervised,weighted_loss=weighted_loss)
            if supervised != arm['token_budget']:
                raise ValueError('Actual supervised-token budget differs')
            save_training(len(arm['updates']))
            del optimizer,parameters
            base = model.unload()
            model = PeftModel.from_pretrained(base,adapter)
            checkpoint('adapter_saved',commit=True,supervised_tokens=supervised,updates=len(history))
        else:
            model = PeftModel.from_pretrained(base,Path('/artifacts')/plan['adapter_from']) if plan.get('adapter_from') else base
        model.eval()
        prior = resume/'evaluation.json' if resume else None
        evaluations = json.loads(prior.read_text()) if prior and prior.exists() else []
        done = {row['id'] for row in evaluations}
        if len(done) != len(evaluations) or not done.issubset(set(dev_ids)):
            raise ValueError('Invalid previous evaluation rows')
        pending = [row for row in dev if row['id'] not in done]
        eos = model.generation_config.eos_token_id
        eos_ids = list(eos) if isinstance(eos,(list,tuple)) else [eos]
        eos_ids.append(tokenizer.eos_token_id)
        batch_size = plan['evaluation_batch_size']
        for offset in range(0,len(pending),batch_size):
            if time.monotonic()-started > 1600:
                raise TimeoutError('Evaluation guard; adapter and completed batches preserved')
            batch = pending[offset:offset+batch_size]
            inputs = tokenizer([render(row['prompt']) for row in batch],padding=True,
                return_tensors='pt',add_special_tokens=False).to('cuda')
            width = inputs['input_ids'].shape[1]
            torch.cuda.synchronize()
            before = time.monotonic()
            with torch.no_grad():
                outputs = model.generate(**inputs,max_new_tokens=plan['max_new_tokens'],do_sample=False,
                    use_cache=True,pad_token_id=tokenizer.pad_token_id)
            torch.cuda.synchronize()
            elapsed = time.monotonic()-before
            for row,output in zip(batch,outputs):
                tail,truncated = trim_generation(output[width:].tolist(),eos_ids,plan['max_new_tokens'])
                evaluations.append({'id':row['id'],'gold_answer':row['gold_answer'],
                    'response':tokenizer.decode(tail,skip_special_tokens=True),
                    'generated_tokens':len(tail),'truncated':truncated,
                    'elapsed_seconds':elapsed/len(batch),'batch_elapsed_seconds':elapsed,
                    'batch_size':len(batch),'latency_measurement':'amortized batched GPU wall time; not single-request latency'})
            (folder/'evaluation.json').write_text(json.dumps(evaluations,indent=2))
            checkpoint('evaluation',commit=True,completed=len(evaluations),total=len(dev))
        ordered = {row['id']:row for row in evaluations}
        result = {'run_id':plan['run_id'],'stage':'completed','arm':arm['arm'] if arm else 'evaluation_only',
            'evaluations':{plan.get('checkpoint_name',plan.get('arm','checkpoint')):[ordered[key] for key in dev_ids]},
            'supervised_tokens':supervised,'optimizer_updates':len(history),'weighted_losses':history,
            'elapsed_seconds':time.monotonic()-started,'plan':plan,
            'held_out_test_used':plan.get('evaluation_kind') == 'final_test',
            'student_probe':student_probe,
            'latency_measurement':'batched amortized GPU timings, not comparable directly with serial latency'}
        (folder/'result.json').write_text(json.dumps(result,indent=2))
        checkpoint('completed',commit=True,supervised_tokens=supervised,optimizer_updates=len(history),evaluation_count=len(dev))
        return result
    except Exception as exc:
        (folder/'failure.txt').write_text(traceback.format_exc())
        checkpoint('failed',commit=True,error_type=type(exc).__name__,error=str(exc))
        raise


@app.local_entrypoint()
def launch(folder:str):
    local = Path(folder)
    runtime = Path(__file__).resolve().parent/'runs/supervisor'
    launch_lock = runtime/'gpu_launch.lock'
    fd = os.open(launch_lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    try:
        os.write(fd,str(os.getpid()).encode())
        if (local/'launch.json').exists():
            raise RuntimeError('Existing launch record: reconcile instead of duplicating')
        plan = json.loads((local/'plan.json').read_text())
        data_bytes = (local/'input.json').read_bytes()
        if hashlib.sha256(data_bytes).hexdigest() != plan['input_sha256']:
            raise ValueError('Frozen worker input changed')
        ledger = json.loads((runtime/'budget.json').read_text())
        job = next((j for j in ledger['jobs'] if j['run_id'] == plan['run_id'] and j.get('service') == 'modal'),None)
        if not job or job['reserved_usd'] < 3 or job.get('status') != 'reserved':
            raise RuntimeError('A separately approved $3 Modal reservation is required before launch')
        env = dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1')
        listed = subprocess.run([sys.executable,'-m','modal','app','list','--json'],
            capture_output=True,env=env,timeout=30,check=True)
        apps = json.loads(listed.stdout.decode('utf-8'))
        if any(str(item.get('tasks','0')).isdigit() and int(item.get('tasks','0'))>0 for item in apps):
            raise RuntimeError('Another Modal task is active; preserve the one-GPU policy and wait')
        (local/'launch.json').write_text(json.dumps({'run_id':plan['run_id'],'status':'spawning'}))
        call = execute.spawn(json.loads(data_bytes),plan)
        value = {'run_id':plan['run_id'],'status':'spawned','call_id':call.object_id}
        (local/'launch.json').write_text(json.dumps(value,indent=2))
        print(json.dumps(value),flush=True)
    finally:
        os.close(fd)
        launch_lock.unlink()
