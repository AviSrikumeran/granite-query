"""Bounded, resumable 16-question API smoke test; never reads test data."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import urllib.error
import winreg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ranking.verification import teacher_eligible

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'runs/deepseek32b_pilot16_seed42'
OUT = ROOT / 'runs/deepseek_api_pilot16_seed42'
MODEL = 'deepseek-v4-pro'

def credential(name):
    value = os.environ.get(name)
    if not value:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
                value = winreg.QueryValueEx(key, name)[0]
        except FileNotFoundError:
            pass
    return value

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    key = credential('DEEPSEEK_API_KEY')
    if not key:
        raise SystemExit('DeepSeek credential missing')
    def api(path, payload=None):
        req = urllib.request.Request('https://api.deepseek.com' + path,
            data=json.dumps(payload).encode() if payload else None,
            headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError('DeepSeek HTTP ' + str(exc.code)) from None
        except urllib.error.URLError:
            raise RuntimeError('DeepSeek network connection failed') from None
    def modal_check():
        try:
            result = subprocess.run([sys.executable, '-m', 'modal', 'token', 'info'],
                capture_output=True, timeout=30)
            return {'verified': result.returncode == 0, 'exit_code': result.returncode}
        except subprocess.TimeoutExpired:
            return {'verified': False, 'error': 'authentication check timed out'}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        modal_future = executor.submit(modal_check)
        models = api('/models')
        available = [m['id'] for m in models.get('data', [])]
        checks = {'deepseek_authenticated': True, 'available_models': available,
                  'modal': modal_future.result()}
    (OUT / 'connectivity.json').write_text(json.dumps(checks, indent=2), encoding='utf-8')
    print(json.dumps(checks), flush=True)
    if MODEL not in available:
        raise SystemExit('Chosen teacher unavailable; no generation launched')
    requests = [json.loads(line) for line in (SOURCE / 'requests.jsonl').read_text(encoding='utf-8').splitlines()]
    sources = {r['id']: r for r in map(json.loads, (SOURCE / 'local_sources.jsonl').read_text(encoding='utf-8').splitlines())}
    settings = {'model': MODEL, 'max_tokens': 4096, 'stream': False,
                'thinking': {'type': 'enabled'}}
    manifest = {'model': MODEL, 'api_revision': 'mutable API alias; actual response model saved per example',
        'size': 16, 'seed': 42, 'settings': settings, 'retries': 0,
        'requests_sha256': hashlib.sha256((SOURCE / 'requests.jsonl').read_bytes()).hexdigest(),
        'held_out_data_used': False, 'gpu_jobs_launched': False,
        'max_completion_tokens_total': 65536, 'purpose': 'formatting and connectivity pilot, not benchmark'}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    results_file = OUT / 'results.jsonl'
    rows = [json.loads(line) for line in results_file.read_text(encoding='utf-8').splitlines()] if results_file.exists() else []
    done = {r['id'] for r in rows}
    started = time.monotonic()
    for request in requests:
        if request['id'] in done:
            continue
        if time.monotonic() - started > 900:
            break
        payload = dict(settings, messages=[{'role': 'system', 'content':
            'Solve the math problem. Explain the necessary calculation steps clearly. End with exactly #### followed by the numeric final answer. No text after the final answer.'},
            {'role': 'user', 'content': request['prompt']}])
        before = time.monotonic()
        raw = api('/chat/completions', payload)
        choice = raw['choices'][0]
        row = dict(sources[request['id']], response=choice['message'].get('content') or '',
            teacher_model=MODEL, teacher_revision=raw.get('model', MODEL),
            finish_reason=choice.get('finish_reason'), elapsed_seconds=time.monotonic()-before,
            generation={'prompt_version': 'gsm8k-api-v1', 'settings': settings}, raw=raw)
        row['eligible'], row['verification'] = teacher_eligible(row)
        with results_file.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
        rows.append(row)
        print(json.dumps({'completed': len(rows), 'id': row['id'], 'verification': row['verification']}), flush=True)
    summary = {'completed': len(rows), 'verified_final_answers': sum(r['eligible'] for r in rows),
        'completion_tokens': sum(r['raw'].get('usage', {}).get('completion_tokens', 0) for r in rows),
        'prompt_tokens': sum(r['raw'].get('usage', {}).get('prompt_tokens', 0) for r in rows),
        'held_out_data_used': False, 'not_a_test_accuracy_estimate': True}
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary), flush=True)

if __name__ == '__main__':
    main()
