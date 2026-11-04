# Code map

4 November 2026, America/Chicago. Original buildless code-to-diagram study, intended route `/playground/code-map/`.

Four readable pseudocode regions map to four diagram regions: shared cohort, exposure budget, paired comparison and qualified report. The scope and budget support the comparison; the comparison supports a bounded report. Selecting either code or drawing updates the same record identity and explanation. The opening view is static and complete.

All code is explanatory pseudocode and all content is an authored browser demo. Nothing executes a protocol, loads questions, trains a model or reports actual outcomes. The paired rows and matching marks depict relationships, not question results, scores or telemetry. No private chain-of-thought is presented.

## Reference and adaptation

Two public reference sources, inspected 4 November 2026:

1. [Inngest current homepage](https://www.inngest.com/). The root agent rendered the hero code with three durable `step.run` regions, left-brace markers and Completed / Running status highlights; root captured the active status moving between named blocks. Public page content also includes Before / After architecture illustrations. This supports code-region correlation. Our selection/replay is authored; exact elapsed timings, pointer behavior and execution behavior are not copied or claimed.
2. [inngest/website](https://github.com/inngest/website). Its README identifies the repository as Inngest's marketing, documentation and blog website; the visible tree includes components and animation helpers. No applicable reuse license was established in this inspection. Public availability alone is not treated as permission to copy.

No source, markup, assets, screenshots, logo or exact composition from Inngest was reused. This study's drawing, layout, pseudocode, record text and interactions are original. The synchronized selection and responsive diagram are our adaptation, not a claim of exact reference behavior or conversion performance. Root owns any rendered reference capture and final visual QA.

## Controls

- Click/tap a code block or diagram region to select that record on both sides. Selection is stable; hover does not change it.
- Up/Down or Left/Right move among records. Home/End choose the first/last. SVG regions also support Enter/Space.
- Previous / Next select one neighboring record. Show diagram scrolls to the drawing.
- Guide through 4 records starts at the first and advances at 3.6-second intervals, then stops after the fourth. Pause guided view, Escape or any manual selection stops it. Hidden/offscreen views suspend the timer. This is a guided presentation, not execution.
- Reduced-motion styling removes incidental motion; enabling the preference stops a guided view. The initial view never autoplays.
- Held URLs: `?step=scope`, `?step=budget`, `?step=compare`, `?step=qualify`.
- At narrow widths the same diagram rearranges vertically, retaining its dependency connections and readable labels rather than shrinking the desktop diagram.

## Files and checks

`index.html`, `style.css`, `model.mjs`, `map.mjs` are the complete implementation. No dependency installation, external assets or network calls are required.

Passed syntax checks: `node --check docs/playground/code-map/model.mjs` and `node --check docs/playground/code-map/map.mjs`.

Passed model checks verify unique correspondence between step IDs, code IDs and diagram IDs; complete wide/narrow layout coordinates; finite bounds; and the finite guided sequence ending at the last record. Root browser QA: desktop/narrow composition, visual wire endpoints, reciprocal code/diagram selection, keyboard equivalents, focus visibility, replay/pause/end behavior, selected explanation, no horizontal document overflow and console errors.

Recommendation: **Adapt pending rendered review**. Precise code and a clear dependency diagram offer different entry points to the same protocol. Original homepage, accepted studies, shared catalogue/registry, research data, training and publication are outside this subtask.

## Root rendered review

Desktop and 390 × 844 checks completed on 4 November. Main selections, keyboard actions and narrow layouts passed the [batch03 review](../../../design/reviews/2026-11-04-overnight-batch-03.md). No document horizontal overflow or preview console warning/error was observed. Reduced-motion/offscreen handling was inspected in source; no OS preference override was used. Owner acceptance remains pending.
