# Testing data value, rather than assuming it

Only GSM8K has been used in the training experiments so far. The user confirmed the two initial references were GSM8K and Alpaca. Alpaca was superseded in the earlier plan. The additional sources below have been researched, not downloaded in full or used to train Granite.

## Relevant additional pools

- [OpenR1-Math-220k](https://huggingface.co/datasets/open-r1/OpenR1-Math-220k): strongest first pool for studying selection of existing DeepSeek-R1 teaching examples. It includes completion and correctness metadata. Use short, numeric-answer math word problems; much of the dataset is harder and longer than GSM8K. Label this teacher provenance separately from V4-Pro API outputs.
- [OpenMathInstruct-2](https://huggingface.co/datasets/nvidia/OpenMathInstruct-2): task-aligned supporting prompts, including an augmented_gsm8k source category and expected answers. Its provided solutions were generated with Llama, so using those silently would change the teacher. Regenerate a small sample with DeepSeek when needed. Expected answers for augmentations are not guaranteed independent gold.
- [OpenThoughts-114k](https://huggingface.co/datasets/open-thoughts/OpenThoughts-114k): a later math-only diversity source with DeepSeek-R1 reasoning. Mixed domains and long traces make it less direct for the current numeric scorer.

## The controlled comparison

Actual bounded source inspection changed the initial recommendation: a seeded block scan of256 OpenR1 training records yielded zero complete verified numeric word-problem traces meeting the768-response-token/2048-context limits.154 inspected verified scalar traces had lengths of at least1217 student tokens. A server429 stopped further scanning; cached records and rejection counts were preserved. This is a small bounded scan, not proof no suitable OpenR1 examples exist. Use new, disjoint GSM8K training prompts with concise DeepSeekV4-Pro responses for the next controlled pool. OpenR1 is not training-ready for this recipe and must not be silently stripped or truncated to fit.

1. Freeze a seeded sample of up to512 eligible OpenR1 records, pinning revision, IDs and content hashes. Retain complete, verified, numeric-answer records that fit the student context; report how much filtering removes. Do not silently truncate traces or claim final-answer flags verify every reasoning step.
2. Remove candidate duplicates and matches to existing training/development questions before either selector. Keep the official test set sealed under the current protocol. Provenance and development exclusion do not prove that a public dataset is free of all test contamination.
3. Draw random and student-aware selections from the SAME eligible pool. Match actual supervised-token budgets and use the same shuffled order policy. Keep source mixture, teacher provenance, optimizer and starting Granite checkpoint identical.
4. Student-aware valuation should target skills Granite struggles with while preserving diversity; its score is a hypothesis about usefulness, not a proven causal value. Retain BM25 as a cheap reference if runtime permits.
5. Evaluate on the frozen64 development monitoring questions; report corrected and regressed answers, token counts and selection cost. Repeat seeds if remaining funds permit before claiming robust improvement. Select the final checkpoint before one independent official-test evaluation.

Adding more datasets or more training examples alone does not establish that data valuation helped. The earlier full120 round measures a larger-data intervention; the matched random/valuation comparison isolates the selection strategy more directly.

OpenR1's authors report that reward-model ranking among correct responses did not outperform choosing a random correct response. This is a reason to keep a real random control and to report negative results, not a reason to promise that any ranker must win. [Official filtering report](https://huggingface.co/blog/open-r1/update-2)

Execution of the next targeted round must respect the existing supervisor's reservations and total service ceilings. This document records candidate research and an experimental design, not a claim that the new datasets have already been imported or evaluated.
