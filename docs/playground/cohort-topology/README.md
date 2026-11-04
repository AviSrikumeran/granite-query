# Cohort topology

4 November 2026, America/Chicago. Original code-native architecture study for the overnight design lab. One contiguous source slab separates into three cohort platforms while each of its twenty-four example record identities stays stable.

Published path after release: `/playground/cohort-topology/`.

## Reference evidence

Inspected [Turso's current public homepage](https://turso.tech/) and [public database repository](https://github.com/tursodatabase/turso) on 4 November. The website explicitly contrasts a centralized shared database with a fleet of isolated databases. Root additionally inspected the rendered section: a rounded centralized enclosure contains a 3×3 T1–T9 grid, while Fleet Control Plane sits above separate Own DB tiles. This establishes the shared-enclosure versus isolated-units explanation. Exact transition timing or pointer behavior was not established.

The repository identifies itself as the database implementation and reports an MIT license. It is **not evidence for the license of the marketing website's diagram**. No Turso code, logo, asset or wording is imported here. The original SVG geometry and interaction code adapt an explanatory principle. The use of magenta planes, an eight-second separation sequence, source ancestry and pointer turning are our choices.

## Meaning and content

This is an **illustrative browser model**, not data valuation, training or a research result. Twenty-four authored example records have stable `DEMO-01` through `DEMO-24` IDs. Exactly eight belong to each of Method, Measurement and Scope examples. The grouping demonstrates a UI relationship, not a learned assignment or measured usefulness.

The first view is a still shared pool. Separate cohorts moves the same records into three labeled platforms. Selecting a cell or its record picker shows the same source ID, its original pool cell and its cohort assignment. A faint line connects the selected record back to its original position. Cohort focus dims the other groups but keeps all twenty-four records present.

## Controls

- Shared pool / Separate cohorts: hold either arrangement with damped movement between them.
- Separation slider: manually inspect any intermediate boundary position.
- Play transition: an explicit, finite eight-second demonstration. Pause stops its clock; resume continues it; replay restarts after completion. There is no default autoplay or endless loop.
- Pointer movement turns the sculpture slightly. On reduced motion, turning is disabled and manual arrangements appear directly. Play shows the separated state without motion.
- Select a cell, use the record picker, or focus a cell and press arrows / Home / End. Source identity remains visible below the figure. Explicitly selecting a record outside the focused cohort clears that focus and restores All records, so the selected source remains readable. Hovering another cohort does not clear an intentional group focus.
- Group buttons focus one cohort; All records restores equal emphasis. Reset view clears focus, pointer turning and the arrangement.

Only active interpolation, input settling or explicit playback schedules animation frames. Hidden and offscreen views stop scheduling frames and freeze the replay clock; returning does not fast-forward. No library, provider call, GPU job or service is used. The figure is original SVG with three shaded faces per volume, rather than a pixel/particle field.

## Construction and checks

`geometry.mjs` owns the conserved record fixture, layouts, transforms, projection, face geometry and sequence. `topology.mjs` owns SVG rendering and controls. `topology.css` provides responsive framing, metadata and keyboard focus. The ordinary HTML is the experiment's explanatory shell.

Completed checks:

- `node --check docs/playground/cohort-topology/topology.mjs` passed.
- `node --test docs/playground/cohort-topology/geometry.test.mjs`: four tests passed. They cover identity and assignment conservation over 101 transition samples; finite/framed faces at wide and narrow sizes and pointer extremes; unchanged source origins; and finite sequence endpoints.

Root browser QA before publication:

1. Inspect the still shared pool and separated cohorts. Three platform labels and eight records per platform must be legible without collision or clipping.
2. Test slider, finite replay, pause/resume, all group filters and Reset view. Compare selected ID/ancestry before and after separation.
3. Move the pointer to both sides; try the picker, arrows, Home and End. Inspect whether the selected ancestry line is sufficiently visible around solid surfaces.
4. Verify reduced-motion behavior and offscreen/hidden clock suspension. Check native focus stays visible.
5. At a roughly 390 px viewport, verify no horizontal document overflow and that the picker, controls and cohort labels remain readable. The cell picker is the reliable alternative to small cell targets.

No browser UI was controlled by the worker. Root owns rendered QA, screenshots, publication and shared index edits. Recommendation: **Adapt**, pending that review. The stable identity through an architectural transformation is promising; actual research integration would need a validated cohort/record contract rather than this authored toy.

## Root rendered review

Desktop and 390 × 844 inspection completed on 4 November. Primary controls, selection/context relationships and narrow layouts passed the checks in the [batch02 review](../../../design/reviews/2026-11-04-overnight-batch-02.md). No document horizontal overflow or preview console warning/error was observed. Reduced-motion and hidden/offscreen handlers were inspected in code rather than through an OS preference override. Owner acceptance remains pending.
