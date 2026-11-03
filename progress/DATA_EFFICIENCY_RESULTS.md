# New-cohort data-efficiency results

Completed 6/18 arms. Only completed matched evaluations appear below. Earlier four-arm results remain separate history.

Untouched-base batch8 control: 58/64, with zero training tokens/updates.

| Supervised tokens | Seed | Selector | Status | Numeric correct | Truncated | Actual tokens | Updates | Examples | Forwarded input tokens |
|---:|---:|---|---|---:|---:|---:|---:|---:|---:|
| 32,768 | 42 | random | completed | 57/64 | 0 | 32768 | 32 | 340 | 72309 |
| 32,768 | 42 | skill | completed | 56/64 | 0 | 32768 | 32 | 467 | 81230 |
| 32,768 | 42 | gradient | completed | 56/64 | 0 | 32768 | 32 | 258 | 67658 |
| 32,768 | 43 | random | completed | 55/64 | 0 | 32768 | 32 | 341 | 73145 |
| 32,768 | 43 | skill | completed | 54/64 | 0 | 32768 | 32 | 467 | 81893 |
| 32,768 | 43 | gradient | completed | 54/64 | 0 | 32768 | 32 | 257 | 67502 |
| 65,536 | 42 | random | prepared | pending | pending | pending | pending | pending | pending |
| 65,536 | 42 | skill | prepared | pending | pending | pending | pending | pending | pending |
| 65,536 | 42 | gradient | prepared | pending | pending | pending | pending | pending | pending |
| 65,536 | 43 | random | prepared | pending | pending | pending | pending | pending | pending |
| 65,536 | 43 | skill | prepared | pending | pending | pending | pending | pending | pending |
| 65,536 | 43 | gradient | prepared | pending | pending | pending | pending | pending | pending |
| 131,072 | 42 | random | prepared | pending | pending | pending | pending | pending | pending |
| 131,072 | 42 | skill | prepared | pending | pending | pending | pending | pending | pending |
| 131,072 | 42 | gradient | prepared | pending | pending | pending | pending | pending | pending |
| 131,072 | 43 | random | prepared | pending | pending | pending | pending | pending | pending |
| 131,072 | 43 | skill | prepared | pending | pending | pending | pending | pending | pending |
| 131,072 | 43 | gradient | prepared | pending | pending | pending | pending | pending | pending |

## Paired comparisons

- 32,768 tokens, seed 42, skill_vs_random: -1.56 pp; corrected 3, regressed 4; paired bootstrap95% [-9.38, +6.25] pp; exploratory McNemar p=1.0000.
- 32,768 tokens, seed 42, gradient_vs_random: -1.56 pp; corrected 1, regressed 2; paired bootstrap95% [-7.81, +3.12] pp; exploratory McNemar p=1.0000.
- 32,768 tokens, seed 42, gradient_vs_skill: +0.00 pp; corrected 3, regressed 3; paired bootstrap95% [-7.81, +7.81] pp; exploratory McNemar p=1.0000.
- 32,768 tokens, seed 43, skill_vs_random: -1.56 pp; corrected 3, regressed 4; paired bootstrap95% [-9.38, +6.25] pp; exploratory McNemar p=1.0000.
- 32,768 tokens, seed 43, gradient_vs_random: -1.56 pp; corrected 1, regressed 2; paired bootstrap95% [-6.25, +3.12] pp; exploratory McNemar p=1.0000.
- 32,768 tokens, seed 43, gradient_vs_skill: +0.00 pp; corrected 3, regressed 3; paired bootstrap95% [-7.81, +7.81] pp; exploratory McNemar p=1.0000.

## Two-seed sensitivity

- 32,768 tokens, random: mean 87.50%, sample SD 2.21 pp across two seeds; range 55�57/64. Descriptive only.
- 32,768 tokens, skill: mean 85.94%, sample SD 2.21 pp across two seeds; range 54�56/64. Descriptive only.
- 32,768 tokens, gradient: mean 85.94%, sample SD 2.21 pp across two seeds; range 54�56/64. Descriptive only.
- 65,536 tokens: both complete seed triples are still required for a two-seed summary.
- 131,072 tokens: both complete seed triples are still required for a two-seed summary.

## Selector overhead

All observed feature-attempt durations, including incomplete predecessors, are additional gradient-selector overhead shared across budgets/seeds. Arm token matching does not equalize end-to-end compute.

Planned selector warmup: 8,192 supervised tokens; actual recorded: 8192. Feature-worker elapsed seconds: 2436.508. Monetary cost is not estimated here.

Unique committed warmup progress counted once across restored checkpoints; uncommitted repeated work is not measured as extra tokens.

- Feature attempt gradient_features_math_v1: calibration_refused; observed worker seconds 1001.047.
- Feature attempt gradient_features_math_resume1: completed; observed worker seconds 1435.461.

## Limits

- Only complete matched evaluations enter plots; pending or failed arms are not zero scores.
- This new multi-source cohort is separate from the earlier four32768-token GSM8K arms.
- Shared supervised-token budgets and update counts do not match examples, forwarded input tokens, source mixture, runtime or selector overhead.
- Paired bootstrap intervals resample questions, not training seeds; p-values are exploratory and have no multiplicity correction.
- Two-seed summaries are descriptive; no128-independent-question or precise seed-uncertainty claim is made.
- Targets and skill information are development signals; results on these64 monitoring questions are adaptive, not final-test accuracy.
- Reference matching and numeric final-answer accuracy do not prove every explanation step correct.
- Near-all-data budget levels provide limited selection contrast because selected token exposures substantially overlap.

Public exports contain aggregates and hashes only; questions, model responses, per-question outcomes and private source paths remain local.
