"""Unlaunched bounded scaled-final worker; metadata/model checks precede input.

The controller owns funding and the global launch lock. This module does not
deploy an endpoint, fetch official data, reserve funds or retry a dispatched job.
"""
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import modal
from .modal_train import image, artifacts, state
from . import final_scale_execution as execution
from . import final_scale_artifacts as artifact_checks
from . import granite_lora_layout as layout
from . import final_scale_receipts as receipt_api

ROOT = Path(__file__).resolve().parent
app = modal.App('granite-query-scaled-final', include_source=False)


def _safe(root, relative):
    execution.volume_path(relative)
    root = Path(root).absolute(); path = root/relative
    artifact_checks._no_links(path)
    result = path.resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError('Worker artifact path escaped its explicit root')
    return result


def _replace(source, target):
    for attempt in range(4):
        try:
            source.replace(target); return
        except PermissionError:
            if attempt == 3: raise
            time.sleep(.05*(2**attempt))


def _write(path, value, *, immutable=True):
    artifact_checks._no_links(path)
    raw = execution.payload_bytes(value)
    if immutable and path.exists():
        if path.read_bytes() != raw:
            raise ValueError('Existing immutable worker receipt differs')
        return hashlib.sha256(raw).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.pending')
    artifact_checks._no_links(temporary)
    if immutable and temporary.exists():
        if temporary.read_bytes() != raw:
            raise ValueError('Ambiguous worker temporary must not be overwritten')
    else:
        with temporary.open('xb' if immutable else 'wb') as handle:
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
    _replace(temporary, path)
    return hashlib.sha256(raw).hexdigest()


