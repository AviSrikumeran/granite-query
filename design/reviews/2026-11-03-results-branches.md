# Results and evidence review

3 November 2026. Recommendation: **Adapt**. The separate comparison attaches the preferred proof-branch interaction to the actual public human-reference study. The owner praised the illustrative interaction during this work and asked for a durable library of what works. That feedback is recorded in [the experiment registry](../experiments.json). The new real-data version still awaits a verdict.

[Open results and evidence](https://avisrikumeran.github.io/granite-query/playground/results-branches/), or compare with the preserved [illustrative proof branches](https://avisrikumeran.github.io/granite-query/playground/proof-branches/). The homepage and every earlier study remain unchanged.

## Finding and source scope

The reviewed human-reference snapshot reports untouched Granite at 179/200, random selection at 174/200, and skill selection at 171/200. Skill minus random is −1.5 percentage points, with a paired 95% question-bootstrap interval of −4.5 to +1.5 pp. The interface says **No gain demonstrated**, preserves the negative point estimate and states that the interval spans no difference. This is an adaptive seed-42 training-split development study, not sealed final-test evidence or a causal ranking claim.

Both adapters received 65,536 supervised loss tokens and 64 updates. Examples, forwarded input tokens, runtime and selection overhead are not matched. The evaluation uses the pinned Granite 4.2 3B non-thinking/512 recipe. Numeric final-answer matching does not verify reasoning steps. The untouched model's eight truncated outcomes and each adapter's two truncated outcomes remain visible.

Primary sources reviewed at commit `daf8d1cbe5bd6c93524ebc7a22a930f6c6ef7804`:

- [Human-reference results JSON](https://github.com/AviSrikumeran/granite-query/blob/daf8d1cbe5bd6c93524ebc7a22a930f6c6ef7804/docs/human-study-results.json).
- [Human-reference report](https://github.com/AviSrikumeran/granite-query/blob/daf8d1cbe5bd6c93524ebc7a22a930f6c6ef7804/progress/HUMAN_STUDY_RESULTS.md).
- [Native-study public receipts](https://github.com/AviSrikumeran/granite-query/blob/daf8d1cbe5bd6c93524ebc7a22a930f6c6ef7804/docs/native-reasoning-study.json).

The newer native OPEN/1024 study has a different inference recipe and stays in an independent status panel. The reviewed native snapshot has prepared student jobs without verified terminal scores. Teacher-data collection is not presented as student improvement. Neither the older 64-question studies nor native-study scores are merged into the human-reference comparison.

## Implementation and comparison

The eleven-node geometry, fourteen paths, magenta material and reveal timing are independently copied without changing the earlier folder. The same query-to-records-to-evidence-to-finding progression now presents actual scope, measured budgets, counts, paired uncertainty and receipt fingerprints. Every node links to public evidence. JSON field paths identify which aggregate fields it uses.

The page reads the public feeds on load and explicit refresh. It shows generation timestamps and marks snapshots older than 24 hours stale. Network failures, unsupported recipes, inconsistent counts and unverified jobs do not produce invented scores. A failed refresh retains a clearly labeled previous snapshot when available. The fetched feed digest is visible with full study, model, protocol and result fingerprints. An exact reviewed digest gets pinned report/design links; changed feed bytes get clearly labeled latest-report links instead.

The renderer does not fetch private outcomes or provider state. Validation checks consistency of the public aggregates and their declared provenance; it does not independently reproduce private worker results.

Held review URLs preserve the geometry pose while loading current public data:

- [Evidence pose](https://avisrikumeran.github.io/granite-query/playground/results-branches/?progress=.72#evidence-step).
- [Complete finding](https://avisrikumeran.github.io/granite-query/playground/results-branches/?progress=1#answer-step).
- [Canvas fallback](https://avisrikumeran.github.io/granite-query/playground/results-branches/?progress=1&renderer=canvas#answer-step).

Browser captures accompany the chat delivery. The normal catalogue link has no held-pose query.

## Validation and limits

Ten automated tests pass. They cover the reviewed counts and uncertainty, pending/failed/unverified jobs, invalid scope and recipes, inconsistent counts and supplied statistics, unmatched budgets, missing intervals, stale/future timestamps, digest-gated permalinks, public citations, unavailable native scores, and exact preservation of the illustrative branch geometry after real-data binding.

Browser review covers loaded real counts and confidence interval, source links, node inspection, refresh, scroll stages, provenance disclosure, narrow layout and the fallback renderer. The mobile document and scroll widths match; direct pointer selection does not move the document. Reduced-motion, offscreen suspension and context recovery are inherited and source-reviewed. OS reduced motion, context loss and network-failure UI are not simulated; malformed and unavailable model states are covered by tests.

The current known human-reference study is intentionally a strict contract. A changed study ID or evaluation recipe needs a reviewed adapter rather than automatic cross-study interpretation. Score interpretation remains development evidence. Raw worker artifacts remain private, with their public hashes available for traceability.

Publication is limited to the new specimen, its test/public fixtures/review, the feedback registry, design notes and the experiment catalogue. All unrelated remote blobs are compared before the branch update, including the homepage, illustrative proof branches and latest training outputs.
