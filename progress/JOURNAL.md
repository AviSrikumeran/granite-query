# Granite Query research journal

Can student aware data selection help Granite learn mathematical reasoning from DeepSeek more efficiently than random selection?

This is a generated, append-only history. Corrections are new events, not edits to earlier evidence.

Current stage: Granite smoke test: training

Next: Poll the existing Granite call using cloud/train_control.py poll; do not relaunch.

> Teacher pilot uses training questions. It is not held-out accuracy or evidence of Granite improvement.

## 2026-11-03T17:13:50.632907+00:00 | completed | Teacher API pilot completed

All 16 seeded GSM8K training questions received DeepSeek responses. Fifteen passed the strict verifier. No test questions or Granite training were used.

## 2026-11-03T17:13:50.633437+00:00 | failed | Correct answer rejected for currency formatting

One solution ended with a dollar sign before 13. The strict numeric parser rejected it; this is a formatting rejection, not evidence of incorrect arithmetic. Original output retained.

## 2026-11-03T17:13:50.633437+00:00 | resolved | Sandbox network failure resolved

The first connectivity attempt failed to resolve the provider hostname. The authorized network-enabled retry verified both services and completed the pilot.

## 2026-11-03T17:13:50.652926+00:00 | completed | Scheduled supervision enabled

A recurring check is configured every 15 minutes, with durable local state and approximately hourly active progress reports. Local checks require the computer and app to remain running.

## 2026-11-03T17:13:50.658925+00:00 | in_progress | Public research journal and Pages preview

Preparing an append-only activity history, generated journal, and public dashboard. Publication will be verified before being reported as live.

## 2026-11-03T17:13:50.752906+00:00 | in_progress | Granite training smoke test

Implement and locally validate the bounded Granite LoRA training smoke test.

## 2026-11-03T17:16:22.031306+00:00 | completed | Public GitHub Pages preview verified

The research dashboard is live. Browser verification confirmed the teacher pilot metrics, the journal links, and failure filtering. Scheduled supervision now includes append-only journal updates and public snapshot synchronization.

## 2026-11-03T17:20:55.067242+00:00 | in_progress | Granite LoRA smoke test prepared

Pinned Granite 4.2 3B; 12 verified teacher training examples and 3 separate training-split development examples. One A100, 900-second limit, 3-dollar reservation. No held-out test data.

## 2026-11-03T17:22:50.709677+00:00 | resolved | Modal launch compatibility issues resolved

Corrected CLI module syntax and Windows console encoding. The workspace image builder was newer than the available SDK supports; a supported builder is selected explicitly. Empty apps were reconciled before retrying. The training image is building; no completed training is claimed.

## 2026-11-03T17:23:26.672265+00:00 | in_progress | Granite training job launched

A detached Modal A100 worker is loading pinned Granite 4.2 3B. The smoke test uses 12 optimizer updates on 12 verified teacher examples, followed by adapter save/reload and three development checks. Execution limit: 900 seconds. Reserved budget: 3 dollars. No held-out test evaluation.

## 2026-11-03T17:23:26.774368+00:00 | in_progress | Granite training smoke test

Poll the existing Granite call using cloud/train_control.py poll; do not relaunch.

## 2026-11-03T17:24:24.945949+00:00 | in_progress | Granite worker: training

The existing detached smoke-test worker reported this stage. Completed optimizer steps: 4. This remains a compatibility check, not a benchmark result.
