# From a pilot to a useful specialization study

The user authorized maximizing the existing $30 Modal and $20 DeepSeek credits on November 3, 2026. These are total ceilings, including previous usage. This project is active; the first tied pilot was a pipeline check, not the promised research result.

## Latest expansion:40-source imports and meaningful credit use

The user further requested an effort to import40 distinct Hugging Face datasets and to use the full service credits efficiently. This supersedes treating the initial four32768-token jobs as project completion. A source registry must record real training-split sample imports, pinned revisions, license/provenance, byte/row counts and rejection reasons. Metadata reviews are not imports, and raw imported rows are not automatically verified training examples. Do not count many duplicate GSM8K forks as independent coverage. Keep logic/coding data in separate schemas until a corresponding verifier and evaluation protocol exist.

The first512-attempt pool and all four32,768-token arms are complete. Random scored55/64 and57/64, versus skill-selected53/64 and56/64; untouched Granite remains58/64. Preserve this as a separate historical study. The40-source audit imported312 complete sample rows from40 repositories, not complete datasets. A separate three-source cohort completed1800 teacher attempts,1565 numeric-reference matches and150750 answer tokens, then supplied1541 common candidates after holding out24 gradient targets.

All 3,130 LESS-inspired CountSketch features and all 12 approved 32k/64k arms are complete. The old watcher exited with `approved_grid_completed`; its completed block must not be restarted. Results on the same 64 development questions are:

| Supervised tokens | Selector | Seed42 correct | Seed43 correct |
|---:|---|---:|---:|
|32768|random|57/64|55/64|
|32768|skill|56/64|54/64|
|32768|gradient|56/64|54/64|
|65536|random|56/64|58/64|
|65536|skill|56/64|58/64|
|65536|gradient|56/64|56/64|

Untouched Granite remains58/64. No arm exceeds that baseline and no consistent ranking advantage is demonstrated. The18-plan grid also contains six deferred131072-token plans, which have not run. That level uses87.85% of149203 available tokens, forcing at least86.17% per-arm overlap; it is a near-all-data reference, not a strong selection contrast. Larger524288-token studies are not prepared or automatically funded.

The separate human-reference cohort completed 2,048 teacher requests, 1,930 reference matches and 223,827 available answer tokens, with 200 different training-split development questions withheld. Its v2 untouched baseline completed 179/200 with 8 truncations: 592.229 worker seconds, including 398.467 seconds of amortized batch generation. The reviewed 65,536-token seed42 random arm completed 174/200 with 2 truncations; call `fc-01M6HQ96BT1DPAA44VV01CTZAJ` has validated terminal evidence. Five fewer correct answers is a regression despite reduced truncation. Skill launched through the controller after the stopped app's task counter cleared and is running as `fc-01M6HQYSYHN8M5FJ14GFTXASB9`. Both arms start independently from the same pinned base/current recipe. Use `human_study_control.py` only, poll the existing skill call and keep its score unavailable until validated completion. No new human watcher is running. The 200-question results cannot be joined to 64-question scores as an improvement curve.

Use DeepSeek credits for useful teacher work: task-aligned solutions on new training prompts, additional independently checked candidate solutions on difficult/uncertain examples, and rubric-assisted explanation audits checked against reference answers or executable verification. Do not assume the teacher is ground truth, regenerate already verified easy answers indefinitely, or manufacture long responses to spend tokens. Record marginal useful verified examples per dollar and student gains per training token. Continue beyond the first block while useful budgeted stages remain, retaining final evaluation and serving allowance.

The spending target is the available credits, not an excuse to burn the final cents or promise100-percent training efficiency. Exact provider consumption, reservations, billing-delay buffers and remaining credit must be shown separately. The historical November3/18:30UTC Modal summary reported$2.31593967 metered usage with$0 billed after credits; that observation is not a current balance, and the earlier$12 local entry was an allowance rather than measured usage. Reconcile with the supported billing summary before new expansion. Existing unreported-call liabilities remain reserved until reconciled; never erase them speculatively.

