"""Undeployed experimental Modal backend; one explicit variant per app.

Requires GRANITE_DEMO_MANIFEST pointing to an offline-prepared private contract.
For correction, GRANITE_DEMO_ADAPTER_DIR must contain its two inspected files.
Only those files are mounted, never an enclosing run/model directory. Base model
files must already exist in the manifest's private Volume; serving mounts it read
only and performs no model download. The durable Dict must be provisioned
separately; `initialize` explicitly binds its namespace without resetting quota.

Importing this module is NOT an offline verification method: it defines Modal
resources. Tests parse its AST instead. No deployment, upload, resource creation,
or GPU verification has been performed. Cold/warm latency and L4 behavior remain
unverified. A 20-request envelope is not a provider-enforced invoice cap; denied
authenticated CPU traffic can also cost money. Stop the deployment after expiry.

For a later authorized deployment, work from the granite_query directory and
use the module path cloud.modal_demo_api_v1. Offline contract CLI commands use
python -m cloud.demo_serving_v1 from that same directory. This keeps serialized
module paths aligned with /root/cloud inside the prepared images. Do not import
this provider module as a verification step.

Official interfaces checked 2026-11-05:
https://modal.com/docs/guide/webhook-proxy-auth
https://modal.com/docs/sdk/py/latest/Dict
https://modal.com/docs/sdk/py/latest/Volume
"""
import asyncio
import json
import os
from pathlib import Path
import time

from .demo_serving_v1 import (Admission, DICT_NAME, LIMITS, MODEL, PREFIX, REVISION, DemoRefused,
                              parse_time, public_model, read, utcnow,
                              validate_manifest, validate_request, verify_adapter,
                              verify_files)

manifest_path = os.environ.get('GRANITE_DEMO_MANIFEST')
if not manifest_path:
    raise RuntimeError('Refusing deployment without an explicit experimental demo manifest')
manifest_file = Path(manifest_path).resolve(strict=True)
manifest = validate_manifest(read(manifest_file))

# Keep this import after fail-closed offline contract validation. Unit tests do
# not import this module, call Modal, build images, or upload private files.
import modal

artifact = manifest['artifact']
adapter_dir = None
if artifact['variant'] == 'correction':
    adapter_path = os.environ.get('GRANITE_DEMO_ADAPTER_DIR')
    if not adapter_path:
        raise RuntimeError('Correction deployment requires its explicit adapter directory')
    adapter_dir = Path(adapter_path).resolve(strict=modal.is_local())
    if modal.is_local():
        verify_adapter(adapter_dir, artifact)

app = modal.App('granite-query-experimental-demo-v1', include_source=False)
control_store = modal.Dict.from_name(DICT_NAME, create_if_missing=False)
base_volume = modal.Volume.from_name(artifact['base']['volume_name'], create_if_missing=False)
base_volume = base_volume.with_mount_options(read_only=True, sub_path=artifact['base']['volume_subpath'])
environment = {'TOKENIZERS_PARALLELISM': 'false', 'HF_HUB_DISABLE_TELEMETRY': '1',
               'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
               'GRANITE_DEMO_MANIFEST': '/serving/manifest.json'}
if adapter_dir:
    environment['GRANITE_DEMO_ADAPTER_DIR'] = '/serving/adapter'
common = (modal.Image.debian_slim(python_version='3.12').env(environment)
          .run_commands('mkdir -p /root/cloud', 'touch /root/cloud/__init__.py'))
cpu_image = common.pip_install('fastapi[standard]==0.115.12', 'transformers==4.57.1', 'Jinja2==3.1.6').env({'USE_TORCH': '0'})
gpu_image = common.pip_install('torch==2.6.0', 'transformers==4.57.1', 'peft==0.17.1',
                               'accelerate==1.10.1', 'safetensors==0.6.2', 'Jinja2==3.1.6')


def attach_source(image):
    # Explicit source files, not a mount of the shared workspace or runs folder.
    source = Path(__file__).parent
    for name in ('demo_serving_v1.py', 'modal_demo_api_v1.py'):
        image = image.add_local_file(str(source / name), '/root/cloud/' + name)
    return image.add_local_file(str(manifest_file), '/serving/manifest.json')


cpu_image, gpu_image = attach_source(cpu_image), attach_source(gpu_image)
if adapter_dir and modal.is_local():
    for name in ('adapter_config.json', 'adapter_model.safetensors'):
        gpu_image = gpu_image.add_local_file(str(adapter_dir / name), '/serving/adapter/' + name)


