# Granite Query unattended supervision

The scheduled agent in the current chat advances the project. The local Python checkpoint records durable status; it is not a continuously running training daemon. Modal workers must be launched detached with saved call identifiers and durable outputs so compute can survive the local chat ending. Local supervision still requires this computer and the app to remain running.

## Every scheduled run

1. Read PROJECT_BRIEF.md, this runbook, supervisor_config.json, and runs/supervisor/status.json and budget.json. Run supervisor.py using the project .venv-modal Python. Review events and inspect any saved Modal job IDs before launching anything. Never duplicate a running or ambiguous job.
2. Advance one concrete stage: implement missing pipeline code, validate it locally, launch a bounded job when ready, or inspect/recover a running job. Do not spend all runs merely reporting that training code is missing. Save code, logs, settings, call IDs, completed outputs, and decisions before yielding. Use the existing ranking pipeline and final-answer checker.
3. First implement a minimal Granite LoRA train/save/reload/evaluate smoke test on Modal. Choose a public compatible Granite checkpoint using its official card, pin its weights revision and dependencies, and preserve its chat template. Use only eligible teacher training examples; retain the rejected dollar-sign example and distinguish formatting from mathematical correctness in any revised verifier. Do not rewrite original results.
4. After the smoke test succeeds, prepare verified teacher data and comparable random/BM25 experiments. Keep the same starting weights and optimization settings, log actual training tokens, separate training probes/development from final test, and freeze the comparison before test evaluation. Add student-aware selection only as a separately logged experiment. Never claim the 16-question teacher pilot is held-out accuracy or evidence of student gains.

## Budget and recovery

Budget is $30 Modal plus $20 DeepSeek TOTAL, including existing pilot usage. The budget ledger is a conservative local estimate, not a provider-enforced billing cap. Before every paid launch, check current official rates and available account usage, reconcile prior spend, and reserve a conservative maximum including GPU, CPU, memory, and persistent resources. Stop if costs cannot be bounded or verified; do not silently exceed the per-service limits. Use one GPU job at a time, function timeouts, no warm serving pool, and no automatic full training sweep. The first GPU job is limited to 900 seconds. Save a job reservation and unique ID before launch, then its Modal call ID immediately afterward. An ambiguous launch must be reconciled, never blindly retried. Release reservations only after termination and cost reconciliation. Routine transient failures may retry at most twice within the same reservation; deterministic failures require a fix and local checks first.

Credentials stay in Windows user environment variables or the Modal user configuration. Never print credentials or upload configuration files. Request required network permissions through the normal tool mechanism; inability to obtain them is a real blocker, not permission to bypass controls.

## Reports and stopping

Write an updated local report each run. Give the user an approximately hourly progress report when work is active, plus immediate reports for meaningful completed milestones, failures requiring action, or budget stops. Stay quiet on unchanged idle checks. Label estimates, partial evaluations, and uncertainty. Reports include completed work, accuracy evidence, spend/reservations, next step, and any required user action. Store last_report_at_utc in runs/supervisor/report_state.json to avoid duplicate hourly reports.

Once the bounded comparison and final summary are complete, stop GPU work and pause this supervision schedule. If budget is exhausted, stop paid work, report once, and pause the schedule. Do not repeatedly retry authentication, spend limits, or unavailable credentials. Public model serving/Vercel deployment is a later deliverable; do not create an indefinitely billable endpoint during the research pilot.