The [Granite/Mistral/Llama reference audit](DISTILLATION_REFERENCES.md) identifies actual public Granite distillation weights and code. The third-party Granite release targets long agentic/tool-use conversations and reports training loss, without a controlled GSM8K gain; do not copy its40K-context30B recipe into our3B numeric task or cite it as proof our checkpoint improved. IBM's much larger post-training recipe also cautions against expecting arbitrary small fine-tunes to outperform an already capable baseline.

## The claim to test

The [DeepSeek reference review](DEEPSEEK_REFERENCES.md) distinguishes verification, predicted usefulness and measured downstream value. Its cited Math/R1/V3/V4 reports motivate the recipe, not a guarantee that it works for Granite.

Can a small Granite model learn grade school mathematical reasoning more effectively from student-aware selected teacher examples than from random examples under the same supervised-token budget?

Small size can make adaptation and deployment economical. It does not guarantee specialization gains, and a large model is not inherently average at every task. Improvement must be observed. More data, a new dataset, a falling training loss, or a custom API by itself is not evidence that valuation worked.

The first task remains concise numeric math word problems. Coding and broad conceptual tutoring require different benchmarks, verifiers and data; they are future extensions.

## Required outputs

- An untouched original Granite baseline and versioned LoRA checkpoints, with pinned model/dependency revisions and training manifests.
- A verified common teacher pool, with teacher/source provenance, rejection counts and deduplication reports.
- A reproducible student-aware selector compared with random selection. BM25 is a cheap historical reference, not a demonstrated valuation method.
- Accuracy, corrected/regressed questions, truncation, actual supervised tokens, selection overhead and training cost. Report explanation brevity separately; do not substitute stylistic resemblance for correct mathematics.
- Matched question-set visualizations and a final frozen-checkpoint evaluation, with paired uncertainty and limitations.
- A demand-driven model API and comparison interface that identify the actual checkpoint and its measured limits. Serving preparation can proceed during research. Public serving follows checkpoint selection and a separately reserved hard usage quota; no indefinitely billable warm GPU.

## Authorized sequence

1. Preserve completed historical stages: the64-question benchmark/resume, full120 adapter,512-attempt concise pool, four original token-matched arms,3130 gradient features and the12-arm32k/64k block. Do not repeat saved generations or restart their completed owners.
2. Finish the human-reference v2 random/skill64k pair through its reviewed controller. Both supervise65536 answer tokens in64 updates with the existing LR0.00002, q/v LoRA8, independent fresh base and seed42. Random exposes561 examples/136319 forwarded input tokens; skill exposes766/150600. Preserve full traces and disclose partial loss masks, unequal input compute and adaptive development selection. Random is terminal at174/200 with2truncations; do not repeat it. Skill has launched as `fc-01M6HQYSYHN8M5FJ14GFTXASB9`; poll that call through the controller instead of launching another.
3. Analyze paired gains/regressions, truncation, actual training exposure, runtime and source transfer against the untouched179/200 baseline on the identical200 questions. Keep earlier64 results separate. More data, a lower loss or a new source is not evidence of a selection advantage. Any further recipe/depth study needs its own predeclared controls, enough complete-token capacity and funding after the final/API allowance.
4. Before official-test access, select one actual checkpoint using development evidence, validate physical source/adapter inventories and obtain measured base/chosen development calibration. Prefer batched inference, preserve raw batch receipts, and test exact shard coverage and terminal-only recovery locally. Post-development adapter hashes establish a later immutable inventory; they do not prove contemporaneous byte identity with the earlier evaluated adapter.
5. Choose one final target before any test access:1000 benchmark questions, or full1319 only if actual development calibration and freshly reconciled whole-bundle funding support it. The user means benchmark questions, not1000 training runs or software checks. The older256 preparation is superseded as a target and must not become a preliminary peek. Freeze the original/chosen pair, source, indices, inference settings and whole denominator once; do not tune, resample easier questions or expand after inspecting results. Budget the same-question DeepSeek reference separately under the matched nonthinking512 protocol, retaining failed, over-cap and truncated outcomes.
6. Complete the missing scaled executors, strict model-layout checks and controller/accounting integration before claiming final execution readiness. The four new `final_scale_contract.py`, `final_scale_receipts.py`, `final_scale_seal.py` and `final_scale_loader.py` modules reached52 synthetic checks, including two loader path-protection fixtures; no actual final seal, access permit or official-test read exists. These checks are infrastructure evidence, not model benchmark answers. Read FINAL_EVALUATION_SCALE_DESIGN.json and preserve the unchanged old256 sources.
7. Prepare and, when prerequisites permit, deploy a scale-to-zero API with checkpoint identity, input/output limits, a fixed request quota and an expiry. Reserve the serving allowance before deployment. If no trained checkpoint beats the base, expose comparisons honestly and preserve the research artifacts; never label a weaker checkpoint improved. Public serving and Vercel integration remain unfinished.

