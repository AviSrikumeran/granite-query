# Overnight teacher-feedback results

Status: completed. No Modal use. Official test remains sealed.

| Role | Development correct/32 | Retention correct/32 | Caps dev/retention | Loss tokens | Updates |
|---|---:|---:|---:|---:|---:|
| baseline | 30 | 29 | 0/1 | 0 | 0 |
| error | 30 | 26 | 0/3 | 5888 | 8 |
| random | 30 | 28 | 0/1 | 5136 | 8 |

## Paired comparisons

- error_vs_base, development: +0.000pp, corrected0/regressed0, question-bootstrap95%[0.0, 0.0]pp.
- error_vs_base, retention: -9.375pp, corrected0/regressed3, question-bootstrap95%[-21.875, 0.0]pp.
- random_vs_base, development: +0.000pp, corrected0/regressed0, question-bootstrap95%[0.0, 0.0]pp.
- random_vs_base, retention: -3.125pp, corrected1/regressed2, question-bootstrap95%[-15.625, 6.25]pp.
- error_vs_random, development: +0.000pp, corrected0/regressed0, question-bootstrap95%[0.0, 0.0]pp.
- error_vs_random, retention: -6.250pp, corrected1/regressed3, question-bootstrap95%[-18.75, 6.25]pp.

Teacher:32 original requests,27 qualified. Peak-rate token estimate$0.23698488, not invoice. No new teacher collection is implied by this report.

## Limits

- Single seed; both32-question partitions are adaptive TRAIN-development, not final test.
- Retention set measures same-task retention, not broad ability.
- Error/random receive equal examples and updates with common replay, but unequal full-target tokens5888/5136.
- Teacher final number and supplied arithmetic were checked; all semantic steps were not independently verified.
- Question bootstrap does not cover training-seed uncertainty; comparisons exploratory without multiplicity correction.
- Loss reduction, feedback qualification and software tests are not established accuracy gains.
- All-identical outcomes can yield a zero bootstrap interval without establishing model equivalence.
