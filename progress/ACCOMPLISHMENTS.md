# What Granite Query has actually accomplished

Granite has been fine-tuned on Modal, but no accuracy improvement has been demonstrated yet. Only GSM8K has been processed for this training study.

## Dataset coverage

- **GSM8K — processed**. Ranking probes, teacher questions, LoRA training examples, and development evaluation. Downloaded from the canonical GitHub source; not a claim that all Hugging Face datasets were processed. Source: https://github.com/openai/grade-school-math/tree/3101c7d5072418e28b9008a6636bde82a006892c

- **Alpaca — not_used**. Mentioned in an older direction, then explicitly superseded by the GSM8K scope. Source: Earlier project discussion; no ingestion artifact for this study

- **open-r1/OpenR1-Math-220k — researched_not_imported**. Recommended next valuation pool: existing DeepSeek-R1 math traces with completion/correctness flags. Start with a small, pinned sample of short numeric-answer word problems; long and difficult traces may not fit Granite's context. Teacher differs from the current V4-Pro API and must be labelled. Source: https://huggingface.co/datasets/open-r1/OpenR1-Math-220k

- **nvidia/OpenMathInstruct-2 — researched_not_imported**. Supporting GSM8K-style prompt pool. Filter augmented_gsm8k and numeric expected answers; its supplied solutions come from Llama, so regenerate with DeepSeek if teacher consistency is required. Do not assume augmented answers are independently verified gold. Source: https://huggingface.co/datasets/nvidia/OpenMathInstruct-2

- **open-thoughts/OpenThoughts-114k — researched_not_imported**. Later skill-diversity source: use math-only records from its DeepSeek-R1 reasoning data. Mixed domains and long traces require filtering; not yet imported. Source: https://huggingface.co/datasets/open-thoughts/OpenThoughts-114k

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

## Current work and failures

- **Original 64-question Granite attempt — failed**. The original attempt reached its application deadline before completing all checkpoints. Completed phase outputs were preserved; this is not a completed comparison across all checkpoints.

- **Resume of unfinished 64-question evaluations — running**. A Modal function call was submitted; currently evaluating the saved BM25 adapter. It is a separate attempt and should reuse completed outputs instead of rerunning them.

- **Larger 120-example Granite training round — queued**. The input and plan are prepared. No Modal function call has been submitted. Its purpose is to measure whether more verified data helps; improvement is not guaranteed.

## Not completed

- Robust or final-test Granite accuracy improvement has not been established.
- Training/evaluation on additional math datasets; candidate sources are researched but not imported.
- Multiple training/selection seeds and matched supervised-token controls.
- An implemented and evaluated student-aware skill-ranking method.
- Independent explanation-quality/depth evaluation.
- Official GSM8K test evaluation of a final frozen checkpoint.
- Public Granite model-serving API and Vercel deployment.

Updated: 2026-11-03T18:14:19.773423+00:00
