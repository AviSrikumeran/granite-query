# Source lens

4 November 2026, America/Chicago. Original, buildless source-to-evidence interaction study. Intended live route: `/playground/source-lens/`.

The question is whether an input/output transformation can make a research claim easier to inspect. One large document stays attached to its structured record. A precise inspection band selects one of four authored passages; the output keeps its exact quote, passage reference and limitation.

All content is illustrative and labeled on the page. There is no model call, live query, training indicator, measured score, remote data request or stored user input. This comparison does not claim that Granite performed the extraction.

## Reference and adaptation

Inspected 4 November 2026:

- [Firecrawl homepage](https://www.firecrawl.dev/): the root agent rendered an Agent prompt with Run control, a structured .JSON panel and scanning text. The Main features section contains Search / Scrape / Interact modes, Python / Node.js / cURL / CLI tabs and a JSON response. This is evidence for a clear input/output pattern, not for conversion performance. The initial text-only web extraction exposed an older Search / Scrape / Map / Crawl arrangement; the rendered observation takes precedence.
- [Firecrawl repository](https://github.com/firecrawl/firecrawl): primarily AGPL-3.0; the README identifies some UI components and SDKs as MIT. The exact marketing component's source/license was not established.

No Firecrawl code, visual assets, logo or source markup was copied. All source files here are original. The inspection band, editorial document, linked quotation and layout are our adaptation. Exact Firecrawl animation timing, pointer behavior and hover states were not captured; this study's transitions are authored rather than a claim of observed parity. The root agent owns rendered reference capture and final browser QA.

## Interactions

- Hover previews a passage. Clicking/tapping a source, choosing a numbered step or using keyboard focus/arrows pins the source/output identity. Pinned selection ignores pointer crossings while traveling between panes. The status offers **Pinned · Follow pointer** to release the pin and resume hover previews.
- Tab through source passages; Up / Down / Left / Right choose adjacent passages. Home and End choose the first/last.
- Readable / JSON changes the representation of the same record and pins the current selection. The JSON is generated from the same passage data.
- Passage reference captures the selected passage index, pins it before scrolling and focuses that exact source. Hover crossings during scroll cannot replace its citation.
- The opening view is still. Play scan cycles passages every 4.8 seconds; Pause scan, Escape or manual inspection stops it. Hidden and offscreen views suspend the timer. Reduced motion disables animated transitions; it also pauses playback if enabled while playing. Playback is always explicit.
- Held review routes: `?passage=cohort`, `?passage=exposure`, `?passage=changes`, `?passage=uncertainty`.

## Files and verification

- `index.html`: semantic source, structured output, visible illustrative status and navigation.
- `style.css`: editorial material, inspection band, restrained magenta and responsive layout.
- `model.mjs`: original illustrative passages and shared structured-record derivation.
- `studio.mjs`: source selection, exact quotation linkage, JSON representation, bounded opt-in scan and accessibility controls.

Passed syntax checks: `node --check docs/playground/source-lens/studio.mjs` and `node --check docs/playground/source-lens/model.mjs`.

Passed logic verification: all four derived records retain their exact source quote and line identity; review IDs resolve uniquely; invalid indexes clamp safely; and the initial HTML source quotations match the shared model. These checks concern citation integrity, not visual quality.

Remaining root browser QA: desktop/narrow layout without horizontal overflow; inspection band follows rows after resize; pointer, tap and arrow selection match the output; source reference visibly returns to the exact passage; Readable/JSON parity; pause and explicit scan; reduced motion; hidden/offscreen suspension; console errors; final screenshot. Recommend **Adapt pending rendered review**: the relation is concrete, while density and material still need visual judgment.

Homepage, accepted studies, catalogue, experiment registry and research/training files are outside this study's implementation scope. The root release adds discoverability and publishes an explicit whitelist.

## Root rendered review

Desktop and 390 × 844 browser inspection completed on 4 November. No document horizontal overflow was observed. The principal selections, view/record controls and applicable replay/pause controls worked; screenshots are retained with the overnight design chat. Reduced-motion and offscreen handlers were inspected in source rather than tested through an OS preference change. See the [batch review](../../../design/reviews/2026-11-04-overnight-batch-01.md). Owner acceptance remains pending.

## Citation stability correction

Root browser QA found that pointer crossings during travel/smooth scrolling could replace a selected citation. Explicit source, keyboard and step choices now pin selection; pointer-following resumes only through its labeled control or an explicitly started scan. The source-reference action captures and pins its identity before scroll/focus. A synthetic DOM event regression check passed: explicit Exposure selection survives hover crossings and simulated scroll crossings, JSON retains the selected identity, and Follow pointer re-enables previews. Syntax check passed. This focused correction preserves the root's rendered-review notes above; root must recheck the reported Exposure → Passage 02 route after refresh.