@app.function(image=gpu_image, gpu='L4', cpu=(1, 1), memory=(12288, 12288),
              timeout=90, startup_timeout=60, retries=0, max_containers=1,
              min_containers=0, buffer_containers=0, scaledown_window=2,
              single_use_containers=True, volumes={'/models': base_volume})
def generate_once(body: dict, ticket: dict):
    """Authenticated workspace RPC, reached publicly only after CPU admission."""
    started = time.monotonic()
    current = validate_manifest(read('/serving/manifest.json'))
    gate = Admission(control_store, current)
    body = validate_request(body, variant=current['artifact']['variant'])
    gate.mark_worker(ticket, body)  # permanent once-only marker before model load
    selected = current['artifact']
    phase_started = time.monotonic()
    verify_files('/models', selected['base']['files_sha256'])
    if selected['variant'] == 'correction':
        verify_adapter('/serving/adapter', selected)
    hashes_seconds = time.monotonic() - phase_started
    gate.ready()
    phase_started = time.monotonic()
    import resource
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer
    torch.cuda.reset_peak_memory_stats()
    runtime_setup_seconds = time.monotonic() - phase_started
    phase_started = time.monotonic()
    tokenizer = AutoTokenizer.from_pretrained('/models', local_files_only=True, trust_remote_code=False)
    rendered = tokenizer.apply_chat_template([{'role': 'user', 'content': PREFIX + body['prompt']}],
                    tokenize=False, add_generation_prompt=True, enable_thinking=False)
    encoded = tokenizer(rendered, return_tensors='pt', add_special_tokens=False)
    tokenizer_seconds = time.monotonic() - phase_started
    if encoded['input_ids'].shape[1] > LIMITS['max_input_tokens']:
        raise DemoRefused('Input token limit exceeded', 422)
    preparation_elapsed = time.monotonic() - started
    # Offline-only adjustment; the 60s cold-preparation guard is unverified on L4.
    # The overall 80s generation budget and 90s function timeout remain unchanged.
    if preparation_elapsed > 60:
        raise TimeoutError(json.dumps({
            'error': 'cold_preparation_deadline_exceeded',
            'phase': 'before_model_load', 'guard_seconds': 60,
            'permit_consumed': True,
            'phase_timings_seconds': {
                'hashes': round(hashes_seconds, 3),
                'runtime_setup': round(runtime_setup_seconds, 3),
                'tokenizer': round(tokenizer_seconds, 3),
                'current_elapsed': round(preparation_elapsed, 3),
            },
        }, sort_keys=True, allow_nan=False))
    phase_started = time.monotonic()
    model = AutoModelForCausalLM.from_pretrained('/models', local_files_only=True,
                trust_remote_code=False, use_safetensors=True,
                torch_dtype=torch.bfloat16, attn_implementation='sdpa', device_map={'': 'cuda'})
    if selected['variant'] == 'correction':
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, '/serving/adapter', local_files_only=True)
    model.eval()
    torch.cuda.synchronize()
    model_load_seconds = time.monotonic() - phase_started
    gate.ready()
    remaining = min(60, 80 - (time.monotonic() - started),
                    (parse_time(current['expires_at_utc']) - utcnow()).total_seconds())
    if remaining <= 0:
        raise TimeoutError('No inference time remains; permit remains consumed')
    phase_started = time.monotonic()
    with torch.inference_mode():
        output = model.generate(**encoded.to('cuda'), max_new_tokens=body['max_new_tokens'],
                    do_sample=False, max_time=remaining, use_cache=True,
                    pad_token_id=tokenizer.eos_token_id)
    torch.cuda.synchronize()
    generation_seconds = time.monotonic() - phase_started
    generated = output[0, encoded['input_ids'].shape[1]:]
    eos = model.generation_config.eos_token_id
    eos_ids = set(eos if isinstance(eos, (list, tuple)) else [eos]) | {tokenizer.eos_token_id}
    return dict(schema_version=1, experimental=True,
                model=MODEL, revision=REVISION,
                response=tokenizer.decode(generated, skip_special_tokens=True),
                generated_tokens=len(generated), input_tokens=encoded['input_ids'].shape[1],
                truncated=bool(len(generated) and int(generated[-1]) not in eos_ids),
                elapsed_seconds=round(time.monotonic() - started, 3),
                checkpoint_id=selected['checkpoint_id'], variant=selected['variant'],
                request_id=body['request_id'],
                settings={'enable_thinking': False, 'do_sample': False, 'max_new_tokens': body['max_new_tokens']},
                diagnostics={
                    'phase_seconds': {'hashes': round(hashes_seconds, 3),
                                      'runtime_setup': round(runtime_setup_seconds, 3),
                                      'tokenizer': round(tokenizer_seconds, 3),
                                      'model_load': round(model_load_seconds, 3),
                                      'generation': round(generation_seconds, 3)},
                    'cuda_peak_allocated_bytes': int(torch.cuda.max_memory_allocated()),
                    # Linux ru_maxrss is KiB; the prepared image is Debian Linux.
                    'host_peak_rss_bytes': int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024),
                    'torch_version': str(torch.__version__),
                    'transformers_version': str(transformers.__version__),
                    'gpu_name': torch.cuda.get_device_name(0)},
                checkpoint_improvement_established=False)


