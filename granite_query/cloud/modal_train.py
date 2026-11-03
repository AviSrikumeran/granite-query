"""Detached, bounded Granite LoRA smoke test with durable progress/artifacts."""
import json
from pathlib import Path
import time
import traceback
import modal

MODEL = 'ibm-granite/granite-4.2-3b'
REVISION = '4e9c275e232f10211ec88644d106a1f6a1b60e06'
app = modal.App('granite-query-training-smoke', include_source=False)
state = modal.Dict.from_name('granite-query-training-progress', create_if_missing=True)
artifacts = modal.Volume.from_name('granite-query-training-artifacts', create_if_missing=True)
image = (modal.Image.debian_slim(python_version='3.12')
    .pip_install('torch==2.6.0', 'transformers==4.57.1', 'peft==0.17.1',
                 'accelerate==1.10.1', 'safetensors==0.6.2')
    .env({'TOKENIZERS_PARALLELISM': 'false', 'HF_HUB_DISABLE_TELEMETRY': '1'})
    .add_local_python_source('cloud'))

@app.function(image=image, gpu='A100-80GB', cpu=4, memory=32768,
              timeout=900, startup_timeout=120, retries=0,
              max_containers=1, min_containers=0, buffer_containers=0,
              scaledown_window=2, volumes={'/artifacts': artifacts})
