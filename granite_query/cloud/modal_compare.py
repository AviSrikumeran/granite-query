"""Single-GPU sequential ranked/random pilot from the same frozen base weights."""
import json
from pathlib import Path
import time
import traceback
import modal
from .modal_train import image, MODEL, REVISION, state, artifacts

app=modal.App('granite-query-ranked-random',include_source=False)

@app.function(image=image,gpu='A100-80GB',cpu=4,memory=32768,timeout=900,
    startup_timeout=120,retries=0,max_containers=1,min_containers=0,
    buffer_containers=0,scaledown_window=2,volumes={'/artifacts':artifacts})
def compare(data:dict,plan:dict):
    started=time.monotonic()
    folder=Path('/artifacts')/plan['run_id']
    folder.mkdir(parents=True,exist_ok=True)
    def checkpoint(stage,**details):
        s={'run_id':plan['run_id'],'stage':stage,'elapsed_seconds':round(time.monotonic()-started,3),**details}
        state[plan['run_id']]=s
        (folder/'status.json').write_text(json.dumps(s,indent=2))
        artifacts.commit()
        print(json.dumps(s),flush=True)
    try:
        if plan['model']!=MODEL or plan['revision']!=REVISION:
            raise ValueError('Checkpoint mismatch')
        train_ids={r['id'] for r in data['training']}
        dev_ids={r['id'] for r in data['development']}
        if train_ids&dev_ids or len(dev_ids)!=16 or any(len(v)!=32 for v in plan['arms'].values()):
            raise ValueError('Split or arm-size mismatch')
        checkpoint('loading_model')
        import importlib.metadata
        import torch
        from transformers import AutoTokenizer,AutoModelForCausalLM,set_seed
        from peft import LoraConfig,get_peft_model,PeftModel
        (folder/'packages.json').write_text(json.dumps({d.metadata['Name']:d.version for d in importlib.metadata.distributions()},indent=2))
        (folder/'plan.json').write_text(json.dumps(plan,indent=2))
        set_seed(plan['seed'])
        tokenizer=AutoTokenizer.from_pretrained(MODEL,revision=REVISION)
        base=AutoModelForCausalLM.from_pretrained(MODEL,revision=REVISION,
            torch_dtype=torch.bfloat16,attn_implementation='sdpa').to('cuda')
        tokenizer.pad_token=tokenizer.eos_token
        base.config.use_cache=False
        model=base
        def prompt(question):
            return tokenizer.apply_chat_template([{'role':'user','content':
                'Solve the math problem. Explain only the necessary calculation steps concisely. Finish with #### followed by the numeric final answer.\n\n'+question}],
                tokenize=False,add_generation_prompt=True,enable_thinking=False)
        encoded={}
        for row in data['training']:
            prefix=tokenizer(prompt(row['prompt']),add_special_tokens=False)['input_ids']
            answer=tokenizer(row['response']+tokenizer.eos_token,add_special_tokens=False)['input_ids']
            if len(prefix)+len(answer)>plan['context_limit']:
                raise ValueError('Selected example exceeds context: '+row['id'])
            encoded[row['id']]=(prefix,answer)
        def evaluate(label):
            model.eval()
            results=[]
            for i,row in enumerate(data['development']):
                if time.monotonic()-started>820:
                    raise TimeoutError('Application deadline before next evaluation item')
                inputs=tokenizer(prompt(row['prompt']),return_tensors='pt',add_special_tokens=False).to('cuda')
                before=time.monotonic()
                with torch.no_grad():
                    output=model.generate(**inputs,max_new_tokens=plan['max_new_tokens'],do_sample=False,
                        use_cache=True,pad_token_id=tokenizer.pad_token_id)
                ids=output[0,inputs['input_ids'].shape[1]:]
                results.append({'id':row['id'],'response':tokenizer.decode(ids,skip_special_tokens=True),
                    'gold_answer':row['gold_answer'],'generated_tokens':len(ids),
                    'truncated':len(ids)>=plan['max_new_tokens'] and int(ids[-1])!=tokenizer.eos_token_id,
                    'elapsed_seconds':time.monotonic()-before})
                (folder/(label+'.json')).write_text(json.dumps(results,indent=2))
                checkpoint(label,completed=i+1,total=len(data['development']))
            return results
        baseline=evaluate('baseline_evaluation')
        arms={}
        for arm in ('ranked','random'):
            set_seed(plan['seed'])
            model=get_peft_model(base,LoraConfig(r=plan['lora_r'],lora_alpha=plan['lora_alpha'],
                lora_dropout=0.0,target_modules=['q_proj','v_proj'],bias='none',task_type='CAUSAL_LM'))
            parameters=[p for p in model.parameters() if p.requires_grad]
            optimizer=torch.optim.AdamW(parameters,lr=plan['learning_rate'])
            losses=[]
            supervised_tokens=0
            model.train()
            for step,row_id in enumerate(plan['arms'][arm]):
                if time.monotonic()-started>680:
                    raise TimeoutError('Application deadline during training')
                prefix,answer=encoded[row_id]
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
                checkpoint(arm+'_training',steps=step+1,total_steps=32,supervised_tokens=supervised_tokens,last_loss=losses[-1])
            adapter=folder/(arm+'_adapter')
            model.save_pretrained(adapter)
            tokenizer.save_pretrained(adapter)
            artifacts.commit()
            del optimizer,parameters
            base=model.unload()
            model=PeftModel.from_pretrained(base,adapter)
            evaluation=evaluate(arm+'_evaluation')
            arms[arm]={'losses':losses,'steps':32,'supervised_tokens':supervised_tokens,'evaluation':evaluation}
            (folder/(arm+'_result.json')).write_text(json.dumps(arms[arm],indent=2))
            artifacts.commit()
            base=model.unload()
            model=base
        result={'run_id':plan['run_id'],'stage':'completed','baseline':baseline,'arms':arms,
            'plan':plan,'elapsed_seconds':time.monotonic()-started,'held_out_test_used':False}
        (folder/'result.json').write_text(json.dumps(result,indent=2))
        checkpoint('completed',arms_completed=2,development_count=16)
        return result
    except Exception as exc:
        (folder/'failure.txt').write_text(traceback.format_exc())
        checkpoint('failed',error_type=type(exc).__name__,error=str(exc))
        raise

@app.local_entrypoint()
def launch(folder:str):
    local=Path(folder)
    if (local/'launch.json').exists():
        raise RuntimeError('Existing launch record must be reconciled, not overwritten')
    plan=json.loads((local/'plan.json').read_text())
    data=json.loads((local/'input.json').read_text())
    (local/'launch.json').write_text(json.dumps({'run_id':plan['run_id'],'status':'spawning'}))
    call=compare.spawn(data,plan)
    result={'run_id':plan['run_id'],'status':'spawned','call_id':call.object_id}
    (local/'launch.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result),flush=True)
