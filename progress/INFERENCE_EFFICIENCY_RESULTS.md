# Granite and DeepSeek inference efficiency

Status: completed. Inference only. Same 32 GSM8K TRAIN development questions; no training or official-test access.

The caps are 512 and 2048 total generated tokens, including reasoning and final output. Each cell uses one sampled response per question. Granite uses its native nonthinking, low-effort and thinking controls. DeepSeek uses nonthinking, low, high and max. These names do not calibrate equal effort.

| Model | Mode | Cap | Reference matches | Total output tokens | Truncated | Total request seconds | Median request seconds | Tokens per correct |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| granite | nonthinking | 512 | 25/32 | 7377 | 5 | 196.09 | 4.57 | 295.1 |
| granite | low | 512 | 27/32 | 6858 | 0 | 185.16 | 5.07 | 254.0 |
| granite | thinking | 512 | 6/32 | 15597 | 25 | 418.37 | 13.22 | 2599.5 |
| granite | nonthinking | 2048 | 27/32 | 11977 | 2 | 319.22 | 4.57 | 443.6 |
| granite | low | 2048 | 27/32 | 6858 | 0 | 185.69 | 4.96 | 254.0 |
| granite | thinking | 2048 | 25/32 | 33965 | 3 | 913.76 | 23.11 | 1358.6 |
| deepseek | nonthinking | 512 | 30/32 | 3904 | 0 | 67.05 | 2.02 | 130.1 |
| deepseek | low | 512 | 26/32 | 8211 | 5 | 116.51 | 3.02 | 315.8 |
| deepseek | high | 512 | 25/32 | 9116 | 6 | 120.87 | 3.23 | 364.6 |
| deepseek | max | 512 | 22/32 | 10392 | 9 | 138.89 | 4.13 | 472.4 |
| deepseek | nonthinking | 2048 | 30/32 | 3893 | 0 | 67.41 | 2.15 | 129.8 |
| deepseek | low | 2048 | 29/32 | 12388 | 2 | 168.25 | 3.22 | 427.2 |
| deepseek | high | 2048 | 30/32 | 12885 | 1 | 159.72 | 3.38 | 429.5 |
| deepseek | max | 2048 | 29/32 | 18413 | 2 | 229.04 | 3.82 | 634.9 |

## Paired changes

| Change | Corrected | Regressed | Accuracy change pp | Exploratory paired 95 percent interval | Extra output tokens |
|---|---:|---:|---:|---|---:|
| granite low minus nonthinking at cap 512 | 5 | 3 | +6.25 | [-9.38, +21.88] | -519 |
| granite thinking minus nonthinking at cap 512 | 0 | 19 | -59.38 | [-75.00, -43.67] | 8220 |
| granite low minus nonthinking at cap 2048 | 3 | 3 | +0.00 | [-15.62, +15.62] | -5119 |
| granite thinking minus nonthinking at cap 2048 | 0 | 2 | -6.25 | [-15.62, +0.00] | 21988 |
| granite cap 2048 minus 512 in nonthinking | 2 | 0 | +6.25 | [+0.00, +15.62] | 4600 |
| granite cap 2048 minus 512 in low | 0 | 0 | +0.00 | [+0.00, +0.00] | 0 |
| granite cap 2048 minus 512 in thinking | 19 | 0 | +59.38 | [+43.75, +75.00] | 18368 |
| deepseek low minus nonthinking at cap 512 | 0 | 4 | -12.50 | [-25.00, -3.12] | 4307 |
| deepseek high minus nonthinking at cap 512 | 0 | 5 | -15.62 | [-28.12, -3.12] | 5212 |
| deepseek max minus nonthinking at cap 512 | 0 | 8 | -25.00 | [-40.62, -9.38] | 6488 |
| deepseek low minus nonthinking at cap 2048 | 0 | 1 | -3.12 | [-9.38, +0.00] | 8495 |
| deepseek high minus nonthinking at cap 2048 | 0 | 0 | +0.00 | [+0.00, +0.00] | 8992 |
| deepseek max minus nonthinking at cap 2048 | 0 | 1 | -3.12 | [-9.38, +0.00] | 14520 |
| deepseek cap 2048 minus 512 in nonthinking | 0 | 0 | +0.00 | [+0.00, +0.00] | -11 |
| deepseek cap 2048 minus 512 in low | 4 | 1 | +9.38 | [-3.12, +21.88] | 4177 |
| deepseek cap 2048 minus 512 in high | 5 | 0 | +15.62 | [+3.12, +28.12] | 3769 |
| deepseek cap 2048 minus 512 in max | 7 | 0 | +21.88 | [+9.38, +37.50] | 8021 |
| deepseek nonthinking minus granite nonthinking at cap 512 | 5 | 0 | +15.62 | [+3.12, +28.12] | -3473 |
| deepseek nonthinking minus granite nonthinking at cap 2048 | 3 | 0 | +9.38 | [+0.00, +18.75] | -8084 |

