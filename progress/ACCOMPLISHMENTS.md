# What Granite Query has actually accomplished

Granite has been fine-tuned on Modal, but no accuracy improvement has been demonstrated yet. The initial training study used GSM8K; additional source imports and teacher-data stages are tracked separately.

## Dataset coverage

- **GSM8K — processed**. Ranking probes, teacher questions, LoRA training examples, and development evaluation. Downloaded from the canonical GitHub source; not a claim that all Hugging Face datasets were processed. Source: https://github.com/openai/grade-school-math/tree/3101c7d5072418e28b9008a6636bde82a006892c

- **Alpaca — not_used**. Mentioned in an older direction, then explicitly superseded by the GSM8K scope. Source: Earlier project discussion; no ingestion artifact for this study

- **open-r1/OpenR1-Math-220k — inspected_no_eligible_data**. Bounded seeded scan of256 training records found zero complete verified numeric word-problem traces meeting the768-response-token limit; cached artifacts retained. Not used for Granite training. This sample does not establish that the full dataset has no suitable records. Source: https://huggingface.co/datasets/open-r1/OpenR1-Math-220k

- **nvidia/OpenMathInstruct-2 — teacher_pool_completed**. 600 source training prompts imported; 523 teacher responses passed the verifier. Reference type: synthetic majority-vote references. New-cohort Granite training/evaluation remains separate from teacher-data collection. Source: https://huggingface.co/datasets/nvidia/OpenMathInstruct-2/tree/469216e3f46f4dacf476b382e192485ea51a143e

- **open-thoughts/OpenThoughts-114k — researched_not_imported**. Later skill-diversity source: use math-only records from its DeepSeek-R1 reasoning data. Mixed domains and long traces require filtering; not yet imported. Source: https://huggingface.co/datasets/open-thoughts/OpenThoughts-114k

- **ChilleD/SVAMP — teacher_pool_completed**. 600 source training prompts imported; 571 teacher responses passed the verifier. Reference type: human dataset answers. New-cohort Granite training/evaluation remains separate from teacher-data collection. Source: https://huggingface.co/datasets/ChilleD/SVAMP/tree/5e0bf1e5e7c0e9c4bc39180d224f41f3f801b7ef

- **math-ai/TemplateGSM — teacher_pool_completed**. 600 source training prompts imported; 471 teacher responses passed the verifier. Reference type: procedural references. New-cohort Granite training/evaluation remains separate from teacher-data collection. Source: https://huggingface.co/datasets/math-ai/TemplateGSM/tree/0c8ed6b60fea0a84f25ddb1b8b761db695df2e19

- **Broader Hugging Face source audit — bounded_samples_imported**. 40 repositories sampled, with 312 complete training rows across 37 declared families. These samples are not entire datasets or evidence of training across all domains. Source: https://github.com/AviSrikumeran/granite-query/blob/main/progress/HF_SOURCE_INVENTORY.json

- **New human-reference GSM training expansion — teacher_pool_completed**. 2,048 new GSM training questions and 200 separate training-split development questions are frozen. 6,053 questions passed exact arithmetic-annotation/final-link checks after 994 prior-question or detectable-ancestry exclusions. These checks do not prove semantic correctness; TemplateGSM ancestry uses a conservative proxy and OpenMath lineage is incomplete. No official test questions were used. Data preparation is separate from teacher generation and Granite training. Current teacher receipts: 2,048/2,048. These artifacts do not themselves evidence Granite training or accuracy improvement. Source: https://github.com/openai/grade-school-math/tree/3101c7d5072418e28b9008a6636bde82a006892c

## Model actually trained

ibm-granite/granite-4.2-3b at revision 4e9c275e232f10211ec88644d106a1f6a1b60e06.

LoRA adapters on a pinned 3B Granite checkpoint, on Modal A100 workers; not full-parameter training and not the earlier local 8B model.

## Completed work

### GSM8K training data prepared

