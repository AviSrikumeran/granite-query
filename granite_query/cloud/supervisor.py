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
        training_folder = ROOT / 'runs/granite42_3b_smoke_seed42_v1'
        launch_path = training_folder / 'launch.json'
        remote_path = training_folder / 'remote_status.json'
        launch = json.loads(launch_path.read_text()) if launch_path.exists() else {}
        remote_status = json.loads(remote_path.read_text()) if remote_path.exists() else {}
        training_action = ('Inspect and test training worker before any bounded launch.' if training_ready else
                           'Implement and locally validate the bounded Granite LoRA training smoke test.')
        if launch:
            training_action = 'Poll the existing Granite call using cloud/train_control.py poll; do not relaunch.'
            if remote_status.get('stage') == 'completed':
                training_action = 'Review saved adapter and smoke-test results; reconcile costs before the controlled comparison.'
            elif remote_status.get('stage') == 'failed':
                training_action = 'Inspect the failed Granite call and saved error; fix and validate before a separately recorded retry.'
        comparison = ROOT / 'runs/ranked_random_32_seed42_v1'
        if (comparison / 'plan.json').exists():
            if (comparison / 'launch.json').exists():
                comparison_status_path = comparison / 'remote_status.json'
                remote_status = json.loads(comparison_status_path.read_text()) if comparison_status_path.exists() else {'stage':'queued'}
                training_action = 'Poll the existing ranked/random call with cloud/comparison_control.py poll, then summarize outcomes and limitations.'
                if remote_status.get('stage') == 'completed':
                    training_action = 'Analyze and publish the completed ranked/random pilot, report uncertainty, and stop further paid expansion until reviewed.'
            elif (comparison / 'input.json').exists():
                remote_status = {'stage':'comparison_launch_prepared'}
                training_action = 'Launch the prepared ranked/random worker once; inspect reservations and existing Modal apps first.'
            elif (comparison / 'teacher_summary.json').exists():
                remote_status = {'stage':'selecting_shared_teacher_pool'}
                training_action = 'Run cloud/comparison_control.py select to freeze ranked/random subsets from the shared verified pool.'
            else:
                remote_status = {'stage':'teacher_generation'}
                training_action = 'Inspect the teacher collector lock and process; do not duplicate active generation. Resume only after confirming no collector is running.'
        status = {'updated_at_utc': datetime.now(timezone.utc).isoformat(),
            'mode': 'budget_exhausted' if exhausted else 'ready_for_agent',
            'teacher_pilot_complete': summary.get('completed') == 16,
            'teacher_pilot': summary, 'last_recorded_connectivity': connectivity,
            'training_worker_exists': training_ready,
            'next_action': 'Stop paid work and report budget ceiling.' if exhausted else
                training_action,
            'training_progress': {k: v for k, v in remote_status.items() if k in ('stage', 'steps', 'total_steps', 'elapsed_seconds', 'supervised_tokens')},
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
