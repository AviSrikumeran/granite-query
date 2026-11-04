# Proof branches

An isolated, scroll-driven Granite Query specimen. A query connects to three source records, five evidence requirements and a qualified answer. The example is illustrative and asserts no measured gain. All previous studies and the homepage remain protected.

Open `/playground/proof-branches/` and scroll. The map grows in either direction with the walkthrough. Select a node or a record in the narrative to inspect its detail and source. The four stage links jump through the walkthrough; Show full map holds every node for inspection, and Follow scroll restores normal behavior. Move the pointer to turn the map. A focused figure supports arrow keys and Home to recenter.

Reduced motion displays the complete map without scroll tweening or pointer-follow motion. Keyboard turning applies directly. The page has no autonomous animation loop: rendering stops when progress and pointer settle, when hidden, and when the artwork is outside the viewport. The complete text walkthrough works without JavaScript. WebGL is preferred; Canvas 2D preserves the graph with coarser material treatment.

## Editable construction

- `graph.mjs` owns node IDs, evidence text, source relationships, stage thresholds, projected positions and path generation. Nodes grow only after incoming paths reach them. All five requirements merge into the qualified answer. Each path has two stable oriented segments. The renderer uses 39 scene volumes plus one unused slot.
- `study.mjs` maps actual section positions to graph progress, eases toward scroll input, projects accessible node buttons with the same pointer transform as the geometry, and handles selection, navigation and visibility.
- `engine/` independently copies the established glyph atlas and magenta rendering material. Existing folders are not runtime dependencies.
- `index.html` provides the readable walkthrough and record buttons. Keep its narrative consistent with `NODES` when changing the illustrative example. Future real-data integration must replace the example with traceable public records and retain missing or inconclusive states.

Held review links use `?progress=0#query-step`, `?progress=.36#sources-step`, `?progress=.72#evidence-step` and `?progress=1#answer-step`. These bypass scroll progression until Follow scroll is selected. Add `&renderer=canvas` to inspect fallback rendering. Normal catalogue links omit these query parameters.

Run `node --test design/proof-branches.test.mjs` from the repository root. See the [review](../../../design/reviews/2026-11-03-proof-branches.md) and [All experiments](../experiments/).
