# Granite Query: Search Based Ranking and Pruning of Training Data for IBM Granite

## Current direction (November 3, 2026)

Current evidence: 40 HF repositories were sampled (312 complete training rows); the 1800-question multi-source teacher pool finalized 1565 reference matches; a separate 2048-question human-reference pool finalized 1930 matches and 223827 answer tokens, with 200 development questions withheld. All 3130 CountSketch features and all 12 approved multi-source 32k/64k arms are complete. The old watcher exited with `approved_grid_completed`; do not restart it to repeat this block or launch the deferred 131k plans.

The matched original remains 58/64. At 32768 supervised tokens, random scored 57/64 and 55/64 across seeds42/43; skill and gradient each scored 56/64 and 54/64. At 65536 tokens, random and skill each scored 56/64 and 58/64; gradient scored 56/64 and 56/64. No arm exceeds the original and no consistent ranking advantage is demonstrated. Preserve the earlier four-arm study as separate historical evidence.

The independent human-reference v2 study is complete on its separate 200-question development set: untouched baseline 179/200 with 8 truncations, random64k 174/200 with 2, and skill64k 171/200 with 2. Both adapters regressed despite fewer truncations. Skill minus random is -1.5 percentage points, with exploratory paired question-bootstrap95% interval [-4.5,+1.5]; no ranking benefit is established. The baseline took 592.229 worker seconds/398.467 generation seconds; skill took 511.475/280.067 and generated23,934 tokens. Timings are amortized batched GPU measurements, not deployed request latency. Calls `fc-01M6HQ96BT1DPAA44VV01CTZAJ` (random) and `fc-01M6HQYSYHN8M5FJ14GFTXASB9` (skill) are terminal with validated results. These single-seed development results cannot be joined to earlier64-question scores as an improvement curve.

The 32-question teacher-depth feasibility pilot completed all 64 original requests and retained 29 eligible pairs: 3,552 concise and 9,643 thinking supervised tokens. Recorded peak token cost is about $0.07909, settled as $0.08 in local accounting. This is teacher-data feasibility, not a Granite training gain. Four separate final-scale modules reached52 synthetic checks. A separate10-check model-layout prototype is not integrated into saved contract/seal formats; it does not complete compatibility. Scaled GPU/teacher executors and controller integration also remain unfinished. No actual final seal, official-test access or public model API execution has occurred.

All study GPU calls are terminal; root provider reconciliation is ongoing. The next work is unpaid final-scale implementation, error/source/layout audit and funding review. Do not automatically launch more training or access official test data because the human pair completed. Read durable results, reviews and ownership before acting.

Latest scope correction: the user explicitly requests a40-source Hugging Face import effort and effective use of the entire existing $20 DeepSeek/$30 Modal credits. The four initial equal-token arms were a first controlled block, not the stopping point. Count successful raw imports separately from metadata reviews and training-ready examples, and reject unsuitable sources instead of padding the count with duplicate forks. Keep math, logic and coding schemas separate. Continue useful measured work while preserving final evaluation/API funds. Consult progress/DISTILLATION_REFERENCES.md for verified Granite/Mistral/Llama recipes. Actual provider consumption must be distinguished from local reservations; the historical18:30UTC Modal observation of about$2.32 was not the previous$12 conservative allowance and is not a current balance.

The user has explicitly authorized using the full $30 Modal ceiling effectively, together with the existing $20 DeepSeek ceiling. The intended deliverable is a useful, reproducible specialized Granite checkpoint and a testable API, supported by measured evidence about data selection. A successful infrastructure smoke test or a tied small pilot is not completion. Do not guarantee positive results, exhaust credits on purposeless runs, or widen this first study to coding/general knowledge. Follow progress/RESEARCH_EXECUTION_PLAN.md for the expanded bounded sequence, including matched-token random controls, repeated seeds when feasible, a frozen final evaluation, and serving preparation.