## Reference interpretation review

Two questions were reviewed after observing reference mismatches. This is not a comprehensive reference audit and is not a new accuracy metric.

- gsm8k:train:03588: The reference treats the first day as the initial group and the fourth day as three tripling transitions. Reading after four days as four elapsed growth intervals gives a different initial count. Reference: 810 / 3^3 = 30. Alternative: 810 / 3^4 = 10. Primary grades are unchanged.
- gsm8k:train:03921: The reference averages the four per-tree branch-to-height ratios. A response instead divides combined branches by combined height, which is a height-weighted mean. Reference: (200/50 + 180/40 + 180/60 + 153/34) / 4 = 4. Alternative: (200+180+180+153) / (50+40+60+34) = 3.875. Primary grades are unchanged.

## Reviewed completed Granite errors

Three observed errors were reviewed with exact arithmetic. Two additional interpretation-sensitive questions are documented in the separate reference audit. This is a diagnostic review, not proof that a new data selector or training recipe helps.

- gsm8k:train:05709, low effort / 2048 cap: returned 15; reference 72. Exact check: 3 * (30/2 + 12/3 + 40/8) = 72. The visible response replaced the three-clove bundle with one clove and used the largest individual requirement rather than summing the separate creature requirements.
- gsm8k:train:03027, low effort / 2048 cap: returned 76; reference 81. Exact check: 72 + 12 + 5 + 2 + 1 + 4 - 12 - 3 = 81. The returned final value disagrees with the complete book-accounting sum. The visible answer alone does not establish which term or arithmetic operation was mishandled.
- gsm8k:train:00743, low effort / 2048 cap: returned 98000; reference 106000. Exact check: (20 + 3*(30+5) + 2*(2*(30+5))) * 400 = 106000. The correct total includes both passengers and crew in the person and bag counts. The returned number is consistent with using 60 bags instead of 70, but that final number alone does not prove the internal mechanism.

Disjoint verified training examples that exercise unit bundles, quantity bookkeeping and entity scope may address these errors. Compare any selected examples against random verified examples under matched training-token budgets; preserve the development exclusions and enterprise-retention checks.


## How to interpret the measurements

- 32 seeded questions from an existing, repeatedly inspected development cohort; one sample per cell; no official-test claim.
- Accuracy means numeric agreement with dataset references. Two posthoc interpretation-sensitive cases are flagged separately; grades and denominators are unchanged.
- Question-bootstrap intervals do not include repeated decoding or training-seed uncertainty; comparisons are exploratory.
- Tokens differ by tokenizer. Both reasoning and final answer count toward the shared native output cap.
- Granite runs batch one on a dedicated A100 with warm weights using Transformers and SDPA. DeepSeek runtime includes network and provider service; neither hardware nor sampling is matched.
- Granite low and DeepSeek low are native controls and do not imply equal internal effort.
- DeepSeek V4 Pro is a much larger teacher model; this is not a parameter-matched architecture comparison.
- A capped unfinished answer is scored incorrect even if a numeric guess appears in its reasoning. No retries or answer-based exclusions.
- The 512 and 2048 caps test bounded-budget behavior, not unconstrained reasoning ability. A truncated answer may succeed with a larger budget.

Runtime in the main table is the sum of serial request durations. Granite also saves synchronized GPU-generation seconds, model-load time, warmup and whole-worker time separately. DeepSeek output totals are the provider completion_tokens field; reasoning_tokens is a subset and is never added twice. Unknown usage is never treated as zero.

Scientific question: does a larger cap or deeper mode correct enough additional questions to justify its extra tokens and request time? Extra spending on wrong or still-incorrect answers is a diagnostic; it does not prove the reasoning could be removed without changing behavior.

Inference settings and data are independently versioned from the earlier 200-question greedy/nonthinking experiment. The new scores must not be joined to old scores as one improvement curve.

Sources: [Granite native modes](https://huggingface.co/ibm-granite/granite-4.2-3b#thinking-modes), [DeepSeek native controls](https://api-docs.deepseek.com/guides/thinking_mode/), [DeepSeek usage fields](https://api-docs.deepseek.com/api/create-chat-completion/).

Granite used two actual provider calls after the first reached its predefined time guard. The second executed only never-attempted cases, on the same GPU class and package versions, within the original $3 GPU envelope. Original provider results remain separate; their union is explicitly a derived artifact. Warm request metrics exclude each call's separately recorded model-load and synthetic-warmup times.
