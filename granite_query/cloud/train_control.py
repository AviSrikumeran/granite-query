"""Prepare or poll one bounded training smoke test; never auto-relaunch."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
RUN = ROOT / 'runs/granite42_3b_smoke_seed42_v1'
sys.path.insert(0, str(ROOT.parent))
from ranking.verification import teacher_eligible
from cloud.progress import record, build

def write(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temp.replace(path)

def prepare():
    RUN.mkdir(parents=True, exist_ok=True)
    if (RUN / 'plan.json').exists():
        print('Existing plan retained; do not duplicate launch.')
        return
    source = ROOT / 'runs/deepseek_api_pilot16_seed42/results.jsonl'
    rows = [r for r in map(json.loads, source.read_text(encoding='utf-8').splitlines()) if teacher_eligible(r)[0]]
    if len(rows) != 15:
        raise ValueError('Expected 15 strictly verified teacher records')
    if any(r.get('source_split') != 'train' for r in rows):
        raise ValueError('Only official training records are permitted')
    train_ids, development_ids = [r['id'] for r in rows[:12]], [r['id'] for r in rows[12:]]
    plan = {'run_id': RUN.name, 'model': 'ibm-granite/granite-4.2-3b',
        'revision': '4e9c275e232f10211ec88644d106a1f6a1b60e06',
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'train_ids': train_ids, 'development_ids': development_ids, 'seed': 42,
        'held_out_test_used': False, 'max_steps': 12, 'max_context': 1024,
        'learning_rate': 1e-4, 'lora_r': 8, 'lora_alpha': 16,
        'train_answer_only': True, 'enable_thinking': False,
        'gpu': 'A100-80GB', 'timeout_seconds': 900,
        'reserved_usd': 3, 'volume': 'granite-query-training-artifacts',
        'pricing_checked': '2026-11-03', 'pricing_source': 'https://modal.com/pricing',
        'gpu_rate_usd_per_second': 0.000694,
        'purpose': 'compatibility smoke test, not ranked/random comparison'}
    ledger_path = ROOT / 'runs/supervisor/budget.json'
    ledger = json.loads(ledger_path.read_text())
    if any(j.get('status') not in ('completed', 'failed', 'cancelled') for j in ledger['jobs']):
        raise RuntimeError('Another job reservation requires reconciliation')
    if ledger['estimated_spend']['modal'] + ledger['reserved']['modal'] + 3 > ledger['limits']['modal']:
        raise RuntimeError('Insufficient remaining Modal budget')
    ledger['reserved']['modal'] += 3
    ledger['jobs'].append({'run_id': RUN.name, 'reserved_usd': 3, 'status': 'reserved',
                          'created_at_utc': datetime.now(timezone.utc).isoformat()})
    write(ledger_path, ledger)
    write(RUN / 'plan.json', plan)
    public_fields = ('id', 'prompt', 'response', 'gold_answer')
    (RUN / 'training_input.jsonl').write_text('\n'.join(json.dumps({k: r[k] for k in public_fields}) for r in rows)+'\n', encoding='utf-8')
    record('in_progress', 'Granite LoRA smoke test prepared',
        'Pinned Granite 4.2 3B; 12 verified teacher training examples and 3 separate training-split development examples. One A100, 900-second limit, 3-dollar reservation. No held-out test data.')
    write(ROOT.parents[1] / 'progress/current.json', {'stage': 'Granite training launch prepared',
          'training_completed': False, 'held_out_evaluation_completed': False})
    print(json.dumps({'prepared': str(RUN), 'train_count': 12, 'development_count': 3, 'reserved_usd': 3}))

def poll():
    import modal
    launch_path = RUN / 'launch.json'
    if not launch_path.exists():
        raise SystemExit('No launch record; training has not been spawned')
    launch = json.loads(launch_path.read_text())
    if not launch.get('call_id'):
        raise SystemExit('Ambiguous spawn: inspect Modal before any retry')
    remote = modal.Dict.from_name('granite-query-training-progress')
    status = remote.get(RUN.name, {'stage': 'queued'})
    write(RUN / 'remote_status.json', status)
    call = modal.FunctionCall.from_id(launch['call_id'])
    try:
        result = call.get(timeout=0)
    except TimeoutError:
        result = None
    except Exception as exc:
        status = dict(status, stage='failed', error_type=type(exc).__name__, error=str(exc))
        write(RUN / 'remote_status.json', status)
        record('failed', 'Granite smoke test failed', 'The worker stopped before completion. Inspect saved runtime logs and artifacts before retrying.', event_id=RUN.name+'-failed')
        result = None
    if result is not None:
        write(RUN / 'result.json', result)
        record('completed', 'Granite LoRA smoke test completed',
            'Adapter training, save, reload, and three development generations completed. This is a wiring check, not evidence of generalization improvement.', event_id=RUN.name+'-completed')
    current = {'stage': 'Granite smoke test: ' + status['stage'],
        'training_completed': result is not None, 'held_out_evaluation_completed': False}
    write(ROOT.parents[1] / 'progress/current.json', current)
    print(json.dumps(status))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'poll'])
    args = parser.parse_args()
    prepare() if args.action == 'prepare' else poll()