def train(rows: list[dict], plan: dict):
    started = time.monotonic()
    run_id = plan['run_id']
    folder = Path('/artifacts') / run_id
    folder.mkdir(parents=True, exist_ok=True)
    def checkpoint(stage, **details):
        record = {'run_id': run_id, 'stage': stage, 'elapsed_seconds': round(time.monotonic()-started, 3), **details}
        state[run_id] = record
        (folder / 'status.json').write_text(json.dumps(record, indent=2))
        artifacts.commit()
        print(json.dumps(record), flush=True)
    try:
        if plan['model'] != MODEL or plan['revision'] != REVISION or len(rows) != 15:
            raise ValueError('Unexpected smoke-test input')
        checkpoint('loading_model')
        import random
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM, set_seed
        from peft import LoraConfig, get_peft_model, PeftModel
        set_seed(42)
        tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION)
        model = AutoModelForCausalLM.from_pretrained(MODEL, revision=REVISION,
                    torch_dtype=torch.bfloat16, attn_implementation='sdpa').to('cuda')
        tokenizer.pad_token = tokenizer.eos_token
        model.config.use_cache = False
        train_rows = [r for r in rows if r['id'] in plan['train_ids']]
        dev_rows = [r for r in rows if r['id'] in plan['development_ids']]
        def prompt(question):
            return tokenizer.apply_chat_template([{'role': 'user', 'content':
                'Solve the math problem. Explain the calculation steps and finish with #### followed by the numeric final answer.\n\n' + question}],
                tokenize=False, add_generation_prompt=True, enable_thinking=False)
        def evaluate(label):
            model.eval()
            outputs = []
            for row in dev_rows:
                if time.monotonic()-started > 760:
                    raise TimeoutError('Application deadline before evaluation')
                inputs = tokenizer(prompt(row['prompt']), return_tensors='pt', add_special_tokens=False).to('cuda')
                before = time.monotonic()
                with torch.no_grad():
                    generated = model.generate(**inputs, max_new_tokens=192, do_sample=False,
                        use_cache=True, pad_token_id=tokenizer.pad_token_id)
                result = tokenizer.decode(generated[0, inputs['input_ids'].shape[1]:], skip_special_tokens=True)
                outputs.append({'id': row['id'], 'response': result, 'gold_answer': row['gold_answer'],
                    'generated_tokens': generated.shape[1]-inputs['input_ids'].shape[1],
                    'elapsed_seconds': time.monotonic()-before})
            (folder / (label + '.json')).write_text(json.dumps(outputs, indent=2))
            artifacts.commit()
            return outputs
        checkpoint('baseline_evaluation', development_count=len(dev_rows))
        baseline = evaluate('baseline')
        model = get_peft_model(model, LoraConfig(r=8, lora_alpha=16, lora_dropout=0.0,
            target_modules=['q_proj', 'v_proj'], bias='none', task_type='CAUSAL_LM'))
        trainable = [p for p in model.parameters() if p.requires_grad]
        before_weights = [p.detach().float().cpu().clone() for p in trainable]
        optimizer = torch.optim.AdamW(trainable, lr=1e-4)
        losses, token_count = [], 0
        checkpoint('training', steps=0, train_examples=len(train_rows), trainable_parameters=sum(p.numel() for p in trainable))
        model.train()
        for step, row in enumerate(train_rows):
            if time.monotonic()-started > 650:
                raise TimeoutError('Application deadline during training')
            prefix = tokenizer(prompt(row['prompt']), add_special_tokens=False)['input_ids']
            answer = tokenizer(row['response'] + tokenizer.eos_token, add_special_tokens=False)['input_ids']
            if len(prefix)+len(answer) > 1024:
                raise ValueError('Training example exceeds frozen context; do not silently truncate')
            ids = torch.tensor([prefix+answer], device='cuda')
            labels = torch.tensor([[-100]*len(prefix)+answer], device='cuda')
            optimizer.zero_grad(set_to_none=True)
            loss = model(input_ids=ids, labels=labels).loss
            if not torch.isfinite(loss):
                raise ValueError('Non-finite training loss')
            loss.backward()
            torch.nn.utils.clip_grad_norm_(trainable, 1.0)
            optimizer.step()
            token_count += len(answer)
            losses.append(float(loss.detach()))
            checkpoint('training', steps=step+1, total_steps=len(train_rows), last_loss=losses[-1], supervised_tokens=token_count)
        delta = sum(float((p.detach().float().cpu()-old).abs().sum()) for p, old in zip(trainable, before_weights))
        if delta <= 0:
            raise ValueError('Adapter parameters did not change')
        model.save_pretrained(folder / 'adapter')
        tokenizer.save_pretrained(folder / 'adapter')
        (folder / 'plan.json').write_text(json.dumps(plan, indent=2))
        artifacts.commit()
        checkpoint('adapter_saved', steps=len(losses), supervised_tokens=token_count, adapter_parameter_delta_l1=delta)
        del optimizer, before_weights, trainable
        base = model.unload()
        model = PeftModel.from_pretrained(base, folder / 'adapter')
        checkpoint('reloaded_evaluation')
        after = evaluate('after')
        result = {'run_id': run_id, 'stage': 'completed', 'model': MODEL, 'revision': REVISION,
            'steps': len(losses), 'losses': losses, 'supervised_tokens': token_count,
            'adapter_parameter_delta_l1': delta, 'baseline': baseline, 'after': after,
            'elapsed_seconds': time.monotonic()-started, 'held_out_test_used': False,
            'purpose': 'training/save/reload smoke test; not an accuracy claim'}
        (folder / 'result.json').write_text(json.dumps(result, indent=2))
        artifacts.commit()
        checkpoint('completed', steps=len(losses), supervised_tokens=token_count,
                   artifact_path=str(folder), adapter_parameter_delta_l1=delta)
        return result
    except Exception as exc:
        (folder / 'failure.txt').write_text(traceback.format_exc())
        checkpoint('failed', error_type=type(exc).__name__, error=str(exc))
        raise

@app.local_entrypoint()
def launch(folder: str):
    local = Path(folder)
    plan = json.loads((local / 'plan.json').read_text())
    if (local / 'launch.json').exists():
        raise RuntimeError('Launch record exists; reconcile it instead of relaunching')
    rows = [json.loads(line) for line in (local / 'training_input.jsonl').read_text(encoding='utf-8').splitlines()]
    # A prewritten reservation prevents automatic re-launch after an ambiguous interruption.
    (local / 'launch.json').write_text(json.dumps({'run_id': plan['run_id'], 'status': 'spawning'}))
    call = train.spawn(rows, plan)
    record = {'run_id': plan['run_id'], 'status': 'spawned', 'call_id': call.object_id}
    (local / 'launch.json').write_text(json.dumps(record, indent=2))
    print(json.dumps(record), flush=True)
