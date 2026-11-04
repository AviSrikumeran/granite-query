# Granite low-effort misses: paired answer and training-data review

**Status: review complete; training benefit unproven. High priority. November 3, 2026, America/Chicago.**

All five low-effort misses are retained. Three are supported process failures; two are reference-sensitive. DeepSeek nonthinking solves all three process failures, and the same Granite checkpoint also solves all three in its sampled nonthinking answers. There were no new model calls or training runs. The original 27/32 score is unchanged.

| Case | Granite low / tokens | DeepSeek nonthinking / tokens | Assessment |
|---|---:|---:|---|
| Garlic: units and separate requirements | 15 / 351 | 72 / 196 | process_failure |
| Books: recognized gifts disappear from the sum | 76 / 108 | 81 / 199 | process_failure |
| Plane fuel: a corrected count is not propagated | 98000 / 324 | 106000 / 169 | process_failure |
| Bedbugs: elapsed intervals versus numbered days | 10 / 54 | 10 / 106 | reference_sensitive |
| Trees: mean of rates versus pooled rate | 3.875 / 324 | 3.875 / 91 | reference_sensitive |

## Garlic: units and separate requirements

Source ID: `gsm8k:train:05709`. Dataset reference: 72.

A three-clove batch covers two vampires, eight bats, or three wights. The requested groups are 30 vampires, 40 bats and 12 wights.

Granite observed text: Replaces a three-clove batch with one clove, then treats the separate creature requirements as simultaneous coverage and takes a maximum.

DeepSeek comparison: Keeps the three-clove multiplier for each group, computes 45, 12 and 15 cloves, and sums them to 72.

Verified arithmetic: 3*(30/2+12/3+40/8) = 72; 30/2 = 15.

Data implication: Examples that preserve batch sizes and named units through each conversion; contrast sequential/additive requirements with explicitly shared or parallel capacity.

The generated reasoning explicitly shows both substitutions. This describes the observed trace, not a mechanistic account of the weights.

## Books: recognized gifts disappear from the sum

Source ID: `gsm8k:train:03027`. Dataset reference: 81.

Start with 72 books; add 12 monthly books, purchases of five and two, and gifts of one and four; then remove 12 donated and three sold books.

Granite observed text: Recognizes the two gifts as an additional five books, but omits that five when writing the net-change equation. The arithmetic on the incomplete equation is correct.

DeepSeek comparison: Carries every addition and removal into the final signed ledger, including both gifts.

Verified arithmetic: 72+12+5+2+1+4-12-3 = 81; 72+12+7-12-3 = 76.

Data implication: Short solutions that name every incoming and outgoing quantity and include each once; include already-counted quantities so the model must avoid both omissions and double counting.

The omitted term is directly visible in the generated reasoning. The earlier final-answer-only audit could not identify it.

## Plane fuel: a corrected count is not propagated

Source ID: `gsm8k:train:00743`. Dataset reference: 106000.

Fuel uses 20 gallons per mile plus three per person and two per bag. There are 30 passengers and five crew, two bags per person, and 400 miles to travel.

Granite observed text: Initially computes bags for 30 passengers. It later includes five crew in the people count, but retains 60 bags rather than recomputing 70 bags for all 35 people.

DeepSeek comparison: Defines 35 people first, derives 70 bags from that same set, and uses both counts consistently in the per-mile rate.

Verified arithmetic: (20+3*(30+5)+2*(2*(30+5)))*400 = 106000; (20+3*35+2*60)*400 = 98000.

Data implication: Examples that define the full entity set once and derive every dependent count from it; contrast each attendee with passengers-only or students-only wording.

The stale bag count is explicit in the generated reasoning. Final-number agreement alone would not establish this explanation.

## Bedbugs: elapsed intervals versus numbered days

Source ID: `gsm8k:train:03588`. Dataset reference: 30.

The population triples daily and reaches 810 after four days. The wording does not explicitly distinguish day zero from day one as the starting observation.

Granite observed text: Uses four elapsed tripling intervals, giving 810 divided by 3 to the fourth power.

DeepSeek comparison: All four tested DeepSeek modes make the same interval interpretation and return 10. The source reference instead counts three transitions from day one to day four.

Verified arithmetic: 810/3**4 = 10; 810/3**3 = 30.

Data implication: Quarantine this wording from corrective supervision. If teaching interval counting, write separate explicit day-zero/four-interval and day-one/three-interval problems with independently checked labels.

Both arithmetic results are exact. A reference mismatch is not sufficient evidence that the model's interval arithmetic is wrong.

## Trees: mean of rates versus pooled rate

Source ID: `gsm8k:train:03921`. Dataset reference: 4.

The four height/branch pairs are 50/200, 40/180, 60/180 and 34/153. The question asks for average branches per foot without specifying the weighting convention.

Granite observed text: Computes total branches divided by total height, a height-weighted rate. Its arithmetic is exact for that interpretation.

DeepSeek comparison: Nonthinking uses the same pooled rate. All three thinking modes reach the 2048-token cap discussing the two interpretations and produce no completed final answer.

Verified arithmetic: (200+180+180+153)/(50+40+60+34) = 3.875; (200/50+180/40+180/60+153/34)/4 = 4.

