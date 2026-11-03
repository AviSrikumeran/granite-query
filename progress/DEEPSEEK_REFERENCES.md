# What DeepSeek's reports support for Granite Query

Reviewed November3,2026. These are authors' reported experiments and methods, not independent guarantees or a complete disclosed training corpus. R1/V3 are historical references; the current API teacher in this project is V4-Pro.

## Findings from primary sources

**DeepSeekMath,2024, sections2.1–2.2.** The authors iteratively retrieve and filter math content using a classifier seeded with mathematical web text. They test alternative corpora by training the same1.3B model for150B tokens. Table1 reports GSM8K2.9% without math training,11.5% with OpenWebMath,14.3% with Proof-Pile2 and23.8% with their corpus. Corpus sizes/repetition differ; this is not an isolated per-example valuation result. Its useful precedent is judging a data recipe by downstream learning under controlled training. [Paper](https://arxiv.org/pdf/2402.03300), [official repository and collection pipeline](https://github.com/deepseek-ai/DeepSeek-Math).

**DeepSeek-R1,2025, sections2.3.3–2.4,3 and4.2.** The report describes retaining correct generated reasoning examples, readability filtering, and supervised distillation into smaller Qwen/Llama models without an RL stage for those distilled models. It reports about600k reasoning plus200k other examples. Evaluation uses substantial generation budgets and repeated samples; its published scores cannot be transferred to our512-token greedy Granite setting. It also describes difficulties with process-reward models and reward hacking. [Versioned technical report](https://arxiv.org/html/2501.12948v1), [released models and usage recommendations](https://github.com/deepseek-ai/DeepSeek-R1).

**DeepSeek-V3,2024, sections5.1 and5.4.1.** The authors describe teaching verification/reflection patterns while controlling response style and length, then rejection-sampling concise teaching responses. This motivates checking useful reasoning within our output budget, rather than training Granite to imitate arbitrary verbosity. [Versioned report](https://arxiv.org/html/2412.19437v1).

**DeepSeek-V4,2026, section5.1.** The report describes domain specialists, rule-based verification for readily checkable tasks, and consolidation through on-policy distillation using full-vocabulary teacher logits. Its open weights/model card do not imply that the API exposes those distributions. Our completion-based supervised distillation is a different method. [Versioned report](https://arxiv.org/html/2606.19348v1), [official V4 model card](https://fe-static.deepseek.com/chat/transparency/deepseek-V4-model-card-EN.pdf).

These documents do not establish the earlier conversational claim that DeepSeek is simply OpenAI/Anthropic distilled more cheaply. They describe their own training pipelines. We do not need that unverified provenance claim for this study.

## Our inference and implementation decisions

Separate three concepts:

1. **Validity:** Is the example complete, on-task, uniquely identified and checkable against a reference? Did it fit the student context? A correct final answer is necessary for our eligibility rule but does not prove each intermediate step correct.
2. **Predicted usefulness:** Does the example address a weakness this student has, add skill coverage, or avoid redundancy? This is a selection heuristic. A difficult example may be noisy or beyond the student's current capacity; maximum difficulty is not automatically maximum usefulness.
3. **Measured value:** Does training on the selected subset improve performance on other questions more than random selection at the same supervised-token budget? Only the controlled training experiment supplies this evidence.

Implement verification before ranking. Use disjoint training probes or explicitly labeled adaptive development skill aggregates for student signals. Preserve diversity, common source proportions, teacher identity and full original traces. Match token budgets, shuffle consistently and independently initialize every arm. Track useful concise answers and truncation separately from numeric accuracy. Reserve final-test evaluation until checkpoint/protocol freeze.

A compact next hypothesis is: **Verified examples that address Granite's observed skill gaps, while preserving diversity, yield more held-out accuracy per supervised training token than random verified examples.** The reports motivate this experiment; they do not demonstrate it for Granite or guarantee a positive outcome.

We will use sequence-level supervised fine-tuning, not claim full-logit on-policy distillation or reproduce frontier-scale RL. A separate API demonstration will expose the actual chosen checkpoint and its benchmark evidence, whether the result is an improvement, tie or regression.
