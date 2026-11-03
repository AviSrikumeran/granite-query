# First ranked versus random results

This is a single-seed development pilot, not a final-test benchmark. Each arm trained on 32 examples from the same 120 verified teacher candidates. Both were evaluated on the same 16 separate training-split development questions.

| Model | Numeric matches | Strict format | Truncated | Training tokens | Mean response seconds |
|---|---:|---:|---:|---:|---:|
| Baseline | 13/16 (81.25%) | 13/16 | 0 | — | 2.74 |
| Ranked | 13/16 (81.25%) | 13/16 | 0 | 3260 | 2.37 |
| Random | 13/16 (81.25%) | 13/16 | 0 | 2534 | 2.36 |

Ranked minus random: +0 correct answers, or +0.00 percentage points. One question changes the percentage by 6.25 points.

## Paired comparison

Ranked only correct: 1; random only correct: 1; both correct: 12; both incorrect: 2.

## What this means

Ranked and random selection tied on this development set. Ranked used 28.65% more supervised training tokens than random. This run therefore provides no demonstrated fixed-token data-efficiency advantage for ranking.

Compare each trained adapter with the original model to assess the observed effect of this small fine-tuning run. Compare ranked with random to assess the observed selection strategy difference. Neither comparison establishes a robust causal effect from this one pilot.

## Manual answer audit

All 48 outputs were manually reviewed: each has a plain numeric final-answer marker, with no truncation. Strict-format and numerical scoring agree. Ranked training fixes one rate-inversion error but introduces one cost-accounting error, leaving the total unchanged. Random correctness matches the original model question-for-question. Two errors persist in both trained arms; one benchmark item has ambiguous wording relative to its reference interpretation. Its frozen score is retained without post-hoc exclusion.

## Limitations

- One seed and 16 training-split development questions.
- Equal examples and updates, not equal supervised training tokens.
- Selection and training order are entangled.
- Development question text contributed to the fixed BM25 index corpus statistics; development answers and outcomes were not used in ranking.
- Numeric extraction is heuristic and does not grade explanation quality.
- Latency is exploratory: sequential evaluation without repeated randomized timing.

The numerical scorer uses the last numeric value after the final answer marker, or on the final nonempty line when no marker is present. Truncated generations are never counted correct. Audit disagreements against the preserved original outputs before interpreting a small score difference.

## Next confirmatory experiment

Use multiple selection/training seeds; fit relevance statistics without the evaluation questions; shuffle both arms using the same order policy; match supervised-token budgets; and keep a final test set untouched until the method is frozen. No additional paid run is automatically launched.
