# Native reasoning study

At the last recorded check, the prior shared call had stopped, its remaining audit was queued, and no shared GPU task was active. Billing protection and queued reservations still needed reconciliation before the native baseline could launch. No native-study claim or call was recorded; the baseline remained unlaunched and training still required measured baseline calibration.

This study uses 256 planned paired TRAIN questions and three fresh student conditions. Each adapter receives 16,384 complete supervised tokens over 16 updates. Evaluation uses the same adaptive 200 TRAIN-development questions with native OPEN thinking and a 1024-token generation cap.

| Condition | State | Accuracy |
|---|---|---|
| Fresh untouched Granite | prepared | Unavailable |
| Concise supervision | prepared | Unavailable |
| Native reasoning supervision | prepared | Unavailable |

The stronger 8192-token teacher reference is pending separate review and funding.

- Adaptive 200-question training-split development evaluation; not official final-test evidence.
- The common OPEN/1024 inference condition requires a fresh baseline; prior closed nonthinking 512-token results are separate.
- Equal complete loss tokens and updates do not match examples, forwarded tokens, compute or wall time.
- This compares supervision recipes, not ranking superiority or a pure causal effect of explanation depth.
- Final-number/reference matches do not verify every reasoning step; common full-fit pairs are a selected intersection.
- One training seed; paired intervals cover questions, not training-seed variation; exploratory comparisons are not multiplicity corrected.
- Preparation, collection and a runnable implementation do not establish student improvement.