## Spending and continuation

The durable ledger and fresh provider observations authorize each new reservation/launch. Modal usage, a3-dollar collection-lag buffer, open reservations and terminal liabilities are separate. DeepSeek conditional funding-based consumption, peak-rate token estimates and call reservations are separate; never treat a13-dollar teacher allowance as13dollars spent. Keep ceilings at30Modal/20DeepSeek including previous consumption.

Protect5Modal dollars for frozen final evaluation, API and recovery until an explicit final-stage allocation review. The six32768 and six65536-token arms are complete; do not reserve them again. Current paid continuation is the reviewed human-reference pair. Gate any later expansion by resources and measured usefulness, preserving the final/API envelope;131072 remains deferred. The scaled contract proposes compute plus one recovery allowances of12.25Modal dollars for1000 questions or15.75 for1319, and5/7DeepSeek dollars, with other protected/API funds explicit. These are proposed conservative bounds, not existing reservations; the minimum protected5 alone does not fund the larger bundle. Provider runtime, source mixture and exposure are recorded for every arm; CountSketch warmup/collection remains additional selector overhead.

The human-reference2048 collection and32-question depth pilot are complete; do not rerun them. Useful later DeepSeek work includes the matched final teacher comparison after checkpoint/target selection, or a separately reviewed training-data follow-up with sufficient student capacity. Preserve explicit request/input/output bounds, original receipts, zero blind retries and fresh funding. Do not consume credits on duplicated easy answers, broad-source padding or longer-than-needed outputs.

New valuation workers may use a1,800-second hard timeout with one A10080GB,4CPU and32GiB memory. The listed compute rate sums to$0.00081744/second, or about$1.48 over1,800seconds; a$3 reservation also covers startup/storage overhead conservatively. Apply an earlier application deadline, save checkpoints, and finish early when done. This explicitly changes future valuation limits from900seconds to1,800; it does not modify already launched900-second jobs or repeat the completed first smoke test. This adjustment was recorded before any new valuation outcome was observed.

Continue from the pilot into the controlled valuation study even if full120 improves: more-data improvement alone does not establish selection value. Stop only when this bounded sequence has its artifacts/report, the budget cannot support useful next work, or a genuine account/access blocker prevents progress. On failure, save and explain the evidence and the next useful step. Update the journal and public dashboard on meaningful changes. Do not call the whole project complete while evaluation, checkpoint selection, or API delivery is missing.

Sources: [Modal resource prices](https://modal.com/pricing), [OpenR1 dataset](https://huggingface.co/datasets/open-r1/OpenR1-Math-220k), [OpenR1 filtering study](https://huggingface.co/blog/open-r1/update-2).

## Completed teacher-depth feasibility and conditional follow-up

[The design audit](TEACHER_DEPTH_DESIGN.json) led to the completed 32-question pilot at `runs/teacher_depth32_v1`: 64 original requests and 29 eligible paired questions. The paired supervised-token capacities are 3,552 concise versus 9,643 native-thinking tokens. Recorded peak token cost is $0.07909, settled as $0.08 in local accounting, below the original $0.8178 bound. This pilot performed no student training and demonstrates no Granite gain. Thinking mode and output caps both changed, and the full-fit/reference-matched intersection is selected; intermediate steps were not independently verified.

A512-pair teacher expansion would bound13.0843dollars before student compute and is not automatically approved by the completed pilot. Any follow-up needs enough complete-token capacity, correct native/BPE boundaries, identical student inference controls and funds for both student comparison and final/API work. Equal answer-token budgets change example coverage; they do not isolate pure explanation depth. The200-question development holdout and official test stay out of teacher training requests.
