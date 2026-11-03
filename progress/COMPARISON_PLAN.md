# First ranked versus random development pilot

Frozen before student evaluation on November 3, 2026.

Question: does BM25 relevance selection outperform uniform random selection for Granite mathematical reasoning when both arms receive the same number of verified teacher examples?

- Student: `ibm-granite/granite-4.2-3b`, revision `4e9c275e232f10211ec88644d106a1f6a1b60e06`.
- Candidate questions: 128 uniformly sampled questions from the previously pruned official GSM8K training pool, excluding the 16-question smoke pilot. Sampling seed: 20261103. The 128 ranking probes are already excluded from the candidate source.
- Development questions: 16 separately reserved questions from that training pool, disjoint from candidates, ranking probes, and prior pilot examples. The official test split is not read.
- Teacher: DeepSeek V4 Pro API, maximum 4096 output tokens per call, at most 128 calls, no automatic retries. Raw outputs, provenance, usage, and rejected records are retained locally.
- Verification: existing strict numeric final-answer check; correct final answers do not establish correct reasoning steps.
- Observed eligible pool: 120; rejected: 4 truncated, 4 incorrect final answers.
- Ranked arm: 32 highest frozen BM25 scores. Scores average prompt-only relevance against 128 training probes using the existing fixed 7344-question index. This is a fixed-reference-index selector, not a newly fit index on the verified pool.
- Random arm: 32 uniformly sampled eligible records, seed 42. Both selectors use the identical eligible pool. Arm overlap is allowed; observed overlap is 9 examples.
- Optimization: one pass over 32 examples per arm; BF16 base, response-only LoRA loss, rank 8, alpha 16, query/value attention projections, learning rate 0.0001, AdamW, batch size 1, gradient norm clipping 1.0, dropout 0. Each adapter starts independently from the same untouched weights and initialization seed 42.
- Evaluation: shared untouched-model baseline and both adapters on the same 16 development questions; greedy decoding, non-thinking chat template, maximum 512 output tokens. Truncation is recorded and never scored as correct.
- Numerical scoring: last numeric value after the final `####`, or last numeric value on the final nonempty line if no marker is present. Also report strict-format correctness separately. This is heuristic answer extraction and does not grade reasoning steps.
- Report: correct counts out of 16, ranked minus random difference, strict-format counts, truncation, generated tokens, latency, and actual supervised training-token counts.

This first pilot matches example count, epochs, and training settings, not total training tokens. Length/difficulty differences can confound results. One seed and 16 development questions cannot establish robust generalization or a publication-grade improvement. A later confirmatory experiment would need additional seeds, token-budget controls, and a frozen final test protocol.

Budget: $3 reserved for teacher generation and $3 for the single 900-second Modal A100 worker. Recorded teacher usage has a conservative peak-price estimate below $0.30. Existing smoke-test usage remains accounted for separately. All amounts are estimates/reservations rather than provider invoices; total service ceilings remain $20 DeepSeek and $30 Modal.