class Runtime:
    """Actual remote I/O and CUDA boundary; local tests substitute it entirely."""
    def __init__(self, root=Path('/artifacts')):
        self.root = root; self.started = time.monotonic()
        self.call_id = modal.current_function_call_id()

    def elapsed(self):
        return time.monotonic()-self.started

    def begin(self, intent, authorization, launch):
        self.intent = intent
        if not state.put('final-scale-owner:'+intent['run_id'], {'call_id': self.call_id,
                'intent_sha256': intent['intent_sha256'], 'remote_directory': execution.remote_directory(intent)}, skip_if_exists=True):
            raise ValueError('Existing final attempt owns this run; never repeat it')
        self.folder = _safe(self.root, execution.remote_directory(intent))
        self.folder.mkdir(parents=True, exist_ok=True)
        _write(self.folder/'intent.json', intent); _write(self.folder/'authorization.json', authorization)
        _write(self.folder/'launch.json', launch); artifacts.commit()

    def status(self, stage, **details):
        value = dict(stage=stage, run_id=self.intent['run_id'], call_id=self.call_id,
            intent_sha256=self.intent['intent_sha256'], elapsed_seconds=round(self.elapsed(), 3), **details)
        _write(self.folder/'status.json', value, immutable=False)
        state[self.intent['run_id']] = value; artifacts.commit()

    def verify_assets(self, authorization):
        p = authorization['sealed']['contract']['protocol']
        artifact_checks.verify_packaged_sources(ROOT, p['source_hashes'])
        config = authorization['model_config']; config_path = _safe(self.root, config['volume_path'])
        self.config_path = config_path
        if config_path.stat().st_size != config['bytes']:
            raise ValueError('Staged model configuration byte count differs')
        self.adapter = _safe(self.root, authorization['adapter_path'])
        verified = artifact_checks.verify_adapter(self.adapter,
            authorization['sealed']['checkpoint']['adapter_files_sha256'], model_config_path=config_path,
            expected_model_config_sha256=config['sha256'], key_format='peft_saved', allowed_root=self.root)
        _write(self.folder/'artifact_verification.json', verified); artifacts.commit()

    def load_model(self, authorization, checkpoint, seed):
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM, set_seed
        from peft import PeftModel
        from safetensors.torch import load_file
        torch.set_num_threads(4); set_seed(seed)
        p = authorization['sealed']['contract']['protocol']
        self.tokenizer = AutoTokenizer.from_pretrained(p['base']['model'], revision=p['base']['revision'], trust_remote_code=False)
        self.tokenizer.pad_token = self.tokenizer.eos_token; self.tokenizer.padding_side = 'left'
        base = AutoModelForCausalLM.from_pretrained(p['base']['model'], revision=p['base']['revision'],
            torch_dtype=torch.bfloat16, attn_implementation='sdpa', trust_remote_code=False).to('cuda')
        config = base.config.to_dict(); layout.validate_config(config)
        adapter_config, _ = artifact_checks._read_json(self.adapter/'adapter_config.json')
        loaded = PeftModel.from_pretrained(base, self.adapter, is_trainable=False)
        parameters = {name: parameter for name, parameter in loaded.named_parameters() if '.lora_' in name}
        verified = layout.validate_layout({name: list(parameter.shape) for name, parameter in parameters.items()},
            config, adapter_config, key_format='runtime_default')
        saved = load_file(str(self.adapter/'adapter_model.safetensors'), device='cpu')
        layout.validate_layout({name: list(tensor.shape) for name, tensor in saved.items()},
            config, adapter_config, key_format='peft_saved')
        for name, tensor in saved.items():
            runtime_name = name[:-len('.weight')]+'.default.weight'
            actual = parameters[runtime_name].detach().cpu()
            if not torch.isfinite(actual).all() or not torch.isfinite(tensor).all() or not torch.equal(actual, tensor.to(dtype=actual.dtype)):
                raise ValueError('Runtime PEFT parameters differ from sealed tensor values')
        del saved, parameters
        artifact_checks.verify_adapter(self.adapter, authorization['sealed']['checkpoint']['adapter_files_sha256'],
            model_config_path=self.config_path, expected_model_config_sha256=authorization['model_config']['sha256'],
            key_format='peft_saved', allowed_root=self.root)
        if checkpoint == 'base':
            self.model = loaded.unload()
            if any('.lora_' in name for name, _ in self.model.named_parameters()) or any(hasattr(module, 'lora_A') for module in self.model.modules()):
                raise ValueError('Baseline still contains an active adapter')
        else:
            self.model = loaded
        self.model.eval(); self.prefix = p['inference']['user_prefix']
        eos = self.model.generation_config.eos_token_id
        self.eos = list(eos) if isinstance(eos, (tuple, list)) else [eos]
        self.eos = sorted({int(n) for n in self.eos+[self.tokenizer.eos_token_id] if n is not None})
        if self.tokenizer.eos_token_id != 100257:
            raise ValueError('Pinned tokenizer EOS differs')
        _write(self.folder/'runtime_model_verification.json', dict(verified, runtime_peft_load_verified=True,
            runtime_adapter_values_match_sealed_file=True, baseline_adapter_unloaded=checkpoint == 'base'))
        artifacts.commit()

    def read_input(self, descriptor):
        path = _safe(self.root, descriptor['volume_path'])
        if not path.is_file() or path.stat().st_size != descriptor['bytes'] or path.stat().st_size > execution.MAX_INPUT_BYTES:
            raise ValueError('Staged input file byte bound differs')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != descriptor['sha256']:
            raise ValueError('Staged input file hash differs')
        return json.loads(raw)

    def render(self, row):
        return self.tokenizer.apply_chat_template([{'role': 'user', 'content': self.prefix+row['prompt']}],
            tokenize=False, add_generation_prompt=True, enable_thinking=False)

    def input_counts(self, rows):
        return [len(self.tokenizer(self.render(row), add_special_tokens=False)['input_ids']) for row in rows]

    def generate(self, rows):
        import torch
        inputs = self.tokenizer([self.render(row) for row in rows], padding=True, return_tensors='pt', add_special_tokens=False).to('cuda')
        if inputs['input_ids'].shape[1] > 1536:
            raise ValueError('Actual generated subset exceeds the frozen input limit')
        width = inputs['input_ids'].shape[1]
        torch.cuda.synchronize(); before = time.monotonic()
        with torch.no_grad():
            output = self.model.generate(**inputs, max_new_tokens=512, do_sample=False, use_cache=True,
                pad_token_id=self.tokenizer.pad_token_id)
        torch.cuda.synchronize()
        return [row[width:].tolist() for row in output], time.monotonic()-before

    def decode(self, ids):
        return self.tokenizer.decode(ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)

    def write_raw(self, start, value):
        result = _write(self.folder/'raw'/f'batch{start:04d}.json', value)
        artifacts.commit(); return result

    def write_batch(self, start, value):
        _write(self.folder/'batches'/f'batch{start:04d}.json', value); artifacts.commit()

    def finish(self, result):
        if result['worker_terminal'] is not None:
            _write(self.folder/'worker_terminal.json', result['worker_terminal'])
        _write(self.folder/'result.json', result); artifacts.commit()


