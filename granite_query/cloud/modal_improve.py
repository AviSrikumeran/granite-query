"""Bounded shared64 evaluation or full120 LoRA training on one GPU."""
import json
from pathlib import Path
import time
import traceback
import modal
from .modal_train import image,MODEL,REVISION,state,artifacts

app=modal.App('granite-query-improvement',include_source=False)

@app.function(image=image,gpu='A100-80GB',cpu=4,memory=32768,timeout=900,
    startup_timeout=120,retries=0,max_containers=1,min_containers=0,
    buffer_containers=0,scaledown_window=2,volumes={'/artifacts':artifacts})
def execute(data:dict,plan:dict):
    started=time.monotonic()
    folder=Path('/artifacts')/plan['run_id']
    folder.mkdir(parents=True,exist_ok=True)
    def checkpoint(stage,**details):
        s={'run_id':plan['run_id'],'stage':stage,'elapsed_seconds':round(time.monotonic()-started,3),**details}
        state[plan['run_id']]=s
        (folder/'status.json').write_text(json.dumps(s,indent=2))
        item=details.get('completed',details.get('steps'))
        if item is None or item%8==0 or stage in ('completed','failed'):
            artifacts.commit()
        print(json.dumps(s),flush=True)
    try:
        if plan['model']!=MODEL or plan['revision']!=REVISION or len(data['development'])!=64:
            raise ValueError('Unexpected frozen evaluation plan')
        import torch
        import importlib.metadata
        from transformers import AutoTokenizer,AutoModelForCausalLM,set_seed
        from peft import LoraConfig,get_peft_model,PeftModel
        set_seed(plan['seed'])
        checkpoint('loading_model')
        tokenizer=AutoTokenizer.from_pretrained(MODEL,revision=REVISION)
        base=AutoModelForCausalLM.from_pretrained(MODEL,revision=REVISION,
            torch_dtype=torch.bfloat16,attn_implementation='sdpa').to('cuda')
        tokenizer.pad_token=tokenizer.eos_token
        base.config.use_cache=False
        model=base
        resume_folder=Path('/artifacts')/plan['resume_from'] if plan.get('resume_from') else None
        if resume_folder:
            previous=json.loads((resume_folder/'plan.json').read_text())
            for key in ('model','revision','development_ids','max_new_tokens','seed','mode'):
                if previous[key]!=plan[key]:
                    raise ValueError('Resume would change frozen evaluation conditions')
        (folder/'plan.json').write_text(json.dumps(plan,indent=2))
        (folder/'packages.json').write_text(json.dumps({d.metadata['Name']:d.version for d in importlib.metadata.distributions()},indent=2))
        def prompt(q):
            return tokenizer.apply_chat_template([{'role':'user','content':
                'Solve the math problem. Explain only the necessary calculation steps concisely. Finish with #### followed by the numeric final answer.\n\n'+q}],
                tokenize=False,add_generation_prompt=True,enable_thinking=False)
        def evaluate(name):
            model.eval()
            prior=resume_folder/(name+'.json') if resume_folder else None
            rows=json.loads(prior.read_text()) if prior and prior.exists() else []
            completed_ids={r['id'] for r in rows}
            if len(completed_ids)!=len(rows) or not completed_ids.issubset(set(plan['development_ids'])):
                raise ValueError('Invalid prior evaluation records')
            for i,row in enumerate(data['development']):
                if row['id'] in completed_ids:
                    continue
                if time.monotonic()-started>820:
                    raise TimeoutError('Application evaluation deadline')
                inp=tokenizer(prompt(row['prompt']),return_tensors='pt',add_special_tokens=False).to('cuda')
                before=time.monotonic()
                with torch.no_grad():
                    out=model.generate(**inp,max_new_tokens=plan['max_new_tokens'],do_sample=False,
                        use_cache=True,pad_token_id=tokenizer.pad_token_id)
                ids=out[0,inp['input_ids'].shape[1]:]
                rows.append({'id':row['id'],'response':tokenizer.decode(ids,skip_special_tokens=True),
                    'gold_answer':row['gold_answer'],'generated_tokens':len(ids),
                    'truncated':len(ids)>=plan['max_new_tokens'] and int(ids[-1])!=tokenizer.eos_token_id,
                    'elapsed_seconds':time.monotonic()-before})
                (folder/(name+'.json')).write_text(json.dumps(rows,indent=2))
                checkpoint(name+'_evaluation',completed=len(rows),total=64)
            (folder/(name+'.json')).write_text(json.dumps(rows,indent=2))
            artifacts.commit()
            return rows
        evaluations={}
        supervised_tokens=0
        losses=[]
        if plan['mode']=='evaluate_saved':
            evaluations['baseline']=evaluate('baseline')
            for name,adapter_name in [('ranked32','ranked_adapter'),('random32','random_adapter')]:
                model=PeftModel.from_pretrained(base,Path('/artifacts')/plan['adapter_source']/adapter_name)
                evaluations[name]=evaluate(name)
                base=model.unload()
                model=base
        elif plan['mode']=='train_full120':
            training={r['id']:r for r in data['training']}
            if len(training)!=120 or set(training)&set(plan['development_ids']):
                raise ValueError('Training/evaluation isolation failed')
            model=get_peft_model(base,LoraConfig(r=8,lora_alpha=16,lora_dropout=0.0,
                target_modules=['q_proj','v_proj'],bias='none',task_type='CAUSAL_LM'))
            parameters=[p for p in model.parameters() if p.requires_grad]
            optimizer=torch.optim.AdamW(parameters,lr=plan['learning_rate'])
            import random
            order=list(plan['train_ids'])
            random.Random(plan['seed']).shuffle(order)
            model.train()
            for step,row_id in enumerate(order):
                if time.monotonic()-started>600:
                    raise TimeoutError('Application training deadline')
                row=training[row_id]
                prefix=tokenizer(prompt(row['prompt']),add_special_tokens=False)['input_ids']
                answer=tokenizer(row['response']+tokenizer.eos_token,add_special_tokens=False)['input_ids']
                if len(prefix)+len(answer)>plan['context_limit']:
                    raise ValueError('Example exceeds frozen context: '+row_id)
                ids=torch.tensor([prefix+answer],device='cuda')
                labels=torch.tensor([[-100]*len(prefix)+answer],device='cuda')
                optimizer.zero_grad(set_to_none=True)
                loss=model(input_ids=ids,labels=labels).loss
                if not torch.isfinite(loss):
                    raise ValueError('Non-finite loss')
                loss.backward()
                torch.nn.utils.clip_grad_norm_(parameters,1.0)
                optimizer.step()
                supervised_tokens+=len(answer)
                losses.append(float(loss.detach()))
                checkpoint('full120_training',steps=step+1,total_steps=120,supervised_tokens=supervised_tokens,last_loss=losses[-1])
            adapter=folder/'adapter'
            model.save_pretrained(adapter)
            tokenizer.save_pretrained(adapter)
            artifacts.commit()
            del optimizer,parameters
            base=model.unload()
            model=PeftModel.from_pretrained(base,adapter)
            evaluations['full120']=evaluate('full120')
        else:
            raise ValueError('Unknown mode')
        result={'run_id':plan['run_id'],'stage':'completed','evaluations':evaluations,
            'supervised_tokens':supervised_tokens,'losses':losses,'plan':plan,
            'elapsed_seconds':time.monotonic()-started,'held_out_test_used':False}
        (folder/'result.json').write_text(json.dumps(result,indent=2))
        checkpoint('completed',evaluations_completed=len(evaluations))
        return result
    except Exception as exc:
        (folder/'failure.txt').write_text(traceback.format_exc())
        checkpoint('failed',error_type=type(exc).__name__,error=str(exc))
        raise

@app.local_entrypoint()
def launch(folder:str):
    local=Path(folder)
    if (local/'launch.json').exists():
        raise RuntimeError('Existing launch must be reconciled before retrying')
    plan=json.loads((local/'plan.json').read_text())
    data=json.loads((local/'input.json').read_text())
    (local/'launch.json').write_text(json.dumps({'run_id':plan['run_id'],'status':'spawning'}))
    call=execute.spawn(data,plan)
    record={'run_id':plan['run_id'],'status':'spawned','call_id':call.object_id}
    (local/'launch.json').write_text(json.dumps(record,indent=2))
    print(json.dumps(record),flush=True)
