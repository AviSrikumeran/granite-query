# Granite 4.2 3B: targeted versus random verified data

**High priority. Planning only. November 3, 2026, America/Chicago. No new inference or training is scheduled by this plan.**

## Decision and research goal

Keep `ibm-granite/granite-4.2-3b`, revision `4e9c275e232f10211ec88644d106a1f6a1b60e06`, as the fixed student. It is an already post-trained, general-purpose reasoning model with math and code training. Its open Apache 2.0 checkpoint, manageable size and continuity with the existing baseline make it a practical controlled research subject. We have not established that it is the best model overall or that a Granite Code checkpoint would score higher on our math workload. A coding checkpoint is another language model with a different training emphasis; there is no separate coding department to remove. [IBM model card](https://huggingface.co/ibm-granite/granite-4.2-3b), [Granite Code documentation](https://github.com/ibm-granite/granite-code-models).

The API teacher/reference remains `deepseek-v4-pro`, a much larger general-purpose model. Its answers require verification, as the paired error review demonstrated. Its score is a teacher comparison, not a parameter-matched architecture test. [DeepSeek model documentation](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro).

**Long-term goal:** improve a small general-purpose model's reasoning reliability per unit of training and inference cost through verified, student-targeted data, while preserving its other capabilities.

Math is the initial testbed because intermediate quantities and numerical answers can often be checked. The scalable contribution is the validation-and-selection method. Later transfer studies should test another workload, such as quantity tracking in grounded documents, and another student. Math gains alone do not establish broad assistant improvement. Sparse upcycling remains a conditional later experiment.

## What has already been learned

The 32-question mode study retained 448 outcomes. Granite low effort matched 27/32 references with 6,858 generated tokens at either tested cap. All three clear low-effort process failures were solved by both DeepSeek nonthinking and Granite nonthinking in the preserved samples. The leading hypotheses concern unit preservation, complete quantity ledgers and consistent entity dependencies. Mode and decoding differ, so these observations do not prove a deterministic mode effect.

There are 15 checked candidate seed examples: nine existing TRAIN questions and six authored contrasts. They contain 905 raw target tokens before native serialization and EOS. They are a review specification, not an adequate frozen training pool or evidence that training helps. Two reference-sensitive development questions stay excluded from corrective supervision. [Mode study](https://avisrikumeran.github.io/granite-query/inference-efficiency.html), [paired errors and seed examples](https://avisrikumeran.github.io/granite-query/low-effort-error-review.html).

## Before retraining: complete these gates

1. **Test the inexpensive prompt control first.** On the existing 32 diagnostic questions, compare the current concise prompt with a short instruction to define entity sets, list signed changes and compute from the complete ledger. Use low-effort mode, a 2048-total-token cap and decoding seeds 17, 29 and 43: 192 proposed generations in total. Compare correctness and all generated tokens. These familiar questions support prompt selection only. Freeze the chosen prompt before the new transfer set is selected. A useful prompt result can justify reassessing whether training adds enough value.
2. **Build one common verified training pool.** Start from permitted TRAIN sources and the 15 seed examples. Expand to at least 32,768 complete serialized assistant-loss tokens so each arm can select 16,384. Check every accepted target's arithmetic, final answer, quantity coverage, signs, unit conversions, entity membership, dependent counts and prose-equation agreement. Resolve timing and averaging conventions explicitly. Apply identical rules and the same concise worked-solution style to both arms. Human references and existing training-only teacher answers still require semantic review. Development teacher answers remain evidence only.
3. **Freeze an independent transfer-development set.** Target 100 reviewed TRAIN questions previously unused in this project after prompt selection and before ranking the training examples. Exclude training IDs, exact and near prompts, detected template relatives and authored seed-pair variants. Keep all existing 200 development questions out of training. If 100 eligible questions cannot be found, publish a revised count and protocol before launch. Do not select training examples using the new set's outcomes. Project-disjoint questions are not guaranteed to be absent from IBM's pretraining corpus.
4. **Freeze a small retention screen.** Prepare 30 disjoint cases: ten tool-selection/argument-schema cases, ten grounded-document answers and ten instruction/output-format cases. The proposed pilot gate is no new critical tool or unsupported-grounding failures and no lower observed correct count than the untouched base in any category. This screen does not certify enterprise quality.
5. **Prove the training contract and cost bound.** Validate native low-effort boundaries, complete targets, loss masks and one EOS. Demonstrate save/reload and complete causal inputs with the proposed packing. Freeze data IDs, target hashes, source code, inference settings and the exact runnable configuration. Quote bounded selection, training, model-load and evaluation costs against available shared credits. This document creates no new allocation or reservation.

## The controlled pilot

| Component | Untouched base | Targeted verified data | Random verified data |
| --- | --- | --- | --- |
| Starting checkpoint | Pinned Granite 4.2 3B | Fresh copy of the same checkpoint | Fresh copy of the same checkpoint |
| Eligible pool and solution style | Evaluation reference | Same verified pool and concise target rule | Same verified pool and concise target rule |
| Selection | No updates | Prioritize the three observed skill families | Seeded random question priorities across that pool |
| Loss budget | Zero | 16,384 serialized assistant-loss tokens | 16,384 serialized assistant-loss tokens |
| Updates and training seed | Zero | 16 updates, seed 42 | 16 updates, seed 42 |
| Evaluation | Same frozen questions | Same frozen questions | Same frozen questions |

**Targeted selection:** assign reviewed primary skill labels for units/aggregation, complete ledgers and entity dependencies. Aim for one third of selected loss tokens per family, within five percentage points. Break ties with seeded question-ID priorities. Freeze the actual mix and selected IDs before training. These categories are hypotheses from three errors, not an empirically optimal curriculum.

**Random selection:** use a seeded random question-priority order over the same eligible pool. Apply the same whole-target budget-fitting algorithm without skill priorities. The arms may overlap; report overlap, question counts, family mix and prompt/target length distributions. Do not selectively improve the targeted arm's labels or target style.

**Shared proposal defaults:** LoRA on `q_proj` and `v_proj`, rank 8, alpha 16, dropout 0, AdamW, learning rate `2e-5`, weight decay `0.01`, BF16 base weights, FP32 adapters and context limit 4096. Each arm receives 16 updates of 1024 assistant-loss tokens. Complete and hash all remaining runnable settings before dispatch. Start both arms from fresh base weights; do not continue one arm from another adapter.

Choose complete targets without repeating questions and prove the exact loss-token budget after native serialization. Preserve complete causal inputs and valid boundaries when constructing loss windows. If the exact shared budget or family allocation cannot be constructed, finish curation or revise the proposal before launch. Raw text-token totals are insufficient. Equal loss tokens do not imply equal forwarded compute, so measure both.

## Evaluation and decision

Evaluate all three checkpoints on the same frozen 100 transfer-development questions. The primary setting is native low effort, cap 2048 for reasoning plus final output, temperature 1.0, top-p 0.95 and common per-question decoding seeds derived from seed 17. Use the same warm device, engine, precision and batch settings. [Granite inference settings](https://huggingface.co/ibm-granite/granite-4.2-3b#generation-parameters).

Report reference-match accuracy after reference QA, paired corrections/regressions, paired question-bootstrap 95% intervals, all generated tokens, tokens per correct answer, truncations, failures and runtime. Also report data verification/selection overhead, forwarded training tokens, GPU time and dollars. Keep the existing 200-question cohort diagnostic. Include secondary low-effort-512 and nonthinking-2048 checks only when covered by the bounded evaluation plan, and label them separately.

Keep two claims separate: **training helps versus untouched base**, and **targeted selection helps versus random verified data**. A practical pilot screen is at least three percentage points of accuracy improvement at comparable measured inference cost, or at least 20% fewer generated tokens per correct answer with at most one percentage point accuracy loss, compared with both reference conditions, while passing retention checks. These are proposed engineering screens, not statistical proof.

Publish every pilot outcome. Question-bootstrap intervals do not cover training-seed uncertainty. A separately budgeted repeat of the full paired comparison with training seed 43 is required before claiming a robust selection advantage. If no advantage appears, retain the best-supported base/prompt configuration and document the null or negative result. Keep the existing official-test protocol sealed until the final candidate and inference rules are frozen.

The current step is preparing this comparison. No training manifests, jobs or official-test data are changed. [Download the machine-readable proposal](https://avisrikumeran.github.io/granite-query/targeted-random-verified-plan.json).