The full project is NOT complete after the first tied pilot. The user explicitly requires matched DeepSeek and Granite evaluation on GSM8K, visual representations, and further measured Granite improvement rounds. Earlier completed stages include the16-question bridge (DeepSeek15/16 versus Granite13/16), frozen64 monitoring comparisons, the full120 adapter and the negative human200 pair. Supervision now follows reconciliation and unpaid final-evaluation/API prerequisites. Accuracy improvement cannot be guaranteed or invented.

Working title: Granite Query: Learning More from Less.

Research question: Can student aware data selection help Granite learn mathematical reasoning from DeepSeek more efficiently than random selection?

The user selected the DeepSeek API as teacher, superseding the hosted distilled-teacher pilot below. The authorized first API pilot reuses the 16 seeded training questions from that prepared pilot; no held-out test questions are sent. It uses `deepseek-v4-pro`, saves raw responses and token usage, and checks final answers locally. API aliases may change; the response model identifier is recorded rather than represented as an immutable weights revision.

Total available credit ceiling is $50: $30 Modal and $20 DeepSeek. Do not assume another $50 is available. First establish a small end-to-end experiment before expanding compute. The API pilot launches no GPU jobs.

Planned deliverables include reproducible ranked versus random comparisons, student-aware selection, resumable autonomous execution with periodic reports, and an evaluated Granite checkpoint served on Modal through a Vercel website/backend. Scheduled supervision and the public GitHub Pages research dashboard are active. Public model serving is not deployed. The first completed ranked/random pilot's protocol remains in progress/COMPARISON_PLAN.md. The requested roughly1000 benchmark questions mean evaluation questions, not software checks or training runs. Prefer the full1319 official questions only if actual development calibration and fresh whole-bundle funding support it; otherwise choose1000 before any test access. The older256 protocol is prepared history, never a preliminary peek. Keep credentials out of repository files and chat.

Team member and coordinator: Avinash Sri-Kumeran (netID: aus4).

## Confirmed scope

Does better training-data selection let IBM Granite achieve the same held-out math accuracy with fewer examples?

- Target task: GSM8K grade school math word problems.
- Candidate training pool: DeepSeek-generated math solutions, with explicit teacher provenance and final-answer checks. Alpaca is not part of this design.
- Ranking queries: a frozen, seeded subset of GSM8K's official training split.
- Future teacher input questions: the remaining official training questions, separate from the ranking queries.
- Held-out evaluation: official GSM8K test data, used only for grading. Neither test questions nor test answers influence ranking, deduplication, filtering, or parameter selection.
- Selector: BM25/deduplication was the original cheap reference. Later completed studies compare student-skill/diversity and gradient-alignment selection with random controls; none has established a selection advantage.
- Comparison: retain the historical same-size pilots separately. Current controlled arms match supervised-token budgets and updates from the same eligible pool; example counts, forwarded input tokens and selection overhead can differ. Overlap between arms is permitted.
- Training: separate copies of the same Hugging Face Granite checkpoint, identical LoRA/optimization settings, multiple sizes and seeds. Report normalized exact-match accuracy and seed variation honestly.

## Phase boundaries

Phase 1 completed local Ollama compatibility runs. Original MP2 remains unchanged.

Phase 2 established the local preparation and selection pipeline. Its original question-only selections were provisional; later completed studies selected from shared, reference-checked teacher-answer pools. Any new cohort still needs its own eligibility, isolation and selection checks before fine-tuning.

Historical Phase 3 first prepared a hosted DeepSeek-R1-Distill-Qwen-32B pilot on16 training questions. The user superseded that route with the DeepSeek API; credentials were configured and later teacher generation, Granite training and development evaluations actually ran. The old hosted-pilot preparation is not an active credential blocker or a new launch instruction. Current state and budgeted continuation are described above and in progress/RESEARCH_EXECUTION_PLAN.md. Do not place credentials in chat.

The prior Avi's Orchard/Alpaca description is superseded by this brief.