Data implication: Quarantine the ambiguous original. Teach explicitly equal-weight averages and pooled rates as contrasting tasks, rather than forcing one answer for unspecified weighting.

The source reference averages four per-tree rates equally. Both models' completed low/nonthinking outputs use a different defensible convention.

## Candidate curriculum

Prepared 15 untrained seed examples: nine manually reviewed questions from the existing TRAIN teaching pool and six authored counterfactual examples, five per skill family. All exact calculations were checked. The 200-question development exclusion was checked by IDs, normalized text and a limited numeric-masked lexical diagnostic. None entered a live training manifest.

The assistant targets contain concise named calculations and final answers. Raw target token counts exclude template/EOS and cannot be treated as an actual supervised-token budget. These are posthoc development-informed training candidates, not independent evaluation cases.

| Training source ID | Family | Purpose |
|---|---|---|
| gsm8k:train:04233 | units_and_aggregation | Meal quantities to bags to cost |
| gsm8k:train:03612 | units_and_aggregation | Cards through students, packs and cost |
| gsm8k:train:04326 | units_and_aggregation | Two sellers with different price units |
| gsm8k:train:03019 | complete_quantity_ledger | Inventory with a mixed-color outgoing gift |
| gsm8k:train:05346 | complete_quantity_ledger | Donations from multiple locations and a later addition |
| gsm8k:train:01306 | complete_quantity_ledger | Carry all three spending categories into the balance |
| gsm8k:train:02606 | entity_scope_and_dependencies | Students and adults have different fees |
| gsm8k:train:05541 | entity_scope_and_dependencies | Separate adult tickets, child tickets and concessions |
| gsm8k:train:04040 | entity_scope_and_dependencies | Different consuming and sharing groups |
| authored:units-sequential | units_and_aggregation | sequential |
| authored:units-parallel | units_and_aggregation | parallel |
| authored:ledger-new-gifts | complete_quantity_ledger | new_gifts |
| authored:ledger-counted-gifts | complete_quantity_ledger | already_counted |
| authored:scope-all | entity_scope_and_dependencies | all_attendees |
| authored:scope-subset | entity_scope_and_dependencies | apprentices_only |

## Reference defects found during candidate review

Two references passed the existing exact-annotation/final-number checks but contained contradictory prose. This is a targeted manual finding, not a rejection-rate estimate for the full pool. The existing pool was left unchanged.

- gsm8k:train:03273: The reference final answer and annotated arithmetic give 0.08 dollars profit per ear, but one prose sentence says 0.098. It also mixes dollar and cent wording. Exclude this reference explanation pending a separate semantic repair and review.
- gsm8k:train:04624: One prose sentence describes five tractor teams for four days while its adjoining computation and the question require seven tractors for three days. Exclude this reference explanation pending a separate semantic repair and review.

## Experiment required to establish usefulness

1. Treat these three process failures as development-informed hypotheses. First expand manual error review to more development questions before choosing category weights.
2. Before retraining, compare a short entity-and-quantity-ledger prompt with the current prompt on separate transfer-development questions, using repeated decoding and total-token accounting. A prompt or mode change may improve reliability with the original weights.
3. Build a larger semantically reviewed training pool with varied contexts. Use these 15 examples to establish quality criteria; do not fill the pool with numerical clones of the five missed questions.
4. Compare targeted selection with random selection from the same reviewed pool. Apply the same concise worked-solution style and validation rules to both arms, and match actual supervised tokens and optimizer updates.
5. Use fresh copies of the same base checkpoint and identical adapter/optimizer settings. Validate native low-effort serialization, role masks, target completeness and EOS before any run. Include an untouched-base comparison.
6. Freeze a new transfer-development set from untouched TRAIN questions or independently authored families. Keep all original 200 development questions excluded from training. These five reviewed cases are diagnostic, not independent confirmation.
7. Report paired corrections/regressions, accuracy, total tokens, truncation and runtime in low-effort mode; also check nonthinking and instruction/tool/grounding retention. Repeat decoding or training seeds before stronger claims.
8. Keep the two ambiguous references out of corrective supervision. A separate clarification/interval/averaging task can teach explicit conventions with verified labels.
9. Launch training only through a separately reviewed and funded protocol. This review adds no jobs, reservations, live manifests or official-test access.

## Limits

- Five selected misses from one sampled 32-question study. This diagnoses observed text, not hidden model internals or the causal effect of training.
- All three process failures were solved by Granite in sampled nonthinking responses, but mode and random decoding differ; this does not prove a deterministic mode effect.
- DeepSeek is an evidence source, not an automatic ground-truth oracle. Reference-sensitive items preserve their original grades.
- Semantic review was performed by this assistant and is not an independent second-rater study. Candidate checks and examples are a starter specification, not evidence of improved model performance.

The earlier final-answer-only review was cautious about the book and fuel mistakes. Reviewing their preserved generated reasoning now supplies explicit evidence of the omitted gift subtotal and stale bag count. This describes generated text rather than a direct measurement of internal computation.

Reproduce locally: `python research/analyze_low_effort_errors.py`, then `python research/build_low_effort_page.py`. These require the existing private inference receipts and curator notes, TRAIN teaching/development artifacts and local pinned tokenizer. They do not call providers.
