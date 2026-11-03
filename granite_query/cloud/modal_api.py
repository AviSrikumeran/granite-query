"""Prepared only: deploy a 24h, twenty-request, demand-driven Granite trial.

Import/deployment refuses without GRANITE_SERVING_MANIFEST naming the immutable
manifest produced by serving_control.prepare. That command requires a measured
chosen adapter, research GPU clearance, and an existing $1 reservation. Initial
control is written separately with serving_control initialize. No credentials are
in images, responses, checkpoint manifests or the client. This file does not
deploy, initialize, reserve funds or start a GPU when imported.

The GPU/request envelope is bounded; arbitrary denied HTTP traffic still has CPU
cost. Expiry denies future GPU calls; a supervisor must stop the deployment after
the trial. No always-on GPU pool or automatic retries are configured.
"""
import hashlib
import json
import os
from pathlib import Path
import time

import modal
from .serving_control import (Admission, DICT_NAME, LIMITS, MODEL, PREFIX, REVISION,
                              ServingRefused, public_model, read, validate_manifest,
                              validate_request)

manifest_path = os.environ.get('GRANITE_SERVING_MANIFEST') or (
    '/serving/manifest.json' if not modal.is_local() else None)
if not manifest_path:
    raise RuntimeError('Refusing API deployment without GRANITE_SERVING_MANIFEST and a final evaluated checkpoint')
manifest_file = Path(manifest_path).resolve()
manifest = read(manifest_file)
validate_manifest(manifest)

app = modal.App('granite-query-capped-api', include_source=False)
control_store = modal.Dict.from_name(DICT_NAME)
artifacts = modal.Volume.from_name('granite-query-training-artifacts')
common = (modal.Image.debian_slim(python_version='3.12')
          .env({'TOKENIZERS_PARALLELISM':'false', 'HF_HUB_DISABLE_TELEMETRY':'1',
                'GRANITE_SERVING_MANIFEST':'/serving/manifest.json'}))
# Keep startup mounts last: Modal rejects build steps after add_local_*.
cpu_image = (common.pip_install('fastapi[standard]==0.115.12', 'transformers==4.57.1', 'Jinja2==3.1.6')
             .env({'USE_TORCH':'0'})
             .add_local_python_source('cloud')
             .add_local_file(str(manifest_file), '/serving/manifest.json'))
gpu_image = (common.pip_install('torch==2.6.0', 'transformers==4.57.1', 'peft==0.17.1',
                               'accelerate==1.10.1', 'safetensors==0.6.2', 'Jinja2==3.1.6')
             .add_local_python_source('cloud')
             .add_local_file(str(manifest_file), '/serving/manifest.json'))


@app.function(image=gpu_image, gpu='L4', cpu=(1, 1), memory=(12288, 12288),
              timeout=90, startup_timeout=60, retries=0, max_containers=1,
              min_containers=0, buffer_containers=0, scaledown_window=2,
              single_use_containers=True, volumes={'/artifacts':artifacts})
