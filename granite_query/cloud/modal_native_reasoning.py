"""Unlaunched, separately versioned native reasoning training/evaluation worker.

The caller owns funding, unique dispatch and the global GPU launch guard. This
module has no CLI, reservation, retry, dataset loader or endpoint. Runtime tests
replace the complete CUDA/provider boundary with a synthetic object.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import time

import modal
from cloud.modal_train import image, artifacts, state
from cloud import native_reasoning_contract as contract
from cloud import final_scale_artifacts as physical
from cloud import granite_lora_layout as layout
from cloud.comparison_metrics import summarize
from cloud.valuation_contract import trim_generation

ROOT = Path(__file__).resolve().parent
VERSION = 'native-reasoning-worker-v1'
MAX_JSON_BYTES = 64*1024*1024
HASH = re.compile(r'[a-f0-9]{64}')
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}')
REQUIRED_SOURCES = frozenset(('modal_native_reasoning.py', 'native_reasoning_contract.py',
    'modal_train.py', 'valuation_contract.py', 'comparison_metrics.py',
    'final_scale_artifacts.py', 'granite_lora_layout.py'))
DEPENDENCIES = {'torch': '2.6.0', 'transformers': '4.57.1', 'peft': '0.17.1',
    'accelerate': '1.10.1', 'safetensors': '0.6.2'}
RESOURCES = {'gpu': 'A100-80GB', 'cpu': (4, 4), 'memory': (32768, 32768),
    'timeout': 1800, 'startup_timeout': 120, 'retries': 0,
    'max_containers': 1, 'min_containers': 0, 'buffer_containers': 0,
    'scaledown_window': 2}
app = modal.App('granite-query-native-reasoning', include_source=False)


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False)+'\n').encode('utf-8')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _hash(value):
    return isinstance(value, str) and HASH.fullmatch(value) is not None


def validate_dispatch(data, plan, dispatch):
    """Bind a caller claim; this never claims to verify remote ledger funding."""
    keys = {'version', 'claim_id', 'run_id', 'plan_sha256', 'input_sha256',
        'source_sha256', 'funding_review_sha256', 'intent_sha256'}
    if (not isinstance(dispatch, dict) or set(dispatch) != keys
            or dispatch['version'] != 'native-reasoning-dispatch-v1'
            or not isinstance(dispatch['claim_id'], str)
            or not re.fullmatch(r'[a-f0-9]{32}', dispatch['claim_id'])
            or not isinstance(plan, dict) or not NAME.fullmatch(str(plan.get('run_id', '')))
            or dispatch['run_id'] != plan['run_id']
            or dispatch['plan_sha256'] != contract.digest(plan)
            or dispatch['input_sha256'] != contract.digest(data)
            or not _hash(dispatch['funding_review_sha256'])
            or dispatch['intent_sha256'] != contract.digest({k: v for k, v in dispatch.items() if k != 'intent_sha256'})):
        raise ValueError('Exact source/input/plan/funding-review dispatch identity required')
    sources = dispatch['source_sha256']
    if (not isinstance(sources, dict) or not REQUIRED_SOURCES <= sources.keys()
            or len(sources) > 64 or any(not isinstance(k, str)
                or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*\.py', k)
                or k in ('.', '..') or not _hash(v) for k, v in sources.items())):
        raise ValueError('Complete simple-basename source hash inventory required')
    return True


def verify_sources(sources, root=ROOT):
    """Physical source bytes are checked before tokenizer/model downloads."""
    if not REQUIRED_SOURCES <= sources.keys():
        raise ValueError('Worker dependency source coverage is incomplete')
    return physical.verify_packaged_sources(root, sources)


def runtime_adapter_config(value):
    """PEFT.to_dict retains enum/set objects; normalize only known metadata."""
    result = dict(value)
    for key in ('peft_type', 'task_type'):
        if hasattr(result.get(key), 'value'):
            result[key] = result[key].value
    if isinstance(result.get('target_modules'), set):
        result['target_modules'] = sorted(result['target_modules'])
    layout.validate_adapter_config(result)
    return result


def render_prompt(tokenizer, row):
    text = tokenizer.apply_chat_template([{'role': 'user', 'content': contract.PREFIX+row['prompt']}],
        tokenize=False, add_generation_prompt=True, enable_thinking=True)
    if not isinstance(text, str) or not text.endswith(contract.OPEN_TAIL):
        raise ValueError('Runtime native OPEN generation prefix differs')
    return text


def _safe(root, relative):
    if not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative:
        raise ValueError('Explicit relative artifact path required')
    parts = relative.split('/')
    if any(not part or part in ('.', '..') or part.endswith((' ', '.'))
            or not NAME.fullmatch(part) for part in parts):
        raise ValueError('Artifact path escaped its portable namespace')
    root = Path(root).absolute(); path = root.joinpath(*parts)
    physical._no_links(path)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Artifact path escaped its volume')
    return path


def _replace(source, target):
    for attempt in range(4):
        try:
            source.replace(target); return
        except PermissionError:
            if attempt == 3:
                raise
            time.sleep(.05*(2**attempt))


def _write(path, value, *, immutable=True):
    path = Path(path); physical._no_links(path); raw = encoded(value)
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError('Worker artifact exceeds its explicit byte bound')
    if immutable and path.exists():
        if path.read_bytes() != raw:
            raise ValueError('Immutable worker artifact changed')
        return _sha(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name+'.pending'); physical._no_links(pending)
    if pending.exists():
        if immutable and pending.read_bytes() == raw:
            _replace(pending, path); return _sha(raw)
        raise ValueError('Pending local artifact requires explicit reconciliation')
    with pending.open('xb') as handle:
        handle.write(raw); handle.flush(); os.fsync(handle.fileno())
    _replace(pending, path)
    return _sha(raw)


def derive_batch(raw, data, plan, dispatch, decode):
    """Pure deterministic decoding of an already durably saved logical batch."""
    validate_dispatch(data, plan, dispatch)
    keys = {'schema_version', 'version', 'run_id', 'protocol_hash', 'input_sha256',
        'intent_sha256', 'call_id', 'arm', 'start', 'stop', 'question_ids',
        'input_tokens', 'generation_ids', 'generation_token_ids', 'eos_ids',
        'generation_seconds', 'generation_failed', 'error_type'}
    if (not isinstance(raw, dict) or set(raw) != keys or raw['schema_version'] != 1
            or raw['version'] != VERSION or raw['run_id'] != plan['run_id']
            or raw['protocol_hash'] != plan['protocol_hash'] or raw['arm'] != plan['arm']
            or raw['input_sha256'] != dispatch['input_sha256']
            or raw['intent_sha256'] != dispatch['intent_sha256']
            or not re.fullmatch(r'fc-[A-Za-z0-9-]+', str(raw['call_id']))
            or type(raw['start']) is not int or raw['start'] % 8
            or not 0 <= raw['start'] < len(data['development'])
            or raw['stop'] != min(raw['start']+8, len(data['development']))
            or raw['eos_ids'] != [100257] or type(raw['generation_failed']) is not bool
            or not isinstance(raw['generation_seconds'], (int, float))
            or isinstance(raw['generation_seconds'], bool)
            or not math.isfinite(raw['generation_seconds']) or raw['generation_seconds'] < 0):
        raise ValueError('Raw batch identity or bounds differ')
    questions = data['development'][raw['start']:raw['stop']]
    ids = [r['id'] for r in questions]; counts = raw['input_tokens']
    if (raw['question_ids'] != ids or not isinstance(counts, list) or len(counts) != len(ids)
            or any(type(n) is not int or not 0 < n <= 1000000 for n in counts)):
        raise ValueError('Raw batch lost/reordered a logical question')
    eligible = [qid for qid, n in zip(ids, counts) if n <= 1536]
    tokens = raw['generation_token_ids']
    if raw['generation_ids'] != eligible or not isinstance(tokens, list):
        raise ValueError('Generation subset differs from actual input eligibility')
    if raw['generation_failed']:
        if tokens or not isinstance(raw['error_type'], str) or not eligible:
            raise ValueError('Failed attempted batch has ambiguous generated tokens')
    elif (len(tokens) != len(eligible) or raw['error_type'] is not None
            or any(not isinstance(row, list) or not 0 < len(row) <= 1024
                or any(type(token) is not int or not 0 <= token < 100352 for token in row)
                for row in tokens)):
        raise ValueError('Raw generated output count/token bounds differ')
    by_id = {} if raw['generation_failed'] else dict(zip(eligible, tokens))
    results = []
    for question, count in zip(questions, counts):
        row = {'id': question['id'], 'gold_answer': question['gold_answer'],
            'response': '', 'truncated': True, 'generated_tokens': 0,
            'elapsed_seconds': 0., 'input_tokens': count, 'outcome': 'input_limit'}
        if count <= 1536:
            row['elapsed_seconds'] = raw['generation_seconds']/len(eligible)
            row['outcome'] = 'failed' if raw['generation_failed'] else 'generated'
            if not raw['generation_failed']:
                suffix, truncated = trim_generation(by_id[question['id']], [100257], 1024)
                row.update(response=decode(suffix), truncated=truncated,
                    generated_tokens=len(suffix))
                if not isinstance(row['response'], str):
                    raise ValueError('Decoder must preserve one textual response per question')
        results.append(row)
    return {'schema_version': 1, 'version': VERSION, 'run_id': plan['run_id'],
        'protocol_hash': plan['protocol_hash'], 'intent_sha256': dispatch['intent_sha256'],
        'call_id': raw['call_id'], 'arm': plan['arm'], 'start': raw['start'],
        'stop': raw['stop'], 'raw_sha256': _sha(encoded(raw)), 'rows': results}


def derive_with_tokenizer(raw, data, plan, dispatch, tokenizer, *, expected_call_id):
    """Local replay proof with actual pinned prompt/tokenizer and provider ID."""
    contract.tokenizer_identity(tokenizer)
    if (not re.fullmatch(r'fc-[A-Za-z0-9-]+', str(expected_call_id))
            or not isinstance(raw, dict) or raw.get('call_id') != expected_call_id
            or type(raw.get('start')) is not int or type(raw.get('stop')) is not int
            or not 0 <= raw['start'] < raw['stop'] <= len(data['development'])):
        raise ValueError('Known provider call and bounded original batch required')
    counts = [len(tokenizer.encode(render_prompt(tokenizer, row), add_special_tokens=False))
        for row in data['development'][raw['start']:raw['stop']]]
    if raw.get('input_tokens') != counts:
        raise ValueError('Saved raw input eligibility differs from the pinned prompt encoding')
    return derive_batch(raw, data, plan, dispatch, lambda ids: tokenizer.decode(ids,
        skip_special_tokens=True, clean_up_tokenization_spaces=False))


class Runtime:
    """Actual CUDA/Modal boundary. Construction alone performs no provider call."""
    def __init__(self, root=Path('/artifacts')):
        self.root = Path(root); self.started = time.monotonic()
        self.call_id = modal.current_function_call_id()
        self.latest_checkpoint = None; self.runtime_proof = None

    def elapsed(self):
        return time.monotonic()-self.started

    def begin(self, data, plan, dispatch):
        self.plan = plan; self.dispatch = dispatch
        self.folder = _safe(self.root, plan['run_id'])
        if self.folder.exists():
            raise ValueError('Existing native artifacts require reconciliation, never fresh execution')
        owner = {'claim_id': dispatch['claim_id'], 'intent_sha256': dispatch['intent_sha256'],
            'call_id': self.call_id}
        if not state.put('native-reasoning-owner:'+plan['run_id'], owner, skip_if_exists=True):
            raise ValueError('This native attempt already has an owner; never repeat execution')
        self.folder.mkdir(parents=True, exist_ok=False)
        for name, value in (('input.json', data), ('plan.json', plan), ('dispatch.json', dispatch), ('owner.json', owner)):
            _write(self.folder/name, value)
        artifacts.commit()

    def status(self, stage, **details):
        value = {'stage': stage, 'run_id': self.plan['run_id'], 'call_id': self.call_id,
            'intent_sha256': self.dispatch['intent_sha256'], 'elapsed_seconds': round(self.elapsed(), 3), **details}
        _write(self.folder/'status.json', value, immutable=False)
        state[self.plan['run_id']] = value; artifacts.commit()

    def verify_sources(self, dispatch):
        observed = verify_sources(dispatch['source_sha256'])
        versions = {name: importlib.metadata.version(name) for name in DEPENDENCIES}
        if versions != DEPENDENCIES:
            raise ValueError('Installed runtime dependencies differ from the pinned image')
        self.source_proof = {'physical': observed, 'dependency_versions': versions,
            'funding_review_sha256': dispatch['funding_review_sha256'], 'remote_ledger_funding_verified': False}
        _write(self.folder/'source_verification.json', self.source_proof)
        artifacts.commit()

    def load_tokenizer(self, plan):
        from transformers import AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(contract.MODEL, revision=contract.REVISION, trust_remote_code=False)
        self.tokenizer.pad_token = self.tokenizer.eos_token; self.tokenizer.padding_side = 'left'
        return self.tokenizer

    def record_tokenizer(self, identity):
        _write(self.folder/'tokenizer_verification.json', identity); artifacts.commit()

    def load_model(self, plan):
        import torch
        from huggingface_hub import hf_hub_download
        from transformers import AutoModelForCausalLM, set_seed
        from peft import LoraConfig, get_peft_model
        torch.set_num_threads(4); set_seed(42)
        config_file = Path(hf_hub_download(contract.MODEL, 'config.json', revision=contract.REVISION))
        if not 0 < config_file.stat().st_size <= physical.MAX_JSON_BYTES:
            raise ValueError('Pinned raw model configuration exceeds its bound')
        raw = config_file.read_bytes()
        if _sha(raw) != physical.PINNED_CONFIG_SHA:
            raise ValueError('Downloaded pinned raw model configuration differs')
        self.config_path = self.folder/'model_config.json'
        with self.config_path.open('xb') as handle:
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        physical.verify_model_config(self.config_path, allowed_root=self.root)
        self.model = AutoModelForCausalLM.from_pretrained(contract.MODEL, revision=contract.REVISION,
            torch_dtype=torch.bfloat16, attn_implementation='sdpa', trust_remote_code=False).to('cuda')
        self.observed_model_commit = getattr(self.model.config, '_commit_hash', None)
        if self.observed_model_commit != contract.REVISION:
            raise ValueError('Loaded model configuration does not attest the pinned commit')
        self.config = self.model.config.to_dict(); layout.validate_config(self.config)
        self.model.config.use_cache = False
        if plan['arm'] != 'baseline':
            self.model = get_peft_model(self.model, LoraConfig(r=8, lora_alpha=16, lora_dropout=0.0,
                target_modules=['q_proj', 'v_proj'], bias='none', task_type='CAUSAL_LM'),
                autocast_adapter_dtype=True)
            self.parameters = [p for p in self.model.parameters() if p.requires_grad]
            adapter_config = runtime_adapter_config(self.model.peft_config['default'].to_dict())
            layout.validate_layout({name: list(p.shape) for name, p in self.model.named_parameters() if '.lora_' in name},
                self.config, adapter_config, key_format='runtime_default')
            if (len(self.parameters) != 160 or sum(p.numel() for p in self.parameters) != 2621440
                    or any(p.dtype != torch.float32 for p in self.parameters)):
                raise ValueError('Unexpected additional/missing trainable parameters')
            self.optimizer = torch.optim.AdamW(self.parameters, lr=2e-5, betas=(.9, .999),
                eps=1e-8, weight_decay=.01)
            self.model.train()
        elif any('.lora_' in name for name, _ in self.model.named_parameters()):
            raise ValueError('Fresh baseline unexpectedly contains an adapter')
        artifacts.commit()

    def begin_update(self):
        self.optimizer.zero_grad(set_to_none=True)

    def backward_window(self, row, window):
        import torch
        ids = torch.tensor([row['input_ids']], device='cuda')
        labels = torch.tensor([contract.window_labels(row, window)], device='cuda')
        mask = torch.tensor([row['attention_mask']], device='cuda')
        loss = self.model(input_ids=ids, attention_mask=mask, labels=labels).loss
        if not torch.isfinite(loss):
            raise ValueError('Nonfinite native training loss')
        (loss*window['loss_weight']).backward()
        return float(loss.detach())

    def step_update(self):
        import torch
        norm = torch.nn.utils.clip_grad_norm_(self.parameters, 1.)
        if not torch.isfinite(norm):
            raise ValueError('Nonfinite adapter gradients')
        self.optimizer.step()

    def save_training(self, completed, history, *, final=False, incomplete_update_discarded=False):
        import torch
        checkpoint = self.folder/f'checkpoints/update{completed:03d}'
        checkpoint.mkdir(parents=True, exist_ok=True)
        adapter = self.folder/'adapter' if final else checkpoint/'adapter'
        self.model.save_pretrained(adapter, safe_serialization=True, save_embedding_layers=False)
        optimizer = checkpoint/'optimizer_state.pt'
        if optimizer.exists():
            raise ValueError('Immutable optimizer checkpoint already exists')
        torch.save({'optimizer': self.optimizer.state_dict(), 'updates': completed,
            'supervised_tokens': completed*1024, 'history': history,
            'incomplete_update_discarded': incomplete_update_discarded}, optimizer)
        with optimizer.open('rb') as handle:
            os.fsync(handle.fileno())
        observed = physical.inspect_adapter(adapter, model_config_path=self.config_path, allowed_root=self.root)
        record = {'run_id': self.plan['run_id'], 'call_id': self.call_id, 'updates': completed,
            'supervised_tokens': completed*1024, 'adapter_path': adapter.relative_to(self.root).as_posix(),
            'adapter_inventory_sha256': observed['adapter_inventory_sha256'], 'adapter_files_sha256': observed['adapter_files_sha256'],
            'physical_observation': observed, 'optimizer_state_sha256': _sha(optimizer.read_bytes()),
            'optimizer_path': optimizer.relative_to(self.root).as_posix(), 'saved_at_utc': datetime.now(timezone.utc).isoformat(),
            'incomplete_update_discarded': incomplete_update_discarded, 'before_evaluation': True}
        _write(checkpoint/'checkpoint_manifest.json', record); artifacts.commit()
        self.latest_checkpoint = record; return record

    def prepare_evaluation(self, checkpoint):
        import torch
        if self.plan['arm'] == 'baseline':
            self.model.eval()
            self.runtime_proof = {'fresh_base': True, 'adapter_loaded': False,
                'base_geometry_verified': True, 'runtime_peft_load_verified': False}
        else:
            from peft import PeftModel
            from safetensors.torch import load_file
            adapter = _safe(self.root, checkpoint['adapter_path'])
            observed = physical.verify_adapter(adapter, checkpoint['adapter_files_sha256'],
                model_config_path=self.config_path, allowed_root=self.root)
            del self.optimizer, self.parameters
            self.model = PeftModel.from_pretrained(self.model.unload(), adapter, is_trainable=False,
                autocast_adapter_dtype=True)
            parameters = {name: p for name, p in self.model.named_parameters() if '.lora_' in name}
            adapter_config, _ = physical._read_json(adapter/'adapter_config.json')
            geometry = layout.validate_layout({name: list(p.shape) for name, p in parameters.items()},
                self.config, adapter_config, key_format='runtime_default')
            saved = load_file(str(adapter/'adapter_model.safetensors'), device='cpu')
            layout.validate_layout({name: list(p.shape) for name, p in saved.items()},
                self.config, adapter_config, key_format='peft_saved')
            for name, tensor in saved.items():
                runtime_name = name[:-len('.weight')]+'.default.weight'
                actual = parameters[runtime_name].detach().cpu()
                if not torch.isfinite(actual).all() or not torch.isfinite(tensor).all() or not torch.equal(actual, tensor.to(dtype=actual.dtype)):
                    raise ValueError('Reloaded native adapter values differ from saved checkpoint')
            physical.verify_adapter(adapter, checkpoint['adapter_files_sha256'], model_config_path=self.config_path, allowed_root=self.root)
            del saved, parameters
            self.model.eval()
            self.runtime_proof = {'fresh_base': False, 'adapter_loaded': True,
                'adapter_inventory_sha256': observed['adapter_inventory_sha256'],
                'runtime_peft_load_verified': True, 'runtime_layout': geometry,
                'loaded_adapter_values_verified': True, 'checkpoint_hashed_before_evaluation': True}
        self.runtime_proof.update(model=contract.MODEL, revision=self.observed_model_commit,
            model_config_sha256=physical.PINNED_CONFIG_SHA,
            inference={'enable_thinking': True, 'max_new_tokens': 1024,
                'input_limit': 1536, 'evaluation_batch_size': 8})
        _write(self.folder/'runtime_model_verification.json', self.runtime_proof); artifacts.commit()
        return self.runtime_proof

    def render(self, row):
        return render_prompt(self.tokenizer, row)

    def input_counts(self, rows):
        return [len(self.tokenizer.encode(self.render(r), add_special_tokens=False)) for r in rows]

    def generate(self, rows):
        import torch
        inputs = self.tokenizer([self.render(r) for r in rows], padding=True,
            return_tensors='pt', add_special_tokens=False).to('cuda')
        width = inputs['input_ids'].shape[1]
        if width > 1536:
            raise ValueError('Generated subset exceeds common input limit')
        torch.cuda.synchronize(); before = time.monotonic()
        with torch.no_grad():
            output = self.model.generate(**inputs, max_new_tokens=1024, do_sample=False,
                use_cache=True, eos_token_id=[100257], pad_token_id=100257)
        torch.cuda.synchronize()
        return [r[width:].tolist() for r in output], time.monotonic()-before

    def decode(self, ids):
        return self.tokenizer.decode(ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)

    def write_raw(self, start, raw):
        result = _write(self.folder/'raw'/f'batch{start:04d}.json', raw); artifacts.commit(); return result

    def write_batch(self, start, batch):
        _write(self.folder/'batches'/f'batch{start:04d}.json', batch); artifacts.commit()

    def finish(self, result):
        _write(self.folder/'result.json', result); artifacts.commit()


def run_native(data, plan, dispatch, *, runtime):
    """One original attempt only; errors preserve exact completed exposures."""
    rows = contract.validate_bundle(data, plan)
    validate_dispatch(data, plan, dispatch)
    runtime.begin(data, plan, dispatch)
    history = []; batches = []; raw_inventory = []; checkpoint = None; proof = None; pending = None; identity = None
    stage = 'failed'; error_type = None; model_loaded = False; incomplete_update = False
    model_seconds = 0.; training_seconds = 0.; evaluation_seconds = 0.; batch_timings = []
    training_started = None; evaluation_started = None
    try:
        runtime.status('verifying_sources')
        runtime.verify_sources(dispatch)
        tokenizer = runtime.load_tokenizer(plan)
        identity = contract.tokenizer_identity(tokenizer)
        if data['arm'] is not None:
            if data['arm']['tokenizer'] != identity:
                raise ValueError('Actual tokenizer identity differs from prepared native training')
            for row in rows.values():
                contract.validate_encoding(row, tokenizer)
        runtime.record_tokenizer(identity)
        runtime.status('loading_model')
        before_model = runtime.elapsed()
        runtime.load_model(plan); model_loaded = True
        model_seconds = runtime.elapsed()-before_model
        if data['arm'] is not None:
            training_started = runtime.elapsed()
            for update in data['arm']['updates']:
                if runtime.elapsed() > 1400:
                    if checkpoint is None or checkpoint['updates'] != len(history):
                        checkpoint = runtime.save_training(len(history), history, incomplete_update_discarded=False)
                    stage = 'timed_out'; break
                runtime.begin_update(); weighted = 0.; incomplete_update = True
                for window in update['microbatches']:
                    if runtime.elapsed() > 1400:
                        if checkpoint is None or checkpoint['updates'] != len(history):
                            checkpoint = runtime.save_training(len(history), history, incomplete_update_discarded=True)
                        stage = 'timed_out'; break
                    loss = runtime.backward_window(rows[window['id']], window)
                    if not math.isfinite(loss):
                        raise ValueError('Nonfinite returned training loss')
                    weighted += loss*window['loss_weight']
                if stage == 'timed_out':
                    break
                runtime.step_update(); history.append(weighted); incomplete_update = False
                completed = len(history)
                if completed % 4 == 0 or completed == 16:
                    checkpoint = runtime.save_training(completed, history, final=completed == 16)
                runtime.status('training', completed_updates=completed,
                    supervised_tokens=completed*1024, weighted_loss=weighted)
            if len(history) != 16:
                if stage != 'timed_out':
                    raise ValueError('Native training did not complete all frozen updates')
            elif checkpoint is None or checkpoint['supervised_tokens'] != 16384:
                raise ValueError('Saved final checkpoint does not match actual loss exposure')
            training_seconds = runtime.elapsed()-training_started; training_started = None
        if stage != 'timed_out':
            runtime.status('verifying_adapter_reload')
            proof = runtime.prepare_evaluation(checkpoint)
            runtime.status('evaluating', completed=0, requested=len(data['development']))
            evaluation_started = runtime.elapsed()
            stage = 'completed'
            for start in range(0, len(data['development']), 8):
                if runtime.elapsed() > 1600:
                    stage = 'timed_out'; break
                questions = data['development'][start:start+8]
                counts = runtime.input_counts(questions)
                if len(counts) != len(questions) or any(type(n) is not int or n < 1 for n in counts):
                    raise ValueError('Runtime tokenizer lost a logical development question')
                eligible = [r for r, n in zip(questions, counts) if n <= 1536]
                tokens = []; seconds = 0.; failed = False
                if eligible:
                    before = time.monotonic()
                    try:
                        tokens, seconds = runtime.generate(eligible)
                    except Exception as error:
                        failed = True; error_type = type(error).__name__; seconds = time.monotonic()-before
                pending = {'schema_version': 1, 'version': VERSION, 'run_id': plan['run_id'],
                    'protocol_hash': plan['protocol_hash'], 'input_sha256': dispatch['input_sha256'],
                    'intent_sha256': dispatch['intent_sha256'], 'call_id': runtime.call_id, 'arm': plan['arm'],
                    'start': start, 'stop': start+len(questions), 'question_ids': [r['id'] for r in questions],
                    'input_tokens': counts, 'generation_ids': [r['id'] for r in eligible],
                    'generation_token_ids': tokens, 'eos_ids': [100257], 'generation_seconds': seconds,
                    'generation_failed': failed, 'error_type': error_type if failed else None}
                raw_hash = runtime.write_raw(start, pending)
                if raw_hash != _sha(encoded(pending)):
                    raise ValueError('Durable raw writer did not preserve canonical bytes')
                raw_inventory.append({'start': start, 'stop': pending['stop'], 'sha256': raw_hash})
                before_derive = runtime.elapsed()
                batch = derive_batch(pending, data, plan, dispatch, runtime.decode)
                if raw_hash != batch['raw_sha256']:
                    raise ValueError('Raw durable byte hash differs from derived batch')
                runtime.write_batch(start, batch); batches.append(batch); pending = None
                batch_timings.append({'start': start, 'stop': start+len(questions),
                    'generation_seconds': seconds, 'actual_generation_count': len(eligible),
                    'derive_and_commit_seconds': runtime.elapsed()-before_derive})
                runtime.status('evaluating', completed=sum(len(b['rows']) for b in batches),
                    requested=len(data['development']))
                if failed:
                    stage = 'failed'; break
    except Exception as error:
        error_type = type(error).__name__; stage = 'failed'
        # Every4 updates already have a durable adapter/optimizer. On a later
        # failure, preserve a new exact completed-update checkpoint if possible.
        if model_loaded and data['arm'] is not None and len(history) % 4:
            try:
                checkpoint = runtime.save_training(len(history), history,
                    incomplete_update_discarded=incomplete_update)
            except Exception:
                pass
    if training_started is not None:
        training_seconds = runtime.elapsed()-training_started
    if evaluation_started is not None:
        evaluation_seconds = runtime.elapsed()-evaluation_started
    evaluations = [r for batch in batches for r in batch['rows']]
    complete = stage == 'completed' and len(evaluations) == len(data['development']) and pending is None
    result = {'schema_version': 1, 'version': VERSION, 'run_id': plan['run_id'],
        'arm': plan['arm'], 'stage': stage, 'call_id': runtime.call_id,
        'protocol_hash': plan['protocol_hash'], 'plan': plan, 'dispatch': dispatch,
        'dispatch_sha256': contract.digest(dispatch), 'supervised_tokens': len(history)*1024,
        'optimizer_updates': len(history), 'weighted_losses': history,
        'expected_evaluation_count': len(data['development']), 'retained_evaluation_count': len(evaluations),
        'evaluation_complete': complete, 'evaluations': {plan['arm']: evaluations}, 'batches': batches,
        'metrics': {plan['arm']: summarize(evaluations)} if complete else None,
        'outcomes': dict(Counter(r['outcome'] for r in evaluations)),
        'checkpoint': checkpoint, 'runtime_model_verification': proof,
        'adapter_inventory': checkpoint['physical_observation'] if checkpoint else None,
        'source_verification': getattr(runtime, 'source_proof', None), 'tokenizer_verification': identity,
        'raw_batches': raw_inventory,
        'model_load_seconds': model_seconds, 'total_model_load_seconds': model_seconds, 'training_seconds': training_seconds,
        'evaluation_seconds': evaluation_seconds, 'batch_timings': batch_timings,
        'max_generation_batch_seconds': max((b['generation_seconds'] for b in batch_timings), default=None),
        'incomplete_update_discarded': incomplete_update,
        'raw_pending': pending is not None, 'raw_pending_record': pending,
        'error_type': error_type, 'elapsed_seconds': round(runtime.elapsed(), 6),
        'worker_terminal': {'confirmed_terminal': False, 'stage': stage,
            'call_id': runtime.call_id, 'retained_evaluation_count': len(evaluations)},
        'official_test_used': False, 'evaluation_role': 'adaptive_training_split_development',
        'funding_verified_by_worker': False,
        'latency_measurement': 'Actual generation subset batch wall time divided by its count; not single-request latency'}
    runtime.finish(result)
    return result


@app.function(image=image, volumes={'/artifacts': artifacts}, **RESOURCES)
def execute(data: dict, plan: dict, dispatch: dict):
    return run_native(data, plan, dispatch, runtime=Runtime())
