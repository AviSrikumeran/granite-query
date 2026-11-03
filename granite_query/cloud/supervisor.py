"""Durable local supervisor checkpoint. No network calls or paid launches."""
import json
import os
from progress import record, build
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / 'runs/supervisor'

def tick():
    STATE.mkdir(parents=True, exist_ok=True)
    lock = STATE / 'tick.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit('Another tick owns the lock. Inspect the owner before recovering it.')
    try:
        os.write(fd, str(os.getpid()).encode())
        config = json.loads((ROOT / 'supervisor_config.json').read_text(encoding='utf-8'))
        pilot = ROOT / 'runs/deepseek_api_pilot16_seed42'
        summary_path = pilot / 'summary.json'
        summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
        connectivity_path = pilot / 'connectivity.json'
        connectivity = json.loads(connectivity_path.read_text(encoding='utf-8')) if connectivity_path.exists() else {}
        ledger_path = STATE / 'budget.json'
        if not ledger_path.exists():
            ledger = {'currency': 'USD', 'limits': config['budget_usd'],
                'estimated_spend': {'deepseek': 0.03, 'modal': 0.0},
                'reserved': {'deepseek': 0.0, 'modal': 0.0},
                'note': 'DeepSeek pilot conservative estimate, not invoice; reconcile before paid expansion.',
                'jobs': []}
            ledger_path.write_text(json.dumps(ledger, indent=2), encoding='utf-8')
        ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
        exhausted = any(ledger['estimated_spend'][service] + ledger['reserved'][service] >= limit
                        for service, limit in ledger['limits'].items())
        training_ready = (ROOT / 'modal_train.py').exists()
        status = {'updated_at_utc': datetime.now(timezone.utc).isoformat(),
            'mode': 'budget_exhausted' if exhausted else 'ready_for_agent',
            'teacher_pilot_complete': summary.get('completed') == 16,
            'teacher_pilot': summary, 'last_recorded_connectivity': connectivity,
            'training_worker_exists': training_ready,
            'next_action': 'Stop paid work and report budget ceiling.' if exhausted else
                ('Inspect and test training worker before any bounded launch.' if training_ready else
                 'Implement and locally validate the bounded Granite LoRA training smoke test.'),
            'paid_work_launched_by_tick': False}
        temp = STATE / 'status.tmp'
        temp.write_text(json.dumps(status, indent=2), encoding='utf-8')
        temp.replace(STATE / 'status.json')
        report = '\n'.join(['# Granite Query supervisor', '',
            'Updated: ' + status['updated_at_utc'],
            'Mode: ' + status['mode'],
            f"Teacher pilot: {summary.get('completed', 0)}/16 responses; {summary.get('verified_final_answers', 0)} strict final-answer passes.",
            'Next action: ' + status['next_action'],
            'No paid work is launched by this checkpoint command.',
            'The scheduled agent implements, tests, and advances stages using the runbook.', ''])
        (STATE / 'latest_report.md').write_text(report, encoding='utf-8')
        with (STATE / 'events.jsonl').open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(status) + '\n')
        record('in_progress', 'Granite training smoke test',
               status['next_action'], event_id='supervisor-next-' + status['next_action'])
        build(status)
        print(json.dumps(status))
    finally:
        os.close(fd)
        lock.unlink()

if __name__ == '__main__':
    tick()
