# Granite Query research journal

Can student aware data selection help Granite learn mathematical reasoning from DeepSeek more efficiently than random selection?

This is a generated, append-only history. Corrections are new events, not edits to earlier evidence.

Current stage: Equal-token random training, seed43

Next: A Modal function call was submitted; currently waiting for the next saved worker update. Frozen budget:32,768 supervised tokens and32 token-weighted optimizer updates; uses adaptive development skill information. No selection advantage is claimed before matched results exist.

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

## 2026-11-03T18:07:40.974556+00:00 | in_progress | Shared64 worker: failed

Polling the existing detached call; no duplicate job launched.

## 2026-11-03T18:08:26.359102+00:00 | planned | Resume only unfinished64-question evaluations

The first evaluation attempt ended before all checkpoints finished. A single separately reserved resume preserves completed outputs and evaluates only missing questions under identical frozen conditions. Do not rerun completed phases.

## 2026-11-03T18:10:54.863349+00:00 | in_progress | Shared64 worker: ranked32 evaluation

Polling the existing detached call; no duplicate job launched.

## 2026-11-03T18:13:42.873338+00:00 | completed | Scope and accomplishments audited against saved evidence

Only GSM8K has been used for training; its data came from the canonical author GitHub repository. Granite4.2 3B LoRA adapters really ran on Modal A100 workers:12 smoke-test updates and32 updates in each selection arm. The first16-question experiment showed no accuracy gain. The website now separates completed work, the timed-out evaluation, its running resume, queued120-example training, and uncompleted research claims. Additional dataset cards are researched, not imported.

## 2026-11-03T18:13:42.997596+00:00 | resolved | Larger evaluation resumed without repeating completed work

The original64-question GPU comparison reached its application deadline. Preserved outputs include64 baseline and27 ranked generations. A separately reserved resume is evaluating only101 missing generations. The recovered original Granite baseline is58/64 versus DeepSeek63/64 on identical questions; trained-checkpoint comparisons remain pending.

## 2026-11-03T18:16:17.760766+00:00 | in_progress | Shared64 worker: random32 evaluation

Polling the existing detached call; no duplicate job launched.

## 2026-11-03T18:17:07.127027+00:00 | completed | Ranked64 monitoring outputs recovered

All64 ranked-adapter development generations are saved:52 numeric matches and1 truncated output, versus58 matches and2 truncations for untouched Granite on the identical questions. Random-adapter evaluation is still running. This is development monitoring, not the final test; no complete three-checkpoint comparison is claimed.

## 2026-11-03T18:18:32.505601+00:00 | decision | Expand from pilot to a controlled specialization study

The user authorized maximizing the existing 30-dollar Modal ceiling for useful results. The project continues through token-matched student-aware and random controls, repeated seeds as feasible, a frozen final comparison and a capped API trial. Math remains the first task; a trained adapter or more data alone is not evidence that valuation helped. Existing jobs and reservations remain in force.

## 2026-11-03T18:20:06.308783+00:00 | decision | Ground the next training recipe in DeepSeek technical reports

Reviewed primary DeepSeekMath, R1, V3 and V4 reports. Distinguish example validity, predicted student usefulness and downstream value measured under matched training tokens. Use verified sequence-level distillation with random controls; the current API workflow does not reproduce V4 full-vocabulary on-policy distillation. Reports motivate the experiment but do not guarantee Granite gains.

## 2026-11-03T18:20:50.191320+00:00 | decision | Freeze a larger controlled training budget and bounded runtime

Before new valuation results, plan 32768 supervised tokens per arm in 32 updates, with shared learning rate 0.00002. New valuation workers may run up to1800 seconds under a3-dollar reservation at checked resource prices; existing900-second jobs are unchanged. Equal token-weighted updates and batched evaluation replace the earlier unequal-token serial pilot. Four arms across two seeds fit a12-dollar envelope, subject to the durable ledger.

## 2026-11-03T18:20:58.441457+00:00 | completed | Shared64 phase completed: eval

All evaluation outputs saved for the frozen64 monitoring questions. Counts: baseline 58/64, ranked32 52/64, random32 52/64. This is development monitoring, not final-test accuracy.

## 2026-11-03T18:21:37.209620+00:00 | in_progress | Full120 Granite training launched

The shared64 benchmark is complete: untouched Granite58/64, BM25-ranked32 adapter52/64, random32 adapter52/64. A fresh pinned Granite adapter is now training on all120 verified examples under the existing3-dollar Modal reservation, with evaluation on the identical64 monitoring questions. Improvement is measured, not assumed.

## 2026-11-03T18:22:04.741044+00:00 | in_progress | Research improvement cycle

Poll improvement_control.py poll --run train; do not duplicate the active job.

## 2026-11-03T18:22:22.828557+00:00 | decision | Measured dataset fit rejects the initial OpenR1 pool

