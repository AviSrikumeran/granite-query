# From a pilot to a useful specialization study

The user authorized maximizing the existing $30 Modal and $20 DeepSeek credits on November 3, 2026. These are total ceilings, including previous usage. This project is active; the first tied pilot was a pipeline check, not the promised research result.

## The claim to test

The [DeepSeek reference review](DEEPSEEK_REFERENCES.md) distinguishes verification, predicted usefulness and measured downstream value. Its cited Math/R1/V3/V4 reports motivate the recipe, not a guarantee that it works for Granite.

Can a small Granite model learn grade school mathematical reasoning more effectively from student-aware selected teacher examples than from random examples under the same supervised-token budget?

Small size can make adaptation and deployment economical. It does not guarantee specialization gains, and a large model is not inherently average at every task. Improvement must be observed. More data, a new dataset, a falling training loss, or a custom API by itself is not evidence that valuation worked.

The first task remains concise numeric math word problems. Coding and broad conceptual tutoring require different benchmarks, verifiers and data; they are future extensions.

## Required outputs

- An untouched original Granite baseline and versioned LoRA checkpoints, with pinned model/dependency revisions and training manifests.
- A verified common teacher pool, with teacher/source provenance, rejection counts and deduplication reports.
- A reproducible student-aware selector compared with random selection. BM25 is a cheap historical reference, not a demonstrated valuation method.
- Accuracy, corrected/regressed questions, truncation, actual supervised tokens, selection overhead and training cost. Report explanation brevity separately; do not substitute stylistic resemblance for correct mathematics.
- Matched question-set visualizations and a final frozen-checkpoint evaluation, with paired uncertainty and limitations.
- A demand-driven model API and comparison interface that identify the actual checkpoint and its measured limits. Serving preparation can proceed during research. Public serving follows checkpoint selection and a separately reserved hard usage quota; no indefinitely billable warm GPU.

## Authorized sequence

1. Finish the existing64-question benchmark resume without repeating saved generations. Train the already-reserved full120 adapter only after the evaluation worker stops. Preserve the failed original attempt and any regressions.
2. Prepare a bounded pool of up to512 complete, verified, short math teaching examples. Inspect OpenR1-Math-220k first; public DeepSeek-R1 traces are a different teacher from the API's V4-Pro outputs and must be labeled. If too few traces fit, use disjoint GSM8K training questions with concise DeepSeek solutions instead of silently truncating long traces. Use one common source mixture for every new arm. Downloading entire corpora is unnecessary.
3. Freeze a simple student-aware rule before new evaluation: weakness on separate training probes or development skill aggregates, combined with diversity and complete-trace feasibility. Never rank against official test questions or answers. Mark development-derived tuning as adaptive. The selector is a hypothesis about usefulness, not a causal value estimate.
4. Compare random and valued selections from that common pool at a frozen supervised-token budget, targeting32,768 tokens per arm if eligible data permits:32 optimizer updates with1,024 supervised tokens per update. Use the same starting weights, LoRA configuration, learning rate, effective batch policy and shuffled ordering rule. The next controlled arms use LR0.00002, a conservative change from the historical0.0001 pilot that regressed; apply it identically across all new arms and do not attribute cross-recipe changes solely to data selection. Record any loss masking used to match budgets; keep full original traces. Run seeds42 and43 if remaining budget permits, starting independently from the base for each arm. Do not start a second seed before the first pair is sound. A smaller preregistered budget is acceptable if the measured pool/runtime cannot support32,768; record the change before observing new outcome scores.
5. Prefer batched evaluation and fewer durable writes over repeated serial evaluation/timeouts. Locally check isolation, selection, masking and resume behavior before paid execution. Save an adapter before evaluation so a timeout cannot erase the training result.
6. On the frozen64 monitoring questions, measure paired gains/regressions for every arm and each seed. Choose and freeze a final checkpoint and protocol from development results; do not tune further after official-test evaluation. Predeclare one seeded official-test subset of256 questions, evaluate original and chosen checkpoint under identical settings, and report exact counts, paired confidence intervals and truncation. A subset is not the full1319-question benchmark. DeepSeek's current64 matched benchmark remains the teacher reference unless a new same-question teacher evaluation is separately budgeted.
7. Prepare and, when prerequisites/credentials permit, deploy a scale-to-zero API with checkpoint identity, input/output limits, a fixed request quota and an expiry. Reserve that serving allowance before deployment. If no trained checkpoint beats the base, expose comparisons honestly and preserve the research artifacts; never label a weaker checkpoint improved.

## Spending and continuation

The durable ledger, not this planning table, authorizes each launch. At plan creation it conservatively accounted $9 Modal, with $6 reserved for the active resume and full120, and $0.47 DeepSeek. These are upper estimates, not invoices. Modal's published resource prices were checked on November3: A10080GB $0.000694/second, CPU $0.0000131/core/second, memory $0.00000222/GiB/second; storage is separate. Existing reservations remain conservative and must not be reduced speculatively to create spending room.

Plan the remaining approximately$15 Modal as up to$12 for four bounded valuation-arm jobs, up to$2 for a batched final comparison, and up to$1 for a capped API trial. This is an envelope, not a claim these jobs are prepared or launched. Reconcile terminal jobs first, reserve each job, bound resources and time, and fit new reservations under the actual remaining ceiling. If final evaluation needs more time, reduce optional repetitions before sacrificing evaluation or exceeding credit. DeepSeek work remains within its independent $20 ceiling. Never spend merely to reach exactly$30.

New valuation workers may use a1,800-second hard timeout with one A10080GB,4CPU and32GiB memory. The listed compute rate sums to$0.00081744/second, or about$1.48 over1,800seconds; a$3 reservation also covers startup/storage overhead conservatively. Apply an earlier application deadline, save checkpoints, and finish early when done. This explicitly changes future valuation limits from900seconds to1,800; it does not modify already launched900-second jobs or repeat the completed first smoke test. This adjustment was recorded before any new valuation outcome was observed.

Continue from the pilot into the controlled valuation study even if full120 improves: more-data improvement alone does not establish selection value. Stop only when this bounded sequence has its artifacts/report, the budget cannot support useful next work, or a genuine account/access blocker prevents progress. On failure, save and explain the evidence and the next useful step. Update the journal and public dashboard on meaningful changes. Do not call the whole project complete while evaluation, checkpoint selection, or API delivery is missing.

Sources: [Modal resource prices](https://modal.com/pricing), [OpenR1 dataset](https://huggingface.co/datasets/open-r1/OpenR1-Math-220k), [OpenR1 filtering study](https://huggingface.co/blog/open-r1/update-2).
