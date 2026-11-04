# Source search

4 November 2026, America/Chicago. Original source-discovery interface study. Implementation edits only this folder; root owns shared catalogue, browser QA and publication.

Question: can a query reveal a set of source documents while keeping the exact passage and reason for a match immediately inspectable?

Live destination: [Source search](https://avisrikumeran.github.io/granite-query/playground/source-search/). Deployment is not claimed until root verification.

## Public references and boundaries

- [Exa public site](https://exa.ai/), inspected 4 November 2026: presents source discovery alongside contents, focused highlights and structured outputs. Its excerpt demonstration makes source content part of the search explanation.
- [Official Exa JavaScript SDK](https://github.com/exa-labs/exa-js), inspected the same day: documents search with highlights and retrieval of contents; identifies an MIT license. This is SDK context, not proof that the homepage or its assets share that license.

The root rendered the current homepage and observed a prominent query input, Search/Agent modes, latency presets, category chips and Results/Answer/Structured output choices. The initial output was empty while the prompt typed; no external search was run. A reference screenshot was captured by the root.

The source → excerpt relationship is the adapted principle. Our spatial document deck, local keyword ranking, explicit why-it-matches panel and pointer-lit document field are original. The source landscape, layout, transition timing and pointer behavior remain original; rendered input/mode/output observations do not establish those details. No logo, code, font, screenshot or site asset was copied. No SDK, dependency or paid provider is used.

## Content and interaction

Six authored records cover protocol, results, uncertainty, provenance, citations and limitations. They describe evidence-presentation principles, never model outcomes. Every fixture includes an explicit boundary. The interface makes no web, Exa or model request.

Search requires every normalized keyword to appear in the title, exact excerpt or category. Title matches rank first, but no confidence percentage is shown. Why-this-matches names the term and actual matching field. Excerpts are unchanged strings from `sources.mjs`, highlighted with safe text nodes.

The Landscape view presents stable, titled document sheets. Distance is explicitly decorative, not semantic relevance. Selecting a sheet updates its exact excerpt and provenance. Hover only moves a soft light; it never changes selection. List offers the same documents and selection in a denser layout. Search retains a selected source if it still matches, otherwise selects the first new result. No-match queries have an explicit reset action.

Mouse/tap and native buttons work throughout. Source arrows move between results; Home/End choose first/last. Input Enter searches. Nothing autoplays. User-triggered result transitions are finite, respect reduced motion and cancel when hidden or offscreen. Reduced motion also suppresses pointer light and sheet tilt.

## Files, checks and remaining QA

- `sources.mjs`: authored records, normalization, AND matching and deterministic ranking.
- `studio.mjs`: result deck/list, stable selection, exact excerpt/match explanation, SVG connections and bounded pointer light.
- `studio.css`: document material, concentrated magenta selection, readable inspector, responsive list/field.
- `index.html`: input, fixture boundaries, meaningful initial query and reference notes.
- `verify.mjs`: identity, AND behavior, match ownership, ranking, normalization and exact excerpt provenance.

Run `node --check docs/playground/source-search/studio.mjs`, `node --check docs/playground/source-search/sources.mjs`, and `node docs/playground/source-search/verify.mjs`.

Root QA: desktop/~390px overflow and source title readability; click/tap a document and verify exact excerpt; hover without selection changes; search “model revision” and “uncertainty”; nonsense query + reset; Landscape/List retain selection; arrows/Home/End; reduced motion; console errors. Save a landscape and narrow/list screenshot. Inspect connector endpoints after viewport changes.

Provisional judgment: **Adapt**. Discovery, source identity and exact excerpt are connected visibly. The spatial deck is intentionally decorative and still needs owner judgment; no usability benefit is asserted. This differs from local document-section navigation and from extracting a single input document.


## Root rendered review / 4 November

Desktop and 390 x 844 review completed. Screenshot artifacts: `source-search-desktop.png` and `source-search-mobile.png` in the design chat overnight artifact directory. The [batch04 review](../../../design/reviews/2026-11-04-overnight-batch-04.md) records exact interactions, fixture limits and corrections. Provisional **Adapt**, owner acceptance pending. Reduced-motion handlers were inspected in source; no OS preference override was performed.
