# Workflow lanes

4 November 2026, America/Chicago. Original buildless component study for the overnight design lab. Only this directory is changed by its implementation.

## Question

Can a task trace make a query's evidence route immediately understandable while retaining the density and precision of a developer tool?

Live destination: [Workflow lanes](https://avisrikumeran.github.io/granite-query/playground/workflow-lanes/). The parent agent owns catalogue registration, browser verification and publication. Publication is not claimed by this README before that work completes.

## Reference and source boundaries

- [Trigger.dev observability and monitoring](https://trigger.dev/product/observability-and-monitoring), inspected 4 November 2026: public product content presents real-time task monitoring, filtering and logging/tracing as ways to inspect task execution.
- [Trigger.dev public repository](https://github.com/triggerdotdev/trigger.dev), inspected the same day: describes a full task trace for each run and identifies its license as Apache-2.0. This establishes product/source context; it does not establish parity with the exact current marketing animation.

The stable trace, nesting, explicit step identity and contextual inspector are adapted principles. The exact lane layout, magenta styling, hover cursor and replay choreography are original design proposals. Exact Trigger.dev transition timings and hover behavior were not observed in a rendered browser in the research pass. No logo, screenshot, code, font or media asset was copied. No dependencies or paid tools were added.

## What the component means

The authored demonstration has six steps: a full route; source reading; two parallel setup/result checks; uncertainty; and an evidence-linked output. The horizontal axis is relative sequence position, never real execution duration. Data is visibly labeled an illustrative browser replay. No model result or live status is asserted by the replay.

The opening view is complete and paused. A user can select any lane to inspect its input, output, reason and source. Replay animates the order without forcing the inspector to change. The slider selects the relevant step when manually scrubbed. Show all returns to the complete route.

## Interaction and implementation

- `trace.mjs`: immutable authored sequence; pure clamped state and active-step derivation.
- `studio.mjs`: DOM construction, selected inspector, range control, pointer comparison cursor, finite 18-second replay, Escape pause, hidden/offscreen suspension and reduced-motion handling.
- `studio.css`: aligned relative-time grid, depth labels, restrained magenta material, desktop inspector and stacked mobile inspector.
- `index.html`: immediate explanation, visible demo boundary, complete static reading context, reference links and All experiments return navigation.

All row buttons are keyboard reachable. Arrow keys move between steps; Home/End choose the first/last. Native buttons and slider support touch and keyboard. Nothing autoplays; reduced-motion changes pause an active replay and suppress the hover cursor. A deliberate Replay remains available. Animation scheduling stops when hidden or offscreen and resumes from the same progress rather than jumping ahead.

## Verification and remaining review

Syntax checks: `node --check docs/playground/workflow-lanes/studio.mjs` and `node --check docs/playground/workflow-lanes/trace.mjs`. Pure sequence invariants are checked with `node docs/playground/workflow-lanes/verify.mjs`.

Root browser QA still needed before publication: desktop and ~390px layout/overflow; each lane's inspector/source; Replay → Pause → Continue; Show all; slider; keyboard arrow/Home/End; Escape; reduced motion and offscreen suspension; pointer comparison cursor. Check that source JSON resolves at the actual Pages base path. Inspect console errors and save a screenshot for the morning comparison.

Provisional recommendation: **Adapt**. The visible order and linked detail directly address the confusing spatial study. This remains a design judgment, not a usability measurement or owner acceptance. The narrow view deliberately keeps the same lane relationships instead of turning the sequence into another generic card list. Its compact labels and axis require rendered review.

## Root rendered review

Desktop and 390 × 844 browser inspection completed on 4 November. No document horizontal overflow was observed. The principal selections, view/record controls and applicable replay/pause controls worked; screenshots are retained with the overnight design chat. Reduced-motion and offscreen handlers were inspected in source rather than tested through an OS preference change. See the [batch review](../../../design/reviews/2026-11-04-overnight-batch-01.md). Owner acceptance remains pending.
