# Matched-token valuation results

These are adaptive development results on the same 64 monitoring questions. The official test split remains untouched. No direction of improvement is assumed.

Each arm starts from the same pinned Granite checkpoint, supervises exactly 32768 answer tokens through 32 effective 1024-token updates, and uses learning rate 0.00002. The shared teacher pool uses DeepSeek V4 Pro with thinking disabled and a 1024-token output limit.

| Seed | Arm | Status | Numeric matches | Strict matches | Truncated | Examples | Input tokens forwarded | Batched generation seconds | Generated tokens |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| 42 | random | completed | 55/64 | 55 | 0 | 286 | 68970 | 97.021 | 6772 |
| 42 | valued | completed | 53/64 | 53 | 1 | 337 | 70774 | 117.812 | 6894 |
| 43 | random | completed | 57/64 | 57 | 0 | 280 | 68534 | 130.234 | 6681 |
| 43 | valued | completed | 56/64 | 56 | 0 | 337 | 71618 | 50.822 | 6740 |

## Paired selection comparison

- Seed 42: valued minus random -2/64 (-3.12 percentage points); corrected 4, regressed 6; paired bootstrap 95% interval [-12.50, +6.25] pp; exact McNemar p=0.7539.
- Seed 43: valued minus random -1/64 (-1.56 percentage points); corrected 1, regressed 2; paired bootstrap 95% interval [-7.81, +3.12] pp; exact McNemar p=1.0000.

## Seed variation

{"available": true, "seeds": [42, 43], "n_seeds": 2, "same_development_questions": true, "limitation": "Two seeds give descriptive variation, not a robust estimate of training-seed uncertainty. The same 64 questions are not 128 independent test questions.", "random": {"mean_accuracy_pct": 87.5, "accuracy_range_pct": [85.9375, 89.0625], "sample_sd_accuracy_pct": 2.209708691207961}, "valued": {"mean_accuracy_pct": 85.15625, "accuracy_range_pct": [82.8125, 87.5], "sample_sd_accuracy_pct": 3.3145630368119416}, "valued_minus_random": {"mean_difference_pp": -2.34375, "range_pp": [-3.125, -1.5625]}}

## Earlier results are separate history

| Checkpoint | Numeric matches | Truncated | Timing basis |
|---|---:|---:|---|
| baseline | 58/64 | 2 | earlier serial generation |
| ranked32 | 52/64 | 1 | earlier serial generation |
| random32 | 52/64 | 3 | earlier serial generation |
| full120 | 52/64 | 1 | earlier serial generation |

Earlier runs differ in data, learning rate, optimization and batching. Their latency totals cannot be combined with batched timings into a speedup claim. A completed random arm alone is not a selection-strategy comparison.

## Limitations

- Weakness signals were derived from these development outcomes; this is adaptive development monitoring, not independent final-test evidence.
- Equal supervised-token counts and optimizer updates do not imply equal examples, input computation, or wall-clock cost.
- The last supervised trace may have a masked answer tail; the full trace remains in the causal input unchanged.
- Candidate NLL was diagnostic only and did not change the frozen skill-based selector in these arms.
- The first random arm also ran the candidate-NLL diagnostic; whole-worker elapsed time therefore is not a matched training-cost comparison.
- Paired bootstrap intervals quantify question resampling, not training-seed uncertainty; p-values are exploratory without multiplicity correction.
- Seed changes can affect initialization, presentation order and random selection together; these runs do not isolate each source of variation.
- Batched timings are amortized generation wall time and cannot be advertised as single-request speedups over earlier serial runs.
- Numerical final-answer scoring does not establish reasoning-step or explanation quality.

Public artifacts contain aggregates and source hashes only. Original questions, teacher traces, model answers, and per-question outcomes remain private.