def generate_once(body:dict, ticket:dict):
    """Only called after a permanent durable quota claim and dispatch marker."""
    started = time.monotonic()
    current = read('/serving/manifest.json')
    validate_manifest(current)
    gate = Admission(control_store, current)
    gate.ready()
    index = ticket['slot']
    stored = control_store.get(gate.prefix+f'slot:{index}')
    if stored != {key:value for key,value in ticket.items() if key != 'slot'}:
        raise ServingRefused('GPU request lacks a durable admission')
    if control_store.get(gate.prefix+f'dispatch:{index}') != {'request_id':ticket['request_id']}:
        raise ServingRefused('GPU request lacks an authorized dispatch')
    from .serving_control import digest
    if digest(body) != ticket['payload_sha256']:
        raise ServingRefused('Request changed after admission')
    # A second GPU entry with the same ticket fails before model loading. The
    # public gateway is the only untrusted entry; workspace RPC is authenticated.
    if not control_store.put(gate.prefix+f'worker:{index}', {'request_id':ticket['request_id']}, skip_if_exists=True):
        raise ServingRefused('GPU execution already attempted')
    artifact = current['selection']['artifact']
    folder = Path('/artifacts')/artifact['run_id']/artifact['adapter_subpath']
    for name, expected in artifact['files_sha256'].items():
        if hashlib.sha256((folder/name).read_bytes()).hexdigest() != expected:
            raise ServingRefused('Chosen adapter changed after final selection')
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel
    tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION)
    rendered = tokenizer.apply_chat_template([{'role':'user','content':PREFIX+body['prompt']}],
                                             tokenize=False, add_generation_prompt=True, enable_thinking=False)
    encoded = tokenizer(rendered, return_tensors='pt', add_special_tokens=False)
    if encoded['input_ids'].shape[1] > LIMITS['max_input_tokens']:
        raise ServingRefused('Input token limit exceeded', 422)
    if time.monotonic()-started > 35:
        raise TimeoutError('Cold-load admission deadline exceeded; request remains consumed')
    base = AutoModelForCausalLM.from_pretrained(MODEL, revision=REVISION,
                torch_dtype=torch.bfloat16, attn_implementation='sdpa').to('cuda')
    model = PeftModel.from_pretrained(base, folder)
    model.eval()
    if time.monotonic()-started > 65:
        raise TimeoutError('Model load left insufficient inference time; request remains consumed')
    cap = body['max_new_tokens']
    with torch.inference_mode():
        output = model.generate(**encoded.to('cuda'), max_new_tokens=cap, do_sample=False,
                    max_time=max(1, 80-(time.monotonic()-started)), use_cache=True,
                    pad_token_id=tokenizer.eos_token_id)
    generated = output[0, encoded['input_ids'].shape[1]:]
    eos = model.generation_config.eos_token_id
    eos_ids = set(eos if isinstance(eos, (list, tuple)) else [eos])
    eos_ids.add(tokenizer.eos_token_id)
    return dict(response=tokenizer.decode(generated, skip_special_tokens=True),
                generated_tokens=len(generated), input_tokens=encoded['input_ids'].shape[1],
                truncated=bool(len(generated) and int(generated[-1]) not in eos_ids),
                elapsed_seconds=round(time.monotonic()-started, 3),
                checkpoint_id=current['selection']['checkpoint_id'], request_id=body['request_id'])


@app.function(image=cpu_image, cpu=(0.125, 1), memory=(512, 2048),
              timeout=240, startup_timeout=60, max_containers=1,
              min_containers=0, buffer_containers=0, scaledown_window=2)
@modal.concurrent(max_inputs=1)
@modal.asgi_app()
def web():
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from transformers import AutoTokenizer
    current = read('/serving/manifest.json')
    gate = Admission(control_store, current)
    api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    api.add_middleware(CORSMiddleware, allow_origins=[current['allowed_origin']],
                       allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])
    tokenizer = None

    def check():
        try:
            gate.ready()
        except ServingRefused as error:
            raise HTTPException(error.status_code, str(error)) from None

    @api.get('/health')
    async def health():
        check()
        used = gate.used()
        return dict(status='quota_exhausted' if used >= LIMITS['max_requests'] else 'ready',
                    checkpoint_id=current['selection']['checkpoint_id'],
                    requests_consumed=used, max_requests=LIMITS['max_requests'],
                    expires_at_utc=current['expires_at_utc'])

    @api.get('/model')
    async def model():
        check()
        return public_model(current)

    @api.post('/generate')
    async def generate(request:Request):
        nonlocal tokenizer
        check()
        payload = bytearray()
        async for part in request.stream():
            payload.extend(part)
            if len(payload) > LIMITS['max_body_bytes']:
                raise HTTPException(413, 'Request body exceeds 16 KiB')
        try:
            body = validate_request(json.loads(payload))
            if tokenizer is None:
                tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION)
            rendered = tokenizer.apply_chat_template([{'role':'user','content':PREFIX+body['prompt']}],
                               tokenize=False, add_generation_prompt=True, enable_thinking=False)
            if len(tokenizer(rendered, add_special_tokens=False)['input_ids']) > LIMITS['max_input_tokens']:
                raise ServingRefused('Input token limit exceeded', 422)
            ticket = gate.claim(body)
            gate.mark_dispatch(ticket, body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HTTPException(422, 'Invalid JSON request body') from None
        except ServingRefused as error:
            raise HTTPException(error.status_code, str(error)) from None
        try:
            # No retry on timeout/cancellation: the consumed permit is permanent.
            return await generate_once.remote.aio(body, ticket)
        except Exception:
            # Do not expose remote tracebacks, account details, paths or secrets.
            raise HTTPException(503, 'Generation failed; this request remains consumed and will not retry') from None

    return api
