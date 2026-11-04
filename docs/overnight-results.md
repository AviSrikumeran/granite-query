# Overnight Granite results — November 4, 2026

**No improved Granite checkpoint was established. Local training worked technically; learning did not transfer to the separate evaluation questions.**

| Model / recipe | Development (32) | Same-task retention (32) |
|---|---:|---:|
| Untouched Granite | 30 | 29 |
| Small correction adapter, 8 updates | 30 | 26 |
| Small random-control adapter, 8 updates | 30 | 28 |
| Larger correction adapter, 64 updates | 28 | 27 |
| Larger random-control adapter, 64 updates | 29 | 25 |

All rows use the same frozen questions and nonthinking greedy512-token inference. Historical baseline reuse is bound to physical result/input hashes. These are small, adaptive TRAIN-development samples, one training seed; retention is same-task rather than broad ability. Bootstrap intervals in the detailed reports measure question uncertainty, not training-seed uncertainty. Official GSM8K test remains unopened.

## What worked

- RTX3060 ran real BF16 Granite inference and LoRA training without Modal. Checkpoints were saved before evaluation and reloaded with all160 small-adapter or560 larger-adapter tensors verified.
- Granite made100 original training-probe attempts. DeepSeek reviewed32 actual attempts;27 corrections passed numeric/arithmetic qualification,5 were rejected, with no API failures or retries.
- Larger correction training changed performance on its8 taught mistakes from0/8 to8/8, preserving8/8 correct replay answers. This is seen-example fitting, not generalization.

## What failed and what the audit supports

The8-update adapter still answered0/8 taught mistakes correctly. Increasing capacity, updates and learning rate together produced near-exact target fitting (training NLL1.08005 to0.001008), but unused-teacher-target NLL worsened1.02025 to1.03372 and separate accuracy declined. This supports distinguishing insufficient initial fitting from failed transfer after stronger fitting. It does not isolate which hyperparameter caused the outcome.

Only8 distinct, heterogeneous mistake corrections plus8 replay examples were used per arm. Repeating a tiny set is not equivalent to adding diverse transferable examples. Frozen target arrays include complete final answers and EOS and fit the512-token training context, so no obvious target-truncation defect was found. Assistant review of the8 mistake targets found no arithmetic error, but three benchmark assumptions/interpretations deserve caution. This was not independent expert adjudication.

This recipe is correction-target supervised fine-tuning. It does not implement teacher/student token-distribution matching or iterative on-policy distillation. Low DeepSeek spending alone does not establish whether the algorithm is correct.

## A follow-up was stopped before spending

A predeclared narrow synthetic arithmetic cohort was probed on128 TRAIN questions only. Original Granite scored121/128. Its7 errors fell below the frozen16-error minimum, so no teacher collection or training followed;96 held-out questions remain untouched. We did not change difficulty to manufacture a favorable result.

## Costs and saved outputs

Overnight teacher generation:32 calls, summed peak-rate token estimate **$0.23698488**, not a provider invoice. The original$2 reservation was settled once. An older ambiguous API request still retains its full$7 hold. Last supported accounting snapshot: conservative estimated total$3.61 including buffer, plus$7 held; figures are dated observations rather than a fresh invoice. No overnight Modal calls. Local GPU uses electricity but no cloud GPU credits.

Four trained adapter checkpoints and their original raw outputs, partial optimizer states, hashes and reload receipts remain private. No checkpoint should be advertised as improved. No API was deployed.

## Next scientific step

Before additional spending, design a larger coherent curriculum with more distinct examples, a fixed training dose, reference-only and teacher-correction controls, and an independent evaluation frozen before any run. Separate fitting and transfer metrics. Do not claim data value until a learning recipe yields reproducible transfer and controlled ablations support attribution. No new paid stage is started by this recommendation.

Detailed machine-readable and paired reports: OVERNIGHT_FEEDBACK_RESULTS and OVERNIGHT_CAPACITY_RESULTS. Local control/logging failures and recoveries remain preserved; no paid request was retried.