A bounded seeded scan of256 OpenR1 training records found zero full verified numeric word-problem traces within the768-response-token and2048-context limits. The shortest of154 inspected verified scalar traces had1217 tokens. Cached artifacts and rejection counts are retained; a server rate limit stopped further scanning. This does not rule out suitable examples elsewhere. Switch the next pool to concise DeepSeek solutions for separate GSM8K training questions; no silent trace truncation.

## 2026-11-03T18:23:32.538866+00:00 | in_progress | Shared64 worker: full120 evaluation

Polling the existing detached call; no duplicate job launched.

## 2026-11-03T18:25:43.068029+00:00 | in_progress | New task-aligned teacher pool is generating

A detached four-worker collector is answering512 new GSM8K training questions with concise DeepSeekV4-Pro non-thinking responses. The frozen pool excludes352 previously used or probe IDs; gold answers are checked locally, not sent to the teacher. Complete raw outputs and every rejection are retained. A4-dollar DeepSeek reservation bounds the collector; current supervised-token capacity will determine whether the planned32768-token arms can run.

## 2026-11-03T18:27:53.824901+00:00 | completed | Controlled selection and capped API source pass local checks

Implemented immutable verified-pool preparation, student-aware skill/diversity selection, exact supervised-token masking, token-weighted optimizer updates and batched checkpoint evaluation. Local cloud checks pass. API source includes20 permanent atomic admission permits and24-hour expiry, with no deployed endpoint. These are implemented components; improved accuracy, final-checkpoint selection and public serving remain uncompleted.

## 2026-11-03T18:28:34.556178+00:00 | planned | Exact-token random arm prepared

Prepared32768 supervised answer tokens,32 optimizer updates, learning rate0.00002, and batched64-question development evaluation. Each arm starts from the pinned base. Preparation launched no GPU job.

## 2026-11-03T18:28:34.720003+00:00 | planned | Exact-token valued arm prepared

Prepared32768 supervised answer tokens,32 optimizer updates, learning rate0.00002, and batched64-question development evaluation. Each arm starts from the pinned base. Preparation launched no GPU job.

## 2026-11-03T18:29:16.173649+00:00 | planned | Exact-token random arm prepared

Prepared32768 supervised answer tokens,32 optimizer updates, learning rate0.00002, and batched64-question development evaluation. Each arm starts from the pinned base. Preparation launched no GPU job.

## 2026-11-03T18:29:16.320782+00:00 | planned | Exact-token valued arm prepared

Prepared32768 supervised answer tokens,32 optimizer updates, learning rate0.00002, and batched64-question development evaluation. Each arm starts from the pinned base. Preparation launched no GPU job.

## 2026-11-03T18:29:16.350785+00:00 | planned | Two-seed exact-token valuation protocol prepared

Finalized the shared verified512-attempt teacher pool, excluded monitoring/probe overlaps, and prepared valued/random arms for seeds42 and43. Each arm has32768 supervised answer tokens and32 token-weighted optimizer updates, learning rate0.00002, and the same64 development questions. Weakness signals are explicitly development-derived; no official test was accessed. Preparation launched no GPU jobs.

## 2026-11-03T18:30:44.884770+00:00 | completed | Shared64 phase completed: train

All evaluation outputs saved for the frozen64 monitoring questions. Counts: full120 52/64. This is development monitoring, not final-test accuracy.

## 2026-11-03T18:31:50.205902+00:00 | in_progress | First matched-token random arm launched

The seed42 random-control worker is running under a3-dollar reservation and hard4CPU/32GiB caps. It will collect untouched-student responseNLL diagnostics for477 verified candidates, then train exactly32768 answer tokens through32 token-weighted optimizer updates at learning rate0.00002, and evaluate the frozen64 development questions in batches. No second valuation arm has launched.

## 2026-11-03T18:32:48.498062+00:00 | decision | Continue beyond the first control block toward effective full-budget use

The user requests a40-source Hugging Face import effort and useful utilization of the existing20-dollar DeepSeek and30-dollar Modal credits. A separate bounded import registry is starting; metadata, raw imports and verified training-ready examples will be counted separately. Frozen arms stay unchanged. Authenticated Modal usage is about2.32dollars; earlier12-dollar local allowances were not actual spending. Further useful larger data-efficiency rounds will be planned from measured results while preserving final evaluation and serving funds.

## 2026-11-03T18:33:34.320196+00:00 | in_progress | Research improvement cycle

Compare all checkpoints on the shared64 questions, then advance the token-matched student-aware versus random study in progress/RESEARCH_EXECUTION_PLAN.md. Continue regardless of whether more-data training improved; preserve funds for final evaluation and a capped API trial.

## 2026-11-03T18:36:05.365130+00:00 | resolved | Provider-backed Modal budget tracking enabled

The authenticated supported billing summary reported2.48 dollars of metered workspace usage and0 dollars invoiced after credits at its latest observation. Historical3-dollar job reservations are not charges. The ledger now separates provider-observed usage, an explicit3-dollar collection-lag buffer, active job reservations, and temporary liabilities for recently finished jobs. DeepSeek remains a recorded peak-price estimate. No extra compute was launched by billing reconciliation.

