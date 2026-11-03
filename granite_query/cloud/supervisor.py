"""Durable local supervisor checkpoint. No network calls or paid launches."""
import json
import os
from progress import record, build
from accomplishments import build as build_accomplishments
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
                    if (comparison/'review_complete.json').exists():
                        training_action = 'Await user review of the completed pilot; no additional paid jobs are queued.'
            elif (comparison / 'input.json').exists():
                remote_status = {'stage':'comparison_launch_prepared'}
                training_action = 'Launch the prepared ranked/random worker once; inspect reservations and existing Modal apps first.'
            elif (comparison / 'teacher_summary.json').exists():
                remote_status = {'stage':'selecting_shared_teacher_pool'}
                training_action = 'Run cloud/comparison_control.py select to freeze ranked/random subsets from the shared verified pool.'
            else:
                remote_status = {'stage':'teacher_generation'}
                training_action = 'Inspect the teacher collector lock and process; do not duplicate active generation. Resume only after confirming no collector is running.'
        improvement=ROOT/'runs/matched_eval64_v1'
        larger=ROOT/'runs/granite_full120_v1'
        improving=(improvement/'plan.json').exists()
        if improving:
            if not (improvement/'result.json').exists():
                p=improvement/'remote_status.json'
                remote_status=json.loads(p.read_text()) if p.exists() else {'stage':'queued'}
                training_action='Poll improvement_control.py poll --run eval. Preserve partial outputs; if confirmed timeout, prepare the single bounded resume before any relaunch.'
            elif not (larger/'result.json').exists():
                if (larger/'launch.json').exists():
                    p=larger/'remote_status.json'
                    remote_status=json.loads(p.read_text()) if p.exists() else {'stage':'queued'}
                    training_action='Poll improvement_control.py poll --run train; do not duplicate the active job.'
                else:
                    remote_status={'stage':'full120_training_queued'}
                    training_action='After confirming the evaluation GPU call stopped, launch the already-reserved full120 training worker once.'
            else:
                remote_status={'stage':'matched64_analysis'}
                training_action='Compare all checkpoints on the shared64 questions, then advance the token-matched student-aware versus random study in progress/RESEARCH_EXECUTION_PLAN.md. Continue regardless of whether more-data training improved; preserve funds for final evaluation and a capped API trial.'
        valuation_folders=[ROOT/f'runs/student_valuation32768_seed{seed}_{arm}_v1'
                           for seed,arm in ((42,'random'),(42,'valued'),(43,'valued'),(43,'random'))]
        if (larger/'result.json').exists() and any((folder/'plan.json').exists() for folder in valuation_folders):
            pending=next((folder for folder in valuation_folders if not (folder/'result.json').exists()),None)
            if pending:
                if (pending/'launch.json').exists():
                    p=pending/'remote_status.json'
                    remote_status=json.loads(p.read_text()) if p.exists() else {'stage':'queued'}
                    training_action='Poll the existing exact-token arm with valuation_control.py poll --folder '+pending.name+'. Preserve its outputs; do not duplicate the call.'
                else:
                    remote_status={'stage':'exact_token_arm_prepared'}
                    training_action='Refresh provider budget reconciliation and confirm the previous GPU stopped, then reserve and launch the prepared '+pending.name+' once.'
            else:
                remote_status={'stage':'next_data_efficiency_cohort'}
                training_action='Analyze both matched seeds, advance the HF import registry and a separately frozen larger token-budget cohort using remaining credits; preserve final evaluation and capped serving allowance. The first four arms are not project completion.'
        math_teacher=ROOT/'runs/math_source_teacher1800_v1'
        if (math_teacher/'teacher_summary.json').exists():
            teacher=json.loads((math_teacher/'teacher_summary.json').read_text())
            if teacher.get('stage')!='completed':
                remote_status={'stage':'multi_source_teacher_collection','completed':teacher.get('completed',0),'total':teacher.get('requested',1800)}
                training_action='Inspect the existing multi-source teacher collector and funding watcher; preserve original receipts and do not duplicate transmitted requests.'
            elif all((folder/'result.json').exists() for folder in valuation_folders):
                remote_status={'stage':'gradient_feature_preparation'}
                training_action='Advance the separately frozen gradient selector and source-reference audit on the completed multi-source pool. The initial two seed pairs showed no skill-selector advantage.'
        feature_folder=ROOT/'runs/gradient_features_math_v1'
        feature_attempts=[p for p in (ROOT/'runs').glob('gradient_features_math*') if (p/'plan.json').exists()]
        if feature_attempts:
            feature_folder=max(feature_attempts,key=lambda p:json.loads((p/'plan.json').read_text()).get('created_at_utc',''))
        if (feature_folder/'plan.json').exists():
            feature_result=json.loads((feature_folder/'result.json').read_text()) if (feature_folder/'result.json').exists() else {}
            feature_terminal=json.loads((feature_folder/'terminal.json').read_text()) if (feature_folder/'terminal.json').exists() else {}
            if (feature_folder/'launch.json').exists() and not feature_terminal.get('confirmed_terminal'):
                remote_status=json.loads((feature_folder/'remote_status.json').read_text()) if (feature_folder/'remote_status.json').exists() else {'stage':'gradient_features_queued'}
                training_action='Poll the saved gradient_feature_control.py call; preserve checkpointed features and finish source-reference auditing. Never duplicate the call.'
            elif feature_result.get('stage')=='completed':
                remote_status={'stage':'gradient_features_completed'}
                training_action='Download and hash-check the private feature export, audit scores, then freeze the common-pool random/skill/gradient token-budget grid with data_efficiency_control.py. Reserve and launch only one reviewed arm at a time.'
            elif feature_terminal.get('confirmed_terminal'):
                remote_status={'stage':feature_terminal.get('stage','gradient_features_terminal')}
                training_action='Inspect terminal feature artifacts. A late calibration refusal may continue only after verified complete earlier features, final warmup snapshot, unchanged execution-source hashes and a fresh remaining-work forecast fit the same per-call bounds. Initial infeasible calibration requires a smaller new cohort; never recompute blindly.'
        batched_baseline=ROOT/'runs/student_baseline_batched64_v1'
        if (batched_baseline/'launch.json').exists() and not (batched_baseline/'result.json').exists():
            remote_status=json.loads((batched_baseline/'remote_status.json').read_text()) if (batched_baseline/'remote_status.json').exists() else {'stage':'batched_baseline_queued'}
            training_action='Poll the existing untouched-Granite batch8 baseline with valuation_control.py. It uses the same64 questions and512-token settings as new adapters; no training or duplicate GPU launch. Reconcile its result before the gradient continuation.'
        human_teacher=ROOT/'runs/human_math_teacher2048_v1'
        if (human_teacher/'teacher_summary.json').exists():
            human_summary=json.loads((human_teacher/'teacher_summary.json').read_text(encoding='utf-8'))
            if human_summary.get('stage')=='collecting':
                training_action+=' Monitor the existing separately funded human-reference teacher chunk; do not overlap collectors. Each later512-request chunk requires its own fresh funding check and reservation.'
        open_calls=any(job.get('status') in ('spawned','running','spawning','queued') for job in ledger.get('jobs',[]))
        allocation_full=exhausted
        exhausted=allocation_full and not open_calls
        status = {'updated_at_utc': datetime.now(timezone.utc).isoformat(),
            'mode': 'budget_exhausted' if exhausted else ('ready_for_agent' if improving else ('awaiting_review' if (comparison/'review_complete.json').exists() else 'ready_for_agent')),
            'teacher_pilot_complete': summary.get('completed') == 16,
            'teacher_pilot': summary, 'last_recorded_connectivity': connectivity,
            'training_worker_exists': training_ready,
            'next_action': 'Stop paid work and report budget ceiling.' if exhausted else
                training_action,
            'training_progress': {k: v for k, v in remote_status.items() if k in ('stage', 'steps', 'total_steps', 'elapsed_seconds', 'supervised_tokens','completed','total','completed_features','total_features')},
            'paid_work_launched_by_tick': False,
            'budget_allocation_full':allocation_full}
        account=ledger.get('modal_budget_accounting',{})
        if account:
            status['public_budget']={key:account[key] for key in ('observed_metered_usd','collection_lag_buffer_usd','active_reservations_usd','pending_terminal_liability_usd','budget_remaining_usd') if key in account}
            status['public_budget']['active_reservations_usd']=sum(j['reserved_usd'] for j in ledger.get('jobs',[]) if j.get('service','modal')=='modal' and j.get('status') in ('reserved','running','spawned','spawning','queued'))
            status['public_budget']['budget_remaining_usd']=max(0,round(ledger['limits']['modal']-ledger['estimated_spend']['modal']-ledger['reserved']['modal'],2))
            status['public_budget']['deepseek_peak_estimate_usd']=ledger.get('deepseek_recorded_peak_estimate_usd',ledger['estimated_spend']['deepseek'])
            deepseek_account=ledger.get('deepseek_budget_accounting',{})
            if deepseek_account.get('status')=='conditional_wallet_inference':
                status['public_budget']['deepseek_observed_usage_usd']=deepseek_account['observed_project_usage_usd']
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
        record('in_progress', 'Research improvement cycle' if improving else ('Ranked versus random supervision' if (comparison/'plan.json').exists() else 'Granite training smoke test'),
               status['next_action'], event_id='supervisor-next-' + status['next_action'])
        build_accomplishments()
        if any((folder/'plan.json').exists() for folder in valuation_folders):
            from valuation_report import build as build_valuation_report
            build_valuation_report()
        efficiency_grid=ROOT/'runs/data_efficiency_math_v1'
        if (efficiency_grid/'grid_manifest.json').exists():
            from data_efficiency_report import build as build_efficiency_report
            build_efficiency_report(grid=efficiency_grid)
        build(status)
        print(json.dumps(status))
    finally:
        os.close(fd)
        lock.unlink()

if __name__ == '__main__':
    tick()
