# Behind the aggregate

4 November 2026, America/Chicago. Original chart-range and underlying-record component study. Publication path: `/playground/result-brush/`.

## Public reference and adaptation

Inspected [Orb's current public homepage](https://www.withorb.com/) and [official overview documentation](https://docs.withorb.com/overview). Public content establishes granular usage metering, event-derived metrics and inspectable views over underlying data. It does not establish the exact geometry, drag behavior or timing of a chart brush. Those are original choices here, not a claim to reproduce Orb's implementation.

No Orb code, asset, logo, billing data or screenshot is imported. No website or application license is assumed. This buildless HTML/CSS/JS/SVG implementation uses no library or service. It borrows the explanatory principle that an aggregate should remain connected to its inputs; it reports no financial information and provides no financial guidance.

## Immutable illustrative content

`records.json` contains **89 authored example records**, divided into Method, Measurement and Scope categories across 16 ordered batches. Batch 07 is deliberately empty. These are interface fixtures, not Granite experiments, model accuracy, spend, revenue or live activity. This boundary appears above the component and in its source file.

Each record has one stable ID, batch, category and neutral authored observation. Loading validates identity uniqueness, batch boundaries and category membership, then freezes the fixture. The chart, interval total, category totals and paginated table all derive from this same fixture. Both interval endpoints are included. No displayed summary is a manually supplied or random number.

## Interaction and behavior

- Drag either range handle to resize the interval. Handles cannot cross.
- Drag inside the interval to move it while preserving its width. Edges clamp the interval without changing its width.
- Drag an area outside the interval to start a new range; dragging either direction is supported.
- Native From / Through sliders, handle arrow/Home/End keys and left/right keys on the plot offer keyboard and tap alternatives. Full range selects all sixteen batches without changing category filters.
- Toggle any legend category to include/exclude its exact records. Excluding every category yields an explicit empty state; selecting batch 07 alone yields the authored empty-batch state.
- Hover the plot for a batch crosshair and exact category counts. Select a record ID to inspect its authored observation and inclusion reason. On mobile this moves to the detail, with a Back to records route.
- The table pages through every matching row in groups of ten. Selected records remain selected while still included in the interval/filter.

Pointer capture is taken by the stable plot element, retained while the pointer moves outside its bounds and released on completion. Pointer cancel, unexpected capture loss, Escape, window blur or a hidden document restores the drag's original interval. A completed drag commits it. There is no autoplay, background timer, model/provider request or simulated live feed. No incidental motion is necessary to read or operate the chart.

## Construction and verification

`model.mjs` owns validation, immutable records, interval normalization, clamped move/resize and exact aggregation. `brush.mjs` owns SVG axes/bars, pointer capture, controls, table pagination and record detail. The chart uses discrete stacked columns because batches are ordered discrete bins, not continuous measurements. Its vertical scale stays anchored to the full fixture while filters change.

Completed: JavaScript syntax check and four model tests. The tests inspect all 136 inclusive intervals and verify that exact rows, category totals and chart-bin sums agree; cover excluded-category and empty-batch states; check move/resize boundaries and width conservation; and reject duplicate identities, out-of-bounds batches and unsupported fixture kinds.

Root browser QA before publication:

1. Initial interval 04–11 must show 43 records. Full range with all categories must show 89. Batch 07 alone must show zero with an explicit explanation.
2. Drag each handle; move the whole interval; start a reversed new range outside it. Check snapping and source-table agreement. Move to the first and last edges without changing a moved interval's width.
3. Release outside the chart and confirm pointer capture ends. Escape/cancel mid-drag must restore the prior range.
4. Use handle keys and native inputs. Toggle all categories off and back on. The same interval stays selected, and no excluded record appears in the table.
5. Select a record and page the table. Count and pagination must agree with all matching records, not just the visible ten.
6. At roughly 390 px, verify no horizontal document overflow, readable axes, range controls and record/detail round trip. Mobile omits the observation table column; its full content remains in the selected record detail.
7. Confirm fixture error behavior, reduced-motion/direct interaction and console errors. Capture the rendered component. The worker used no browser UI; root owns that QA and publication.

Provisional recommendation: **Adapt**, pending rendered QA and owner review. It offers a useful alternative to decorative result counters: an aggregate the reader can inspect and reconcile with its records.

## Rendered review and focused correction

Root browser QA on 4 November verified actual pointer handle resize from 04–11 to 06–11 (33 records), interval movement to 08–13 (40), full range (89), empty batch 07 (zero), keyboard end adjustment, all categories excluded, Measurement-only full range (31), and mobile BR-003 detail parity. At a 390 px viewport the document client/scroll widths both measured 375 px, so no horizontal overflow was observed.

The mobile screenshot showed the redundant SVG “BATCH / ORDERED FIXTURE” caption colliding with the interaction help. Focused correction round 1 removes that caption at the narrow breakpoint while retaining batch ticks, units and the visible drag help. Root owns final visual recheck and screenshot packaging. No aggregate or interaction logic changed in this correction.


## Root rendered review / 4 November

Desktop and 390 x 844 review completed. Screenshot artifacts: `result-brush-desktop.png` and `result-brush-mobile.png` in the design chat overnight artifact directory. The [batch04 review](../../../design/reviews/2026-11-04-overnight-batch-04.md) records exact interactions, fixture limits and corrections. Provisional **Adapt**, owner acceptance pending. Reduced-motion handlers were inspected in source; no OS preference override was performed.
