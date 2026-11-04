# Local capacity and training-dose comparison

Status: completed. No new teacher requests or Modal use.

| Role | Development/32 | Retention/32 | Caps dev/retention | Loss tokens | Updates |
|---|---:|---:|---:|---:|---:|
| baseline | 30 | 29 | 0/1 | 0 | 0 |
| error | 28 | 27 | 0/1 | 47104 | 64 |
| random | 29 | 25 | 0/0 | 41088 | 64 |

## Paired results

- error_vs_base, development: -6.250pp; corrected0/regressed2; question-bootstrap95%[-15.625, 0.0]pp.
- error_vs_base, retention: -6.250pp; corrected0/regressed2; question-bootstrap95%[-15.625, 0.0]pp.
- random_vs_base, development: -3.125pp; corrected0/regressed1; question-bootstrap95%[-9.375, 0.0]pp.
- random_vs_base, retention: -12.500pp; corrected0/regressed4; question-bootstrap95%[-25.0, -3.125]pp.
- error_vs_random, development: -3.125pp; corrected0/regressed1; question-bootstrap95%[-9.375, 0.0]pp.
- error_vs_random, retention: +6.250pp; corrected3/regressed1; question-bootstrap95%[-6.25, 18.75]pp.

## Limits

- Capacity, dose and learning rate changed together; no isolated causal attribution.
- Same small adaptive development and retention partitions as earlier study.
- One training seed; question bootstrap does not measure seed uncertainty; exploratory comparisons uncorrected for multiplicity.
- Complete targets cause unequal token exposure47104/41088 despite equal examples/updates.
- Historical baseline reused with physical hash-bound unchanged data/model/inference receipts; no baseline rerun or fabricated terminal.
- Same-task retention does not measure broad ability.
- No robust generalization or data-value claim from a favorable small development score.
