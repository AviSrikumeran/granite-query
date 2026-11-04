"""Public HF artifact audit. No model code execution, inference, training or paid APIs.

Download the project's pinned Granite checkpoint and inspect public comparison
configs and Safetensors headers without downloading comparison model bodies.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import struct
import time
import requests

ROOT = Path(__file__).resolve().parent
PIN = '4e9c275e232f10211ec88644d106a1f6a1b60e06'
MODELS = [
    ('ibm-granite/granite-4.2-3b', PIN),
    ('ibm-granite/granite-4.2-8b', 'main'),
    ('ibm-granite/granite-4.2-30b', 'main'),
    ('mistralai/Ministral-3-3B-Instruct-2512', 'main'),
    ('tiiuae/Falcon-H1-3B-Instruct', 'main'),
    ('allenai/Olmo-3-7B-Instruct', 'main'),
    ('meta-llama/Llama-3.2-3B-Instruct', 'main'),
    ('Qwen/Qwen3-4B', 'main'),
    ('deepseek-ai/DeepSeek-R1-Distill-Qwen-7B', 'main'),
    ('deepseek-ai/DeepSeek-V3', 'main'),
    ('deepseek-ai/DeepSeek-V4-Pro', 'main'),
]

def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

def url(repo, sha, name):
    return f'https://huggingface.co/{repo}/resolve/{sha}/{name}'

def get_json(address):
    response = requests.get(address, timeout=(20, 120))
    response.raise_for_status()
    return response.json()

def header(address):
    # Servers may ignore Range; read only the exact requested prefix and close.
    with requests.get(address, headers={'Range': 'bytes=0-7', 'Accept-Encoding': 'identity'}, stream=True, timeout=(20, 120)) as r:
        r.raise_for_status()
        prefix = r.raw.read(8)
    n = struct.unpack('<Q', prefix)[0]
    if not 0 < n < 64 * 1024 * 1024:
        raise ValueError('Unexpected Safetensors header size')
    with requests.get(address, headers={'Range': f'bytes=0-{n+7}', 'Accept-Encoding': 'identity'}, stream=True, timeout=(20, 120)) as r:
        r.raise_for_status()
        body = r.raw.read(n + 8)
    if len(body) != n + 8:
        raise ValueError('Short header response')
    return json.loads(body[8:])

def inspect(repo, revision):
    result = {'repo': repo, 'requested_revision': revision, 'observed_at_utc': datetime.now(timezone.utc).isoformat()}
    folder = ROOT / 'models' / repo.replace('/', '--')
    try:
        info = get_json(f'https://huggingface.co/api/models/{repo}/revision/{revision}?blobs=true')
        sha = info['sha']
        result.update(revision=sha, license=(info.get('cardData') or {}).get('license'), gated=info.get('gated'), downloads_last_month=info.get('downloads'), safetensors=info.get('safetensors'), config_summary=info.get('config'))
        save(folder / 'hf_metadata.json', info)
        files = {f['rfilename']: f for f in info['siblings']}
        result['weight_files'] = [{k: f.get(k) for k in ('rfilename', 'size', 'lfs')} for f in files.values() if f['rfilename'].endswith('.safetensors')]
        # Avoid duplicated original-format checkpoints in repositories with both.
        weights = [n for n in files if n.endswith('.safetensors') and '/' not in n]
        if 'model.safetensors' in weights:
            weights = ['model.safetensors']  # HF layout; don't double-count original-format exports.
        result['canonical_weight_files'] = weights
        for name in ['config.json', 'generation_config.json', 'tokenizer_config.json', 'tokenizer.json', 'special_tokens_map.json', 'chat_template.jinja', 'README.md', 'LICENSE', 'LICENSE.txt', 'LICENSE-MODEL', 'model.safetensors.index.json']:
            if name not in files:
                continue
            try:
                r = requests.get(url(repo, sha, name), timeout=(20, 120))
                r.raise_for_status()
                folder.mkdir(parents=True, exist_ok=True)
                (folder / name).write_bytes(r.content)
                if name == 'config.json': result['config'] = r.json()
            except requests.RequestException as e:
                result.setdefault('file_errors', {})[name] = str(e).split('?')[0]
        # Full small-model headers; first shard only for >100GB models.
        total_bytes = sum(files[n].get('size', 0) for n in weights)
        selected = weights if total_bytes < 100_000_000_000 else weights[:1]
        tensors = {}
        for name in selected:
            h = header(url(repo, sha, name))
            save(folder / (name + '.header.json'), h)
            for key, value in h.items():
                if key != '__metadata__': tensors[key] = value
        result['header_shards_inspected'] = len(selected)
        result['header_inventory_complete'] = bool(weights) and len(selected) == len(weights)
        result['header_parameter_elements'] = sum(math.prod(t['shape']) for t in tensors.values())
        result['tensor_count'] = len(tensors)
        result['tensor_examples'] = {k: v for k,v in list(tensors.items())[:10]}
        result['weight_bytes'] = total_bytes
        result['status'] = 'metadata_and_headers' if tensors else 'metadata_only'
    except Exception as e:
        result['status'] = 'unavailable'
        result['error'] = str(e).split('?')[0]
    save(folder / 'audit.json', result)
    print(json.dumps({'repo':repo,'status':result['status'],'revision':result.get('revision'),'elements':result.get('header_parameter_elements'),'complete':result.get('header_inventory_complete')}), flush=True)
    return result

def download_file(repo, sha, item, folder):
    name = item['rfilename']
    target = folder / name
    expected = (item.get('lfs') or {}).get('sha256')
    digest = hashlib.sha256()
    if target.exists() and target.stat().st_size == item['size']:
        with target.open('rb') as h:
            for block in iter(lambda:h.read(8*1024*1024), b''): digest.update(block)
        if expected and digest.hexdigest() == expected:
            return {'file': name, 'bytes': target.stat().st_size, 'sha256': expected, 'verified_against_hf_lfs': True}
        digest = hashlib.sha256()
    partial = target.with_suffix(target.suffix + '.partial')
    last = time.monotonic()
    with requests.get(url(repo, sha, name), stream=True, timeout=(20, 180)) as r:
        r.raise_for_status()
        with partial.open('wb') as h:
            for block in r.iter_content(8 * 1024 * 1024):
                if not block: continue
                h.write(block); digest.update(block)
                if time.monotonic()-last > 30:
                    print(json.dumps({'downloading':name,'bytes':h.tell(),'expected':item['size']}),flush=True);last=time.monotonic()
    actual = digest.hexdigest()
    if partial.stat().st_size != item['size'] or not expected or actual != expected:
        raise ValueError(f'Byte/hash verification failed for {name}')
    partial.replace(target)
    print(json.dumps({'download_complete':name,'bytes':target.stat().st_size,'sha256':actual}),flush=True)
    return {'file':name,'bytes':target.stat().st_size,'sha256':actual,'verified_against_hf_lfs':True}

def download():
    repo = MODELS[0][0]
    folder = ROOT / 'models' / repo.replace('/', '--')
    if not (folder / 'hf_metadata.json').exists(): inspect(repo, PIN)
    info = json.loads((folder / 'hf_metadata.json').read_text(encoding='utf-8'))
    files = [f for f in info['siblings'] if f['rfilename'].endswith('.safetensors') and '/' not in f['rfilename']]
    assert info['sha'] == PIN and files
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(lambda f:download_file(repo,PIN,f,folder), files))
    report = {'repo':repo,'revision':PIN,'complete':True,'weight_bytes':sum(r['bytes'] for r in receipts),'files':receipts,'downloaded_at_utc':datetime.now(timezone.utc).isoformat(),'loaded_for_inference':False}
    save(ROOT / 'granite_download_receipt.json', report)
    print(json.dumps(report),flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['metadata','download'])
    parser.add_argument('--manifest', type=Path, help='Use exact comparison revisions from a saved model_inventory.json')
    args = parser.parse_args()
    if args.action == 'metadata':
        selected_models = MODELS
        if args.manifest:
            frozen = json.loads(args.manifest.read_text(encoding='utf-8'))
            selected_models = [(m['repo'],m['revision']) for m in frozen['models']]
            if selected_models[0] != MODELS[0]:
                raise ValueError('Frozen inventory must retain the pinned Granite student')
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda pair:inspect(*pair), selected_models))
        save(ROOT / 'model_inventory.json', {'observed_date':datetime.now(timezone.utc).date().isoformat(),'models':results})
    else: download()
