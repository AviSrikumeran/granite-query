# Granite Query: Learning More from Less

Can student aware data selection help Granite learn mathematical reasoning from DeepSeek more efficiently than random selection?

This project studies verified teacher-data selection for IBM Granite on GSM8K. It compares random selection with BM25 relevance and, later, student-aware selection under comparable training budgets. Accuracy is primary; explanation quality, training cost, and inference latency are separate outcomes.

## Research status

The first DeepSeek API pilot completed 16 seeded training questions. Fifteen passed the strict numeric-answer verifier; one correct numeric answer was rejected because it included a currency symbol. Granite's initial LoRA train/save/reload smoke test then completed. Neither establishes generalization improvement.

The [first ranked versus random development pilot](progress/COMPARISON_PLAN.md) is complete. Original Granite, BM25 selected training, and random selected training each scored **13/16 (81.25%)**. Ranked used 3,260 supervised training tokens versus 2,534 for random, with 32 examples per arm. This one-seed pilot demonstrates no ranking advantage; it does not establish equivalence or final-test generalization. The official test split remains untouched. See the [results and limitations](progress/RESULTS.md).

## Live progress

- [Research dashboard](https://avisrikumeran.github.io/granite-query/)
- [Growing research journal](progress/JOURNAL.md)
- [Structured event history](progress/events.jsonl)
- [Public status snapshot](docs/status.json)

The supervisor records meaningful completions, active work, failures, solutions, and design decisions. Public summaries are explicitly authored; private runtime logs, credentials, datasets, and raw model outputs are excluded. Scheduled agent runs regenerate the snapshot and synchronize allowlisted files to this repository. The dashboard polls its published snapshot every minute; GitHub publishing adds delay, so it is near-live, not a direct stream from Modal.

## Local checkpoint and journal

Run `granite_query/cloud/supervisor.py` with the project Python environment. Record a new event using `granite_query/cloud/progress.py --kind completed --title "Milestone" --detail "Public summary"`. Valid event types are completed, in_progress, failed, resolved, planned, and decision. Corrections are new entries; do not erase earlier evidence. Update `progress/current.json` as milestones change, then rebuild the export. The local scheduler is separate from GitHub Pages and requires the computer and app to stay running.

## Hosting

GitHub Pages serves the `docs` directory on the `main` branch. It hosts a static research dashboard; it does not run training or keep API keys. The later model demonstration will use a backend calling an evaluated Granite checkpoint on Modal. Vercel is the planned later website/backend host.

## Evidence and limits

Reserve development data separately from final test data; do not tune selection against the final test. Record model revisions, teacher provenance, seeds, selected IDs, training tokens, costs, and per-question outcomes. Report random controls and failed experiments. Current service ceiling: $30 Modal and $20 DeepSeek. Local cost tracking is not a provider-enforced billing limit.
