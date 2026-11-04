# Research atlas

4 November 2026, America/Chicago. Original reading/navigation study, separate from all existing playgrounds. Only this folder is changed by its implementation.

Question: can visitors find the protocol, finding and limitations of a research note without reading everything or losing their place?

Live destination: [Research atlas](https://avisrikumeran.github.io/granite-query/playground/research-atlas/). Root owns browser QA, registry/catalogue updates and publication; this README does not claim deployment has happened.

## Public references

- [Mintlify documentation](https://www.mintlify.com/docs), inspected 4 November 2026: the public documentation surface exposes grouped navigation, a search entry and structured guide destinations. The current [homepage](https://www.mintlify.com/) provides documentation links and positions the platform around documentation. These are one official-site reference, not proof of exact interaction timing.
- [Mintlify starter repository](https://github.com/mintlify/starter), inspected the same day: the README identifies guide pages, navigation, customization and API reference examples; the repository identifies an MIT license. It is a starter, not evidence that every Mintlify website or hosted interface asset is MIT.

The stable breadcrumbs, grouped navigation, section outline and search entry adapt observable documentation patterns. The exact pale editorial layout, authored research note, local keyword index, ranking, result snippets, anchor/history behavior and selected-section treatment are original implementation choices. Source-page geometry, search behavior and motion were not observed in a rendered browser by this implementation agent; root may add rendered observations later. No code, logos, fonts or assets were copied.

## What it does

The page is one six-section authored fixture: overview, protocol, finding, sources, limitations and revisiting the record. It is visibly a demonstration, has no research scores and performs no model/API call.

Desktop keeps grouped navigation, current breadcrumb and section outline visible. Scrolling updates reading context without adding history entries. Choosing a section adds a stable hash, scrolls to the exact heading and focuses it. Browser Back restores the previous chosen section. Narrow screens use a section picker in place of crowded sidebars.

Search is local keyword matching across titles, summaries, keywords and body text in `content.mjs`. It requires all normalized query terms, ranks title matches first, highlights matches safely through text nodes and shows meaningful snippets. It never generates an answer. Empty query offers all six destinations; no match has a useful explicit empty state.

Open search with the visible buttons, `/` when not typing or Ctrl/Command K. Up/Down chooses a result; Enter opens and focuses its heading. Escape or Close returns to the opening control. Native modal behavior contains focus. Search result selection uses the same stable section routes as ordinary links. Reduced-motion preference changes navigation to immediate scroll. There is no autonomous animation or carousel.

## Files and checks

- `index.html`: complete authored note and section navigation; content survives without JS.
- `content.mjs`: immutable section index, normalized AND search, ranking and snippets.
- `studio.mjs`: exact anchor navigation, history, heading focus, current context, local command dialog and safe highlighting.
- `studio.css`: editorial hierarchy, responsive sidebars, section progress and modal.
- `verify.mjs`: search ranking, normalization, section identity, AND queries, no-result handling and snippet bounds.

Run `node --check docs/playground/research-atlas/studio.mjs`, `node --check docs/playground/research-atlas/content.mjs` and `node docs/playground/research-atlas/verify.mjs`.

Root QA before publication: desktop/narrow layout and document overflow; every section route and focused heading; search “protocol”, “uncertainty” and a nonsense query; keyboard result navigation; Esc restoration and modal focus containment; choosing two sections then Browser Back; direct hash entry; manual scrolling context; reduced motion; console errors. Save a screenshot of ordinary reading and the search result state.

Provisional recommendation: **Adapt**. Exact local navigation offers a calmer counterpart to motion studies and makes limitations a first-class destination. Actual usability, final site information architecture and owner acceptance remain unmeasured/pending.

## Root rendered review

Desktop and 390 × 844 checks completed on 4 November. Main selections, keyboard actions and narrow layouts passed the [batch03 review](../../../design/reviews/2026-11-04-overnight-batch-03.md). No document horizontal overflow or preview console warning/error was observed. Reduced-motion/offscreen handling was inspected in source; no OS preference override was used. Owner acceptance remains pending.
