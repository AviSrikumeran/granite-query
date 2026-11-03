# Human-reference development study

New200 development questions; earlier64-question studies remain separate. Official test data remains sealed.

Status: running. Validated completed jobs: 2/3.

| Checkpoint | Status | Numeric correct | Truncated | Actual answer tokens | Updates | Planned examples | Planned forwarded tokens |
|---|---|---:|---:|---:|---:|---:|---:|
| baseline | completed | 179/200 | 8 | 0 | 0 | 0 | 0 |
| random | completed | 174/200 | 2 | 65536 | 64 | 561 | 136319 |
| skill | running | unavailable | unavailable | pending | pending | 766 | 150600 |

## Same200 paired comparisons

- skill_vs_random: unavailable until both complete evaluations validate.
- random_vs_baseline: -2.50 percentage points; corrected 7, regressed 12; paired question-bootstrap95% [-7.00, +1.50] pp; exploratory McNemar p=0.3593.
- skill_vs_baseline: unavailable until both complete evaluations validate.

## Runtime calibration and review

Baseline calibration: validated. Baseline review: reviewed. Pair review: reviewed.
A separately funded pair still requires a calibrated baseline and exact phase review. This report does not inspect funding or authorize work.

## Limits

- This is an exploratory seed42 source and curriculum transfer study, not a robust causal ranking claim.
- The new200 questions are training-split development questions. Earlier64-question results are separate history and are not joined into this improvement curve.
- The unchanged skill selector uses an earlier development weakness signal. Choosing this study after earlier negative results is adaptive research; these200 are not a sealed final test.
- Paired bootstrap intervals resample questions, not training seeds. Three comparisons are exploratory and have no multiplicity correction.
- Equal supervised tokens and updates do not equalize examples, forwarded input tokens, runtime or selection overhead.
- Numeric final-answer scoring and reference qualification do not verify every reasoning step or answer depth.
- Latency is amortized batched GPU generation time, not single-request latency. Recorded worker seconds are not a provider bill.
- Local receipts show last observed progress only. This reporter does not refresh providers, infer funding or repair ambiguous calls.
- The baseline runtime forecast is an explicit planning estimate. Actual worker checks remain1400 seconds training,1600 seconds evaluation and1800 seconds hard timeout.

Public outputs contain aggregates and hashes only. Questions, responses, per-question outcomes, credentials, account details and private source paths stay local.
