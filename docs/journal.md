# Granite Query research journal

Can student aware data selection help Granite learn mathematical reasoning from DeepSeek more efficiently than random selection?

This is a generated, append-only history. Corrections are new events, not edits to earlier evidence.

Current stage: matched_eval64_v1: baseline_evaluation

Next: Poll improvement_control.py poll --run eval. Preserve partial outputs; if confirmed timeout, prepare the single bounded resume before any relaunch.

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

## 2026-11-03T17:26:29.823030+00:00 | completed | Granite LoRA smoke test completed

Adapter training, save, reload, and three development generations completed. This is a wiring check, not evidence of generalization improvement.

## 2026-11-03T17:26:36.935773+00:00 | in_progress | Granite training smoke test

Review saved adapter and smoke-test results; reconcile costs before the controlled comparison.

## 2026-11-03T17:27:07.771728+00:00 | decision | Smoke-test results are not benchmark accuracy

All 12 optimizer updates completed and adapter parameters changed. The saved adapter reloaded and all three development answers matched their reference numbers. Baseline responses were limited to 192 tokens and two were visibly truncated, so this tiny comparison cannot establish accuracy improvement. Preserve these outputs and use an adequate shared generation budget in the controlled experiment.

## 2026-11-03T17:29:53.350046+00:00 | in_progress | Ranked versus random comparison frozen

128 new candidate questions, 32 examples per arm, and 16 separate training-split development questions. Both arms start from pinned Granite 4.2 3B with identical LoRA settings. One seed; equal example counts, with actual token counts reported. Reserved 3 dollars DeepSeek and 3 dollars Modal. No official test data.

## 2026-11-03T17:31:10.552613+00:00 | in_progress | Granite training smoke test

Inspect the teacher collector lock and process; do not duplicate active generation. Resume only after confirming no collector is running.

## 2026-11-03T17:32:18.672087+00:00 | in_progress | Teacher collection passed the halfway point

More than 64 of 128 candidate attempts have been saved. Rejected outputs remain preserved and excluded from both training arms. The experiment plan and numerical scoring policy are frozen before student evaluation.

## 2026-11-03T17:33:17.009760+00:00 | completed | Shared teacher pool generated

Received 128 candidate attempts; 120 passed strict final-answer checks. Raw outputs and rejected records retained. The same eligible pool feeds both selectors.

## 2026-11-03T17:33:23.570169+00:00 | completed | Ranked and random subsets selected

Selected 32 examples per arm from 120 identical eligible candidates. Overlap: 9 examples. BM25 uses frozen prompt-only relevance scores; random selection uses seed 42. Training and development IDs are disjoint.

## 2026-11-03T17:34:06.838308+00:00 | in_progress | Ranked versus random GPU worker launched

A single detached A100 worker will evaluate the untouched model and train/evaluate two independent adapters sequentially. Each arm has 32 verified examples, with 9 shared examples. All use the same 16 development questions and 512-token generation cap. Current GPU reservation: 3 dollars.

## 2026-11-03T17:34:06.938277+00:00 | in_progress | Granite training smoke test

Poll the existing ranked/random call with cloud/comparison_control.py poll, then summarize outcomes and limitations.

## 2026-11-03T17:34:10.225399+00:00 | in_progress | Comparison worker: baseline evaluation

Polling the existing detached call; no duplicate job launched.

## 2026-11-03T17:35:21.217646+00:00 | in_progress | Comparison worker: ranked training

Polling the existing detached call; no duplicate job launched.

## 2026-11-03T17:36:55.435218+00:00 | in_progress | Comparison worker: ranked evaluation

Polling the existing detached call; no duplicate job launched.

## 2026-11-03T17:37:44.963107+00:00 | in_progress | Comparison worker: random training

Polling the existing detached call; no duplicate job launched.

## 2026-11-03T17:38:55.137750+00:00 | decision | Interpretation audit identified selection confounds

The first comparison matches 32 examples and optimizer updates, but selected solution lengths and training order differ. Ranked examples are trained in BM25 order while random examples are shuffled. Development question text also contributed to the pre-existing reference index statistics, though development answers and outcomes were not ranking inputs. Report these limits, preserve the frozen run, and avoid claiming that ranking alone caused any difference.

## 2026-11-03T17:38:58.193791+00:00 | in_progress | Comparison worker: random evaluation

Polling the existing detached call; no duplicate job launched.

## 2026-11-03T17:40:14.012471+00:00 | completed | First ranked versus random run completed

Numeric development matches out of 16: baseline 13, ranked 13, random 13. Supervised training tokens: ranked 3260, random 2534. Both adapters and raw evaluations saved. One seed and development data only; no final-test or robust generalization claim.

## 2026-11-03T17:41:13.512606+00:00 | completed | Comparison results independently audited

Original Granite, BM25 selected, and random selected each scored 13 of 16. All 48 outputs have plain numeric final answers and no truncation. Ranked fixes one baseline error but introduces another; random has the same correctness pattern as baseline. Ranked used 3260 supervised tokens versus 2534 for random, about 28.65 percent more. No ranking accuracy or fixed-token efficiency advantage is demonstrated. One ambiguous benchmark item is retained under the frozen scoring policy.

## 2026-11-03T17:41:13.523829+00:00 | decision | Further paid expansion stopped pending review

Both adapters and evaluation outputs are preserved. The first comparison is complete. A confirmatory run should match token budgets, use the same shuffled order policy, exclude development questions from relevance-index fitting, and repeat across seeds. No additional GPU jobs are queued.

## 2026-11-03T17:41:13.663789+00:00 | in_progress | Ranked versus random supervision

Await user review of the completed pilot; no additional paid jobs are queued.

## 2026-11-03T17:51:14.710976+00:00 | planned | Shared64 benchmark and full120 training frozen

A new64 development monitoring set is disjoint from the earlier pilot, teacher candidates and old development questions. Evaluate original Granite and saved32-example adapters, then train a fresh adapter on all120 verified teacher examples. Reuse the same64 questions for before/after comparisons. Official test remains untouched. Improvement is measured, not assumed.

## 2026-11-03T17:53:26.208809+00:00 | in_progress | Shared64 worker: baseline evaluation

Polling the existing detached call; no duplicate job launched.

## 2026-11-03T17:56:23.698350+00:00 | decision | Full project continues beyond the tied pilot

The user clarified that completion requires matched DeepSeek and Granite baselines, visual evidence, and further measured Granite improvement rounds. The pilot alone is not project completion. Supervision is restored for the queued shared64 benchmark and full120 training cycle.

## 2026-11-03T17:56:23.709459+00:00 | completed | DeepSeek baseline measured on identical16 questions

DeepSeek Pro scored15/16 versus13/16 for original Granite and both32-example adapters on exactly the same questions. All outcomes retained. DeepSeek used thinking with4096 output-token cap; Granite used non-thinking with512. Different timing scopes and inference budgets are disclosed.

## 2026-11-03T17:56:23.719457+00:00 | in_progress | Larger shared64 evaluation started

One detached A100 is evaluating untouched Granite and the saved32-example adapters on a new frozen64 monitoring set. DeepSeek is being evaluated on exactly that set too. A fresh120-example training round is queued after the GPU evaluation; charts will use only measured matched-set results.

## 2026-11-03T17:56:23.838779+00:00 | in_progress | Research improvement cycle

Poll improvement_control.py poll --run eval. Preserve partial outputs; if confirmed timeout, prepare the single bounded resume before any relaunch.