7,473 official training records were prepared. 128 questions were reserved as ranking probes; the remainder supplied candidate questions. This is one dataset, not a survey of all Hugging Face repositories.

[Evidence](https://github.com/AviSrikumeran/granite-query/blob/main/progress/COMPARISON_PLAN.md)

### Prompt ranking and duplicate pruning completed

7,344 candidate question prompts were scored by BM25 against 128 training probes after duplicate pruning. This is relevance ranking, not evidence of causal training value, and it does not mean every question was sent to DeepSeek or used for training.

[Evidence](https://github.com/AviSrikumeran/granite-query/blob/main/progress/COMPARISON_PLAN.md)

### Granite was actually fine-tuned on Modal

The A100 smoke test completed 12 LoRA updates on 12 teacher examples, saved the adapter, and reloaded it. This changed adapter parameters; it was not full-parameter training or evidence of generalization improvement. Modal evidence requires account access.

[Evidence](https://modal.com/apps/avisrikumeran/main/ap-WS6yWYh6OmC0C0Lne7UiMb)

### DeepSeek teacher examples generated and verified

128 candidate responses were collected through the DeepSeek API; 120 passed the strict final-answer verifier. Rejected outputs were preserved and excluded from both training arms.

[Evidence](https://github.com/AviSrikumeran/granite-query/blob/main/progress/RESULTS.md)

### Ranked and random LoRA adapters trained on Modal

Separate adapters each received 32 examples and 32 updates. Ranked used 3,260 supervised tokens; random used 2,534. The budgets matched examples and updates, not tokens. Modal evidence requires account access.

[Evidence](https://modal.com/apps/avisrikumeran/main/ap-yOuxoTkxDoBeMso5YZ5xBd)

### First accuracy comparison completed: a tie

Original Granite: 13/16. BM25-trained Granite: 13/16. Random-trained Granite: 13/16. This single-seed development pilot demonstrated no accuracy gain; the official test set was not used.

[Evidence](https://github.com/AviSrikumeran/granite-query/blob/main/progress/RESULTS.md)

### DeepSeek measured on the identical 16 questions

DeepSeek Pro scored 15/16. The Granite variants scored 13/16 on these same questions. DeepSeek used thinking and a 4096-token cap; Granite used non-thinking and a 512-token cap. API and GPU timing scopes differ.

[Evidence](https://github.com/AviSrikumeran/granite-query/blob/main/progress/RESULTS.md)

### DeepSeek side of the new 64-question benchmark completed

DeepSeek scored 63/64, including 1 truncated response counted as a failure. Do not compare this 64-question score with Granite's earlier 16-question score.

[Evidence](https://github.com/AviSrikumeran/granite-query/blob/main/progress/IMPROVEMENT_PLAN.md)

### Original Granite baseline completed on the same 64 questions

Original Granite scored 58/64, with 2 truncated outputs counted as failures. DeepSeek scored 63/64 on those identical questions. This is a baseline comparison, not evidence that training improved Granite.

[Evidence](https://modal.com/apps/avisrikumeran/main/ap-KMIiovWHG4Bt4CyMzjrU5b)

### 64-question Granite benchmark fully recovered

All three Granite checkpoint evaluations on the same 64 monitoring questions are saved. This is development monitoring, not the official final test.

[Evidence](https://github.com/AviSrikumeran/granite-query/blob/main/progress/IMPROVEMENT_PLAN.md)

### Untouched Granite batch8 control completed

Evaluation-only plan: untouched pinned Granite, no adapter, the same 64 questions, non-thinking 512-token generation and batch8 evaluation. Completed 58/64 numeric answers, with zero actual training tokens and updates. This matched-batch control is separate from the earlier serial58/64 result.

[Evidence](https://modal.com/apps/avisrikumeran/main/ap-8sDpW3oOzIOpKk8VAOWrhj)

### New multi-source DeepSeek teaching pool completed

1,800/1,800 DeepSeek responses saved; 1,565 passed complete-response/reference-match checks, supplying 150,750 supervised answer tokens. Sources are SVAMP, TemplateGSM and OpenMath arithmetic augmentation. Human dataset answers, procedural results and synthetic majority-vote references remain distinct; reference match does not independently prove every reasoning step correct. This is teacher-data preparation, not completed Granite training on the new cohort.

[Evidence](https://github.com/AviSrikumeran/granite-query/blob/main/progress/MATH_TEACHER.json)

### New human-reference teaching and development split frozen

2,048 new GSM training questions and 200 separate training-split development questions are frozen. 6,053 questions passed exact arithmetic-annotation/final-link checks after 994 prior-question or detectable-ancestry exclusions. These checks do not prove semantic correctness; TemplateGSM ancestry uses a conservative proxy and OpenMath lineage is incomplete. No official test questions were used. Data preparation is separate from teacher generation and Granite training.

[Evidence](https://github.com/AviSrikumeran/granite-query/blob/main/progress/HUMAN_MATH_COHORT.json)

### First equal-token random versus skill experiment completed

seed 42: random 55/64, skill and diversity 53/64; seed 43: random 57/64, skill and diversity 56/64. Every arm completed 32,768 supervised tokens and 32 matched optimizer updates on the same 64 monitoring questions. The skill heuristic did not beat random in either seed. Targeted gradient selection and the new source cohort are separate experiments.

[Evidence](https://github.com/AviSrikumeran/granite-query/blob/main/progress/RESEARCH_EXECUTION_PLAN.md)

### Student-gradient feature collection completed

Separate continuation of the same frozen feature protocol. 3,130 projected features are saved for 1,541 candidates and 24 held-out selection targets. CountSketch gradient alignment is an approximate selection signal, not a measured Granite accuracy gain.

[Evidence](https://github.com/AviSrikumeran/granite-query/blob/main/progress/NEXT_VALUATION_METHOD.md)

### Human-reference DeepSeek teaching pool completed

2,048/2,048 human-reference teaching responses saved; 1,930 passed complete-response/reference-match/token checks, supplying 223,827 answer tokens. Each invocation is limited to one separately funded 512-request chunk. The separate 200-question development holdout is withheld from teacher requests and training selection; it is not the official test. Arithmetic annotations were checked exactly, while semantic sufficiency and complete ancestry decontamination remain unproven. Teacher collection is not evidence that Granite used these questions or improved.

[Evidence](https://github.com/AviSrikumeran/granite-query/blob/main/progress/HUMAN_MATH_TEACHER.json)

## Current work and failures

- **Original 64-question Granite attempt — failed**. The original attempt reached its application deadline before completing all checkpoints. Completed phase outputs were preserved; this is not a completed comparison across all checkpoints.

- **Resume of unfinished 64-question evaluations — completed**. All required outputs on the 64 monitoring questions are saved. It is a separate attempt and should reuse completed outputs instead of rerunning them.

- **Larger 120-example Granite training round — completed**. All required outputs on the 64 monitoring questions are saved. Its purpose is to measure whether more verified data helps; improvement is not guaranteed.

- **Untouched Granite control with matched batch8 evaluation — completed**. Evaluation-only plan: untouched pinned Granite, no adapter, the same 64 questions, non-thinking 512-token generation and batch8 evaluation. Completed 58/64 numeric answers, with zero actual training tokens and updates. This matched-batch control is separate from the earlier serial58/64 result.

- **New verified teacher pool for token-matched controls — completed**. 512/512 separate training questions answered; 477 passed eligibility checks, with 55,738 available answer tokens. Uses DeepSeek V4-Pro non-thinking concise responses; original raw answers remain private. Collection is not a completed training experiment.

- **Verify the new multi-source arithmetic teaching pool — completed**. 1,800/1,800 DeepSeek responses saved; 1,565 passed complete-response/reference-match checks, supplying 150,750 supervised answer tokens. Sources are SVAMP, TemplateGSM and OpenMath arithmetic augmentation. Human dataset answers, procedural results and synthetic majority-vote references remain distinct; reference match does not independently prove every reasoning step correct. This is teacher-data preparation, not completed Granite training on the new cohort.

- **Future human-reference arithmetic cohort preparation — completed**. 2,048 new GSM training questions and 200 separate training-split development questions are frozen. 6,053 questions passed exact arithmetic-annotation/final-link checks after 994 prior-question or detectable-ancestry exclusions. These checks do not prove semantic correctness; TemplateGSM ancestry uses a conservative proxy and OpenMath lineage is incomplete. No official test questions were used. Data preparation is separate from teacher generation and Granite training.

- **Equal-token random training, seed 42 — completed**. Measured 55/64 numeric answers, with 0 truncated outputs counted as failures. Completed 32,768 supervised tokens and 32 token-weighted updates. This is adaptive development monitoring, not a final-test result.

- **Equal-token skill and diversity training, seed 42 — completed**. Measured 53/64 numeric answers, with 1 truncated outputs counted as failures. Completed 32,768 supervised tokens and 32 token-weighted updates. This is adaptive development monitoring, not a final-test result.

- **Equal-token random training, seed 43 — completed**. Measured 57/64 numeric answers, with 0 truncated outputs counted as failures. Completed 32,768 supervised tokens and 32 token-weighted updates. This is adaptive development monitoring, not a final-test result.

- **Equal-token skill and diversity training, seed 43 — completed**. Measured 56/64 numeric answers, with 0 truncated outputs counted as failures. Completed 32,768 supervised tokens and 32 token-weighted updates. This is adaptive development monitoring, not a final-test result.

- **First student-aware equal-token experiment — completed**. seed 42: random 55/64, skill and diversity 53/64; seed 43: random 57/64, skill and diversity 56/64. Every arm completed 32,768 supervised tokens and 32 matched optimizer updates on the same 64 monitoring questions. The skill heuristic did not beat random in either seed. Targeted gradient selection and the new source cohort are separate experiments.

- **Model-gradient data selection on the new math cohort — completed**. Separate continuation of the same frozen feature protocol. 3,130 projected features are saved for 1,541 candidates and 24 held-out selection targets. CountSketch gradient alignment is an approximate selection signal, not a measured Granite accuracy gain.

- **New math-cohort data-efficiency training grid — running**. 18/18 arm plans prepared; 2 completed, 1 running, 15 queued, 0 failed and 0 requiring launch reconciliation. Random, skill and gradient arms use a separately frozen common pool and matched token budgets; these are separate from the earlier four-arm results. Poll the existing call for gradient, seed 42, 32,768 supervised tokens. No automatic new paid launch is performed by this report.

- **Human-reference DeepSeek teaching chunks — completed**. 2,048/2,048 human-reference teaching responses saved; 1,930 passed complete-response/reference-match/token checks, supplying 223,827 answer tokens. Each invocation is limited to one separately funded 512-request chunk. The separate 200-question development holdout is withheld from teacher requests and training selection; it is not the official test. Arithmetic annotations were checked exactly, while semantic sufficiency and complete ancestry decontamination remain unproven. Teacher collection is not evidence that Granite used these questions or improved.

- **Capped Granite API trial — queued**. API source and quota controls are prepared and locally checked. No public model endpoint is deployed. It requires a chosen evaluated checkpoint, completed research GPU work, a serving reservation and an expiring request quota.

## Not completed

- Robust or final-test Granite accuracy improvement has not been established.
- Completed Granite training/evaluation on the new multi-source math cohort; source imports and teacher collection are separate stages.
- Robust or final-test evidence that the new selection method outperforms random.
- Independent explanation-quality/depth evaluation.
- Official GSM8K test evaluation of a final frozen checkpoint.
- Public Granite model-serving API and Vercel deployment.

Updated: 2026-11-03T20:34:41.128333+00:00
