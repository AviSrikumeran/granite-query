# Granite Query: Search Based Ranking and Pruning of Training Data for IBM Granite

## Current direction (November 3, 2026)

Current evidence:40 HF repositories were sampled (312 complete training rows); the1800-question multi-source teacher pool finalized1565 reference matches; a separate2048-question human-reference pool finalized1930 matches/223827 answer tokens, with200 development questions withheld. All3130 CountSketch features are complete. The initial four32k arms found no skill-selection advantage. The new random/skill/gradient grid is frozen and actively advancing under a reviewed bounded local watcher; its first random arm scored57/64 versus the matched original58/64. Actual current results, calls, budgets and watcher ownership are in durable files and the runbook. No official test or public model API execution has occurred.

Latest scope correction: the user explicitly requests a40-source Hugging Face import effort and effective use of the entire existing $20 DeepSeek/$30 Modal credits. The four initial equal-token arms are a first controlled block, not the stopping point. Import bounded real training samples with pinned provenance, count successful raw imports separately from metadata reviews and training-ready examples, and reject unsuitable sources instead of padding the count with duplicate forks. Keep math, logic and coding schemas separate. Continue into larger useful data/training budgets and final evaluation while credit permits. Consult progress/DISTILLATION_REFERENCES.md for verified Granite/Mistral/Llama recipes. Actual provider consumption must be distinguished from local reservations; Modal's authenticated summary at18:30UTC reported about$2.32 metered usage, not the previous$12 conservative reservation estimate.

The user has explicitly authorized using the full $30 Modal ceiling effectively, together with the existing $20 DeepSeek ceiling. The intended deliverable is a useful, reproducible specialized Granite checkpoint and a testable API, supported by measured evidence about data selection. A successful infrastructure smoke test or a tied small pilot is not completion. Do not guarantee positive results, exhaust credits on purposeless runs, or widen this first study to coding/general knowledge. Follow progress/RESEARCH_EXECUTION_PLAN.md for the expanded bounded sequence, including matched-token random controls, repeated seeds when feasible, a frozen final evaluation, and serving preparation.

The full project is NOT complete after the first tied pilot. The user explicitly requires: matched DeepSeek and Granite evaluation on Hugging Face GSM8K, visual representations, and further measured Granite improvement rounds. The missing DeepSeek bridge on the same16 development questions is now15/16 versus Granite13/16. A new frozen64 monitoring set and fresh120-example LoRA round are authorized and reserved. Supervision must continue across these queued stages; do not interpret an individual pilot's completion as project completion. Accuracy improvement cannot be guaranteed or invented.

Working title: Granite Query: Learning More from Less.

Research question: Can student aware data selection help Granite learn mathematical reasoning from DeepSeek more efficiently than random selection?

The user selected the DeepSeek API as teacher, superseding the hosted distilled-teacher pilot below. The authorized first API pilot reuses the 16 seeded training questions from that prepared pilot; no held-out test questions are sent. It uses `deepseek-v4-pro`, saves raw responses and token usage, and checks final answers locally. API aliases may change; the response model identifier is recorded rather than represented as an immutable weights revision.

Total available credit ceiling is $50: $30 Modal and $20 DeepSeek. Do not assume another $50 is available. First establish a small end-to-end experiment before expanding compute. The API pilot launches no GPU jobs.

Planned deliverables include reproducible ranked versus random comparisons, a later student aware selector, resumable autonomous execution with periodic reports, and an evaluated Granite checkpoint served on Modal through a Vercel website/backend. Scheduled supervision and the public GitHub Pages research dashboard are active. Public model serving is not deployed. The first ranked/random development pilot is authorized and its frozen protocol is in progress/COMPARISON_PLAN.md. Keep credentials out of repository files and chat.

Team member and coordinator: Avinash Sri-Kumeran (netID: aus4).

## Confirmed scope

Does better training-data selection let IBM Granite achieve the same held-out math accuracy with fewer examples?

- Target task: GSM8K grade school math word problems.
- Candidate training pool: DeepSeek-generated math solutions, with explicit teacher provenance and final-answer checks. Alpaca is not part of this design.
- Ranking queries: a frozen, seeded subset of GSM8K's official training split.
- Future teacher input questions: the remaining official training questions, separate from the ranking queries.
- Held-out evaluation: official GSM8K test data, used only for grading. Neither test questions nor test answers influence ranking, deduplication, filtering, or parameter selection.
- Selector: remove exact/near duplicate questions using MinHash LSH with exact Jaccard checks, then rank using Pyserini BM25 against the training probes.
- Comparison: same-size top-ranked and uniformly random selections from the same eligible pool. Overlap between arms is permitted.
- Training: separate copies of the same Hugging Face Granite checkpoint, identical LoRA/optimization settings, multiple sizes and seeds. Report normalized exact-match accuracy and seed variation honestly.

## Phase boundaries

Phase 1 completed local Ollama compatibility runs. Original MP2 remains unchanged.

Phase 2 is the local preparation and selection pipeline. Until teacher generation occurs, its question-only selections are explicitly provisional and not training-ready. Re-run selection on the shared, verified teacher-answer pool before any fine-tuning.

Phase 3 teacher-generation setup is authorized. The user selected a bounded pilot: DeepSeek-R1-Distill-Qwen-32B, one A100 80GB, 16 uniformly sampled training questions, 15-minute execution limit with a local cancellation watchdog. The pilot is prepared locally; actual cloud execution awaits locally configured Modal credentials. Full-pool generation, Granite fine-tuning and evaluation follow after review of the pilot, not automatically. Do not place credentials in chat.

The prior Avi's Orchard/Alpaca description is superseded by this brief.
