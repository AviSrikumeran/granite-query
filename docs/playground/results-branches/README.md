# Results and evidence

A separate comparison binding the preferred magenta proof branches to actual Granite Query public results. The illustrative specimen and homepage remain unchanged.

Open `/playground/results-branches/`. Scroll through query, source records, evidence and bounded finding. Select nodes for public report links, JSON links and field paths. Show full map holds the graph; Follow scroll restores the walkthrough. Pointer and keyboard turning, reduced motion and the Canvas fallback are retained.

## Data contract

`data.mjs` validates and derives the presentation from `../../human-study-results.json`. This view supports the named human-reference v2 study with the Granite 4.2 3B non-thinking/512 evaluation recipe. It checks cohort scope, verified completed receipts, counts, measured exposure, paired differences and intervals before deriving a finding. Incomplete jobs are not zero scores. Unsupported, malformed or unavailable evidence does not fall back to the illustrative example.

The browser fetches the current public feeds on load and on Refresh results, with a timeout and without a polling loop. Generation timestamps remain visible; snapshots older than 24 hours are marked stale. If a refresh fails after a successful load, the previous snapshot remains explicitly labeled. There is no live provider access, training launch or inference call.

`../../native-reasoning-study.json` is an independent status panel. Prepared or unverified native scores remain unavailable. Its OPEN/1024 recipe and outcomes are never merged with the human-reference comparison.

The fetched primary JSON is fingerprinted with SHA-256 when Web Crypto is available. Only an exact match to the reviewed fixture gets the pinned report/design permalinks. A newer or reformatted feed links to the latest report and displays its own generation time and digest. The individual result and protocol hashes come from the public feed; private raw worker artifacts are not exposed.

## Construction

- `graph.mjs`: preserved branch geometry and timing with replaceable node content.
- `data.mjs`: pure validation, source references and bounded interpretation.
- `content.mjs`: feed loading, DOM presentation, tables, provenance and refresh behavior.
- `study.mjs`: preserved scroll/pointer rendering and selection, with accessible labels updated after loading.
- `engine/`: independent copy of the established magenta renderer. No runtime imports from earlier specimens.

Held reviews: `?progress=.72#evidence-step` and `?progress=1#answer-step`. Add `&renderer=canvas` to inspect the simplified renderer. Held queries freeze geometry progression, not data loading; they still read current published records.

Run `node --test design/results-branches.test.mjs` from the repository root. Golden fixtures in `design/fixtures/results-branches/` are already-public aggregate snapshots from commit `daf8d1cbe5bd6c93524ebc7a22a930f6c6ef7804`; they are tests, not runtime fallback data.

See the [review](../../../design/reviews/2026-11-03-results-branches.md), [feedback registry](../../../design/experiments.json), [preserved illustrative version](../proof-branches/) and [All experiments](../experiments/).