def run_shard(intent, input_descriptor, authorization, *, runtime):
    """Testable worker orchestration; no input bytes before verified PEFT load."""
    execution.validate_remote_metadata(intent, input_descriptor, authorization)
    launch = execution.launch_receipt(intent, runtime.call_id)
    runtime.begin(intent, authorization, launch)
    context = None; batches = []; prefix = []; raw_pending = None; stage = 'failed'; error_type = None
    try:
        runtime.status('verifying_sources_and_adapter')
        runtime.verify_assets(authorization)
        runtime.status('loading_model')
        runtime.load_model(authorization, intent['checkpoint'], intent['seed'])
        payload = runtime.read_input(input_descriptor)
        context = execution.validate_inputs(intent, authorization, payload)
        prefix = context['prefix_rows']; retained = len(prefix)
        for start in range(intent['start']+retained, intent['stop'], 8):
            if runtime.elapsed() > 1600:
                stage = 'timed_out'; break
            rows = context['rows'][start-intent['start']:min(start+8, intent['stop'])-intent['start']]
            counts = runtime.input_counts(rows)
            if len(counts) != len(rows) or any(type(n) is not int or n < 1 for n in counts):
                raise ValueError('Tokenizer did not retain every logical row')
            eligible = [row for row, count in zip(rows, counts) if count <= 1536]
            runtime.status('generating_batch', completed=retained, requested=intent['count'], global_start=start,
                actual_generation_batch_size=len(eligible))
            failed = False; tokens = []; elapsed = 0
            if eligible:
                before = time.monotonic()
                try:
                    tokens, elapsed = runtime.generate(eligible)
                except Exception as error:
                    failed = True; error_type = type(error).__name__; elapsed = time.monotonic()-before
            raw = {key: intent[key] for key in receipt_api.IDENTITY_FIELDS}
            raw.update(call_id=launch['call_id'], launch_sha256=launch['launch_sha256'], start=start,
                stop=start+len(rows), count=len(rows), question_ids=[r['id'] for r in rows], input_tokens=counts,
                generated_ids=tokens, generation_elapsed_seconds=elapsed, eos_token_ids=list(runtime.eos), generation_failed=failed)
            raw_pending = raw
            raw_sha = runtime.write_raw(start, raw)  # Exact tokens are durable BEFORE decode/derivation.
            batch = execution.derive_raw_batch(intent, launch, raw, context['binding'], runtime.decode)
            if batch['raw_batch_sha256'] != raw_sha:
                raise ValueError('Derived batch no longer matches its durable raw token receipt')
            receipt_api.validate_batch(context['contract'], context['binding'], batch)
            runtime.write_batch(start, batch)
            batches.append(batch); retained += len(rows); raw_pending = None
            runtime.status('evaluation', completed=retained, requested=intent['count'])
            if failed:
                stage = 'failed'; break
        else:
            stage = 'completed'
    except Exception as error:
        stage = 'failed'; error_type = type(error).__name__
    terminal = None
    if context is not None:
        terminal = execution.terminal_receipt(intent, launch, batches, prefix, stage,
            raw_pending=raw_pending is not None,
            raw_pending_start=raw_pending['start'] if raw_pending else None,
            raw_pending_sha256=hashlib.sha256(execution.payload_bytes(raw_pending)).hexdigest() if raw_pending else None)
    result = {'stage': stage, 'run_id': intent['run_id'], 'intent_sha256': intent['intent_sha256'],
        'launch': launch, 'batches': batches, 'worker_terminal': terminal, 'raw_pending': raw_pending is not None,
        'raw_pending_record': raw_pending, 'pre_input_failure': context is None, 'error_type': error_type,
        'elapsed_seconds': runtime.elapsed(), 'official_test_used': context is not None,
        'model_and_peft_verified_before_input': context is not None,
        'latency_measurement': 'Successful GPU generation is amortized over the actual eligible subset; failed-attempt time may include setup. Tail/input-limit rows are never padding duplicates.'}
    runtime.finish(result)
    return result