## 2026-11-03T18:36:18.785905+00:00 | in_progress | Research improvement cycle

Poll the existing exact-token arm with valuation_control.py poll --folder student_valuation32768_seed42_random_v1. Preserve its outputs; do not duplicate the call.

## 2026-11-03T18:37:15.557331+00:00 | completed | Equal-token random arm completed

Completed 32768 supervised tokens and 32 optimizer updates. Batched development results are saved; compare only the frozen matched arms and disclose adaptive development use.

## 2026-11-03T18:38:05.601584+00:00 | in_progress | Research improvement cycle

Poll the existing exact-token arm with valuation_control.py poll --folder student_valuation32768_seed42_valued_v1. Preserve its outputs; do not duplicate the call.

## 2026-11-03T18:38:25.880968+00:00 | in_progress | Matching valuedseed42 arm launched

The randomseed42 equal-token arm completed55/64 numerical matches with no truncation. Its frozen matching valued arm is now running with the same32768 supervised tokens,32 optimizer updates, learning rate0.00002, base checkpoint, seed and64-question batched evaluation. CandidateNLL diagnostics are saved but did not change this preselected skill-based arm. No seed43 job has launched yet.

## 2026-11-03T18:44:46.660473+00:00 | completed | Forty Hugging Face sources sampled with verified provenance

Completed bounded training-split imports from40 actual repositories across37 declared source families:312 complete raw rows with verified file hashes. These are samples, not entire datasets or40 trained domains.47 scalar-reference prompts were parsed generically; source-specific quality and teacher verification are still required. Original format/API failures and the first registry were preserved. Next expansion prioritizes compatible arithmetic sources instead of mixing unverified code/science into the math scorer.

## 2026-11-03T18:46:56.660002+00:00 | completed | Equal-token valued arm completed

Completed 32768 supervised tokens and 32 optimizer updates. Batched development results are saved; compare only the frozen matched arms and disclose adaptive development use.

## 2026-11-03T18:48:29.041709+00:00 | completed | First exact-token selection comparison analyzed

Seed 42: random scored 55/64 and valued scored 53/64 on the same adaptive development questions. Valued corrected 4 and regressed 6 answers; the paired 95% interval spans -12.5 to +6.25 percentage points. This provides no evidence of a selection advantage. Both arms supervised exactly 32768 tokens through 32 updates; aggregate reports and immutable source hashes are saved.

## 2026-11-03T18:48:29.041709+00:00 | in_progress | Frozen valued seed 43 replication launched

Launched the unchanged valued-arm replication only after all earlier GPU apps stopped and fresh provider accounting confirmed headroom. The arm retains the same verified pool, 32768 supervised tokens, 32 updates and learning rate 0.00002. One A100 task, hard 4 CPU/32 GiB limits, 1800-second maximum and a separate 3-dollar reservation. Random seed 43 remains prepared.

## 2026-11-03T18:49:33.699697+00:00 | in_progress | Research improvement cycle

Poll the existing exact-token arm with valuation_control.py poll --folder student_valuation32768_seed43_valued_v1. Preserve its outputs; do not duplicate the call.

## 2026-11-03T18:52:30.147762+00:00 | planned | Prepare gradient-based valuation and a larger arithmetic cohort

Source-specific preparation is running for up to1800 new arithmetic prompts from SVAMP, TemplateGSM and OpenMath augmentation, with prior-pool exclusions and reference origins retained. This is not yet teacher-verified training data. A separate LESS-inspired projected-gradient design and reference scoring math are prepared; the bounded GPU feature collector remains to implement. Current frozen replication continues unchanged.

## 2026-11-03T18:52:48.707303+00:00 | completed | Equal-token valued arm completed

Completed 32768 supervised tokens and 32 optimizer updates. Batched development results are saved; compare only the frozen matched arms and disclose adaptive development use.

## 2026-11-03T18:53:32.037365+00:00 | completed | DeepSeek funding-based accounting separated from token estimates

A supported balance observation and the user-declared original funding conditionally imply 0.36 dollars of project-attributed wallet consumption. The 0.75-dollar recorded peak-price token estimate remains separate; an explicit 0.10-dollar lag buffer is retained. No new credits are assumed and the 20-dollar ceiling is unchanged. Funding changes, grants and stale observations block new reservations. Wallet and account details remain private.

## 2026-11-03T18:54:12.105665+00:00 | in_progress | Final frozen random seed 43 arm launched

After valued seed 43 completed and all prior GPU apps stopped, launched the unchanged random seed 43 arm to complete the preregistered first two-seed block. Exactly 32768 supervised tokens, 32 updates, the same teacher pool and learning rate 0.00002; one bounded A100 job with a separate 3-dollar reservation. Seed variation remains unavailable until this final arm completes.

## 2026-11-03T18:55:26.246019+00:00 | in_progress | Research improvement cycle

Poll the existing exact-token arm with valuation_control.py poll --folder student_valuation32768_seed43_random_v1. Preserve its outputs; do not duplicate the call.
