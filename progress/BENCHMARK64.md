# Shared64 development comparison

All checkpoints use identical64 questions and a512-token output cap. Official test data remains unused. DeepSeek separately scored63/64 using thinking mode and a4096-token cap.

| Checkpoint | Correct | Truncated | Corrected vs original | Regressed vs original | Accuracy change |
|---|---:|---:|---:|---:|---:|
| baseline | 58/64 | 2 | — | — | +0.00 pp |
| ranked32 | 52/64 | 1 | 2 | 8 | -9.38 pp |
| random32 | 52/64 | 3 | 2 | 8 | -9.38 pp |
| full120 | 52/64 | 1 | 2 | 8 | -9.38 pp |

## Paired uncertainty

- ranked32: paired question-bootstrap95% interval [-18.75,+0.00] percentage points; exact two-sided McNemar p=0.1094.
- random32: paired question-bootstrap95% interval [-18.75,+0.00] percentage points; exact two-sided McNemar p=0.1094.
- full120: paired question-bootstrap95% interval [-18.75,+0.00] percentage points; exact two-sided McNemar p=0.1094.

Exploratory development results, one training seed and no multiplicity correction. Intervals cover question sampling, not training-seed variation. Current32-example arms both regressed from the original; neither establishes a selection advantage. Equal accuracy does not establish equivalent behavior. More-data training, new token-matched controls and a frozen final evaluation are distinct stages.

The original64 attempt timed out; its completed generations were retained and a separately reserved resume filled only missing outcomes. Different question sets must not be joined into an improvement curve.