@app.function(image=cpu_image, cpu=(0.125, 1), memory=(512, 2048),
              timeout=180, startup_timeout=60, max_containers=1,
              min_containers=0, buffer_containers=0, scaledown_window=2,
              volumes={'/models': base_volume})
@modal.concurrent(max_inputs=1)
@modal.asgi_app(requires_proxy_auth=True)
def web():
    from fastapi import FastAPI, HTTPException, Request
    from transformers import AutoTokenizer
    current = validate_manifest(read('/serving/manifest.json'))
    gate = Admission(control_store, current)
    api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    tokenizer = None

    @api.middleware('http')
    async def response_headers(request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    def check():
        try:
            gate.ready()
        except DemoRefused as error:
            raise HTTPException(error.status_code, str(error)) from None

    @api.get('/health')
    async def health():
        check()
        used = gate.used()
        return dict(schema_version=1, experimental=True,
                    status='quota_exhausted' if used >= 20 else 'ready',
                    requests_consumed=used, max_requests=20,
                    checkpoint_id=current['artifact']['checkpoint_id'],
                    variant=current['artifact']['variant'], expires_at_utc=current['expires_at_utc'])

    @api.get('/model')
    async def model():
        check()
        used = gate.used()
        return dict(public_model(current), requests_consumed=used,
                    status='quota_exhausted' if used >= 20 else 'ready')

    @api.post('/generate')
    async def generate(request: Request):
        nonlocal tokenizer
        check()
        if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
            raise HTTPException(415, 'Use Content-Type application/json')
        if request.headers.get('content-encoding', 'identity').lower() != 'identity':
            raise HTTPException(415, 'Compressed request bodies are not supported')
        payload = bytearray()
        try:
            async with asyncio.timeout(10):
                async for part in request.stream():
                    payload.extend(part)
                    if len(payload) > LIMITS['max_body_bytes']:
                        raise HTTPException(413, 'Request body exceeds 16 KiB')
        except TimeoutError:
            raise HTTPException(408, 'Request body deadline exceeded') from None
        try:
            body = validate_request(json.loads(payload), variant=current['artifact']['variant'])
            if tokenizer is None:
                verify_files('/models', current['artifact']['base']['files_sha256'], weights=False)
                tokenizer = AutoTokenizer.from_pretrained('/models', local_files_only=True, trust_remote_code=False)
            rendered = tokenizer.apply_chat_template([{'role': 'user', 'content': PREFIX + body['prompt']}],
                        tokenize=False, add_generation_prompt=True, enable_thinking=False)
            if len(tokenizer(rendered, add_special_tokens=False)['input_ids']) > LIMITS['max_input_tokens']:
                raise DemoRefused('Input token limit exceeded', 422)
            ticket = gate.claim(body)
            gate.mark_dispatch(ticket, body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HTTPException(422, 'Invalid JSON request body') from None
        except DemoRefused as error:
            raise HTTPException(error.status_code, str(error)) from None
        except Exception:
            raise HTTPException(503, 'Private inference bundle is unavailable; no GPU dispatch occurred') from None
        try:
            # Cancellation/timeouts never refund or automatically retry a permit.
            return await generate_once.remote.aio(body, ticket)
        except Exception:
            raise HTTPException(503, 'Generation failed or completion is unknown; permit remains consumed. Do not retry.') from None

    return api


@app.local_entrypoint()
def initialize(confirmation: str = ''):
    """Explicit durable-control write only; never run as part of verification."""
    if confirmation != manifest['quota_namespace']:
        raise RuntimeError('Initialization requires the exact explicit quota namespace confirmation')
    print(json.dumps(Admission(control_store, manifest).initialize()))
