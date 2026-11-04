# Review the change

4 November 2026, America/Chicago. Original component study: a precise before/after research-note diff, with selectable edits linked to their review rationale. Publication path: `/playground/review-diff/`.

## Public reference

The requested [graphite.dev](https://graphite.dev/) legitimately redirects to [graphite.com](https://graphite.com/). Its current public homepage presents PR page features around changes, history and comments. The [official overview documentation](https://graphite.com/docs/get-started) describes its review workflow. Root inspected the rendered homepage and selected its PR page feature tab; the promotional pane was mostly dark/transition content. Exact diff geometry, keyboard behavior and timing were **not established**.

The transferable principle is keeping a change and its review context together. Split/unified layout, local marks, source IDs, colors and navigation in this study are our original adaptation. No Graphite code, screenshot, logo or asset is imported. No license for its marketing website or application has been assumed; a CLI repository's license would not license the homepage.

## What this study means

This is an **illustrative change review**, not a real pull request. Four authored example changes make a neutral research note more inspectable: name the baseline, attach a measurement unit, qualify an estimate and keep source/scope beside the conclusion. The previous draft intentionally contains overstatements for the demo; it describes no actual model experiment. No score, gain, interval or Granite outcome is invented.

The JSON fixture is the common source for both revisions, the diff and the rationale. Each change has a stable ID across split and unified views. A browser-local Set tracks inspected edits for this open tab. Reloading clears those marks. They approve, merge or modify nothing on GitHub.

## Interaction

- Select a change in the left rail or click its hunk heading. The same change highlights in the diff and fills the rationale panel.
- Split / Unified changes the layout while preserving selected change and review marks. Narrow screens start unified; choosing Split stacks the revisions and labels that adaptation.
- Next / Previous, J / K, or arrow/Home/End keys in the change rail navigate the same stable IDs.
- Mark reviewed toggles a local acknowledgement and the inspected count. It does not post a review.
- On mobile, the selected hunk exposes Read rationale, and the rationale provides Return to selected edit. The long document and notes can be traversed without losing the selected identity.
- Open example records exposes the actual local JSON fixture.

No autoplay, background timer, service or dependency is used. The only transition is a short progress-bar change; reduced-motion disables it and uses direct scroll positioning. Failed or invalid fixture loading declares the example unavailable and disables controls.

## Implementation and verification

`model.mjs` derives full revisions, ordered line numbers, stable hunks and both diff representations from `changes.json`. `review.mjs` renders the views and controls; `review.css` provides the dense tool layout and narrow-screen adaptation; `index.html` supplies the semantic shell.

Completed: JavaScript syntax check. Three model tests pass: stable mapping of split/unified change groups; continuous line numbers that reconstruct both full revisions; rejection of invalid type, duplicate identities and missing content. No files outside `review-diff` were changed.

Root browser QA before publication:

1. Inspect all four changes, especially the last hunk. Each heading, line pair and rationale must remain associated and legible.
2. Select change 3, mark it reviewed, switch split/unified and confirm the same selected ID and mark survive.
3. Use Next/Previous, J/K and rail arrow/Home/End navigation. Check focus and scroll positioning.
4. Mark/unmark multiple edits; count, progress bar, left-rail ticks and selected button agree. Reload clears marks.
5. At roughly 390 px width, verify no horizontal document overflow, unified default, stacked split labels and the selected edit → rationale → edit round trip.
6. Open the local fixture route; inspect reduced-motion behavior and console errors. Capture the rendered study.

Root owns browser observation, screenshots, publication and shared catalogue edits. Recommendation: **Adapt**, pending rendered QA and owner review. Change identities paired with a concise rationale can explain research-record revisions without requiring visitors to infer meaning from a raw diff.

## Root rendered review

Desktop and 390 × 844 checks completed on 4 November. Main selections, keyboard actions and narrow layouts passed the [batch03 review](../../../design/reviews/2026-11-04-overnight-batch-03.md). No document horizontal overflow or preview console warning/error was observed. Reduced-motion/offscreen handling was inspected in source; no OS preference override was used. Owner acceptance remains pending.