@app.function(image=image, gpu='A100-80GB', cpu=(4, 4), memory=(32768, 32768), timeout=1800,
    startup_timeout=120, retries=0, max_containers=1, min_containers=0, buffer_containers=0,
    scaledown_window=2, volumes={'/artifacts': artifacts})
def evaluate_shard(intent: dict, input_descriptor: dict, authorization: dict):
    return run_shard(intent, input_descriptor, authorization, runtime=Runtime())


def validate_dispatch(intent, descriptor, authorization, claim, started, ledger, *, launch_lock_present):
    execution.validate_remote_metadata(intent, descriptor, authorization)
    if claim != execution.dispatch_claim(intent, claim.get('claim_id')):
        raise ValueError('Unique dispatch claim differs')
    expected = {'stage': 'dispatch_started', 'run_id': intent['run_id'],
        'intent_sha256': intent['intent_sha256'], 'claim_sha256': claim['claim_sha256']}
    if started != expected or not launch_lock_present:
        raise ValueError('Controller must persist dispatch intent and own the global GPU launch lock')
    from .comparison_control import require_fresh_modal_budget
    require_fresh_modal_budget(ledger)
    if not 0 < ledger['limits']['modal'] <= 30 or not 0 < ledger['limits']['deepseek'] <= 20:
        raise ValueError('Service ceilings differ from authorization')
    jobs = [job for job in ledger['jobs'] if job.get('run_id') == intent['run_id']]
    if len(jobs) != 1:
        raise ValueError('Child dispatch requires one saved reservation')
    job = jobs[0]
    reserved = Decimal(str(job.get('reserved_usd', 0)))
    if (job.get('service') != 'modal' or job.get('status') != 'spawning'
            or isinstance(job.get('reserved_usd'), bool) or not reserved.is_finite() or reserved < Decimal('1.75')
            or any(job.get(key) != value for key, value in {
                'intent_sha256': intent['intent_sha256'], 'claim_sha256': claim['claim_sha256'],
                'freeze_sha256': intent['freeze_sha256'], 'seal_sha256': intent['seal_sha256'], 'bundle_id': intent['bundle_id']}.items())):
        raise ValueError('Saved funded child/claim/source identity differs')
    return True


@app.local_entrypoint()
def launch(job_folder: str):
    # The parent already owns gpu_launch.lock; acquiring it here would deadlock.
    from .final_scale_loader import private, read, ensure_json
    local = private(job_folder)
    if (local/'cli_spawn_started.json').exists(): raise ValueError('A CLI spawn was already attempted; reconcile instead of replaying')
    if (local/'launch.json').exists(): raise ValueError('Existing launch must be reconciled, never repeated')
    intent, descriptor, authorization, claim, started = [read(local/name) for name in
        ('intent.json', 'input_descriptor.json', 'authorization.json', 'dispatch_claim.json', 'dispatch_started.json')]
    runtime = ROOT/'runs/supervisor'
    validate_dispatch(intent, descriptor, authorization, claim, started, read(runtime/'budget.json'),
        launch_lock_present=(runtime/'gpu_launch.lock').is_file())
    artifact_checks.verify_packaged_sources(ROOT, authorization['sealed']['contract']['protocol']['source_hashes'])
    receipt = _spawn_once(local, intent, descriptor, authorization, claim, spawn=evaluate_shard.spawn)
    print(json.dumps(receipt), flush=True)


def _spawn_once(local, intent, descriptor, authorization, claim, *, spawn):
    from .final_scale_loader import ensure_json
    if local.name != intent['run_id']:
        raise ValueError('The private job directory must match the owned run identity')
    if (local/'launch.json').exists() or (local/'cli_spawn_started.json').exists():
        raise ValueError('A CLI transmission was already attempted; never replay it')
    # This exclusive marker closes the CLI-replay window when spawn transmits
    # but local launch-receipt persistence fails. Never remove it automatically.
    with (local/'cli_spawn_started.json').open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(execution.payload_bytes({'stage': 'cli_spawn_started', 'run_id': intent['run_id'],
            'intent_sha256': intent['intent_sha256'], 'claim_sha256': claim['claim_sha256']}).decode('utf-8'))
        handle.flush(); os.fsync(handle.fileno())
    call = spawn(intent, descriptor, authorization)
    receipt = execution.launch_receipt(intent, call.object_id)
    ensure_json(local/'launch.json', receipt)
    return receipt
