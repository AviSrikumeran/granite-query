# Granite Query light and form study

The isolated playground uses green temporarily to review depth, glyph detail and motion. It is not the final project palette. The homepage and the preserved Modal comparison remain outside this change.

## Reference recording, November 3, 2026

The user supplied a 45.4-second screen recording named **modal hero.mov** and confirmed that they moved the mouse without clicking. The recording is the current motion reference. It was reviewed as an overview and in 50 ms sampled clips. The source has variable frame timing, so these timecodes and durations are approximate.

| Recording time | Visible behavior |
| --- | --- |
| Around 2.50–2.95 s | Sparse, muted marks suggest the outline while the main field remains unlit. |
| Around 3.00–3.25 s | A bright central ignition spreads through the shape rapidly; it settles afterward. |
| Around 7.95–8.05 s | Brighter parts of the box flare while the darker field stays muted. |
| Around 8.10–8.25 s | A few in-between frames reshape the box into separated plates. It is a very fast morph rather than a literal hard cut. |
| Around 8.30 s onward | The new form holds while highlights continue moving over the surfaces. |
| Later cycles | Changes recur roughly five seconds apart as the pointer moves, and also while it is nearly still. |

The earlier implementation interpreted the blink as a direct geometry cut. The recording corrects that interpretation: the transition contains a brief reshaping window. Likewise, the earlier randomly filling startup missed the long sparse hold followed by the fast central ignition.

Pointer movement changes the perspective gently, including the repeated silhouettes. Moving surface highlights are also visible between geometry changes. The current implementation separates an autonomous shape clock, moving surface illumination and damped pointer pose. The recording does not recover Modal's implementation or prove which internal effects use the cursor.

The original recording and extracted images stay local. Only authored code, tests and these findings are published.

## Review decisions retained

- Keep nested squares, stepped blocks and separated slabs.
- Remove the folded loop, weave and double helix. Their curved subjects exposed straight box segments.
- Improve both large forms and tiny marks. Rounded tiers use analytic cylinder surfaces with continuous side normals.
- Use one hue with dark shadows and pale highlights instead of assigning blue and pink to different material regions.
- Keep three dim repetitions: left, upper right and a weaker lower right.
- Pointer motion should gently turn the field. Clicking it must not advance the form. The explicit selector remains a review control.

## One-hue material and moving light

The default base is **#78E865**, with **#040804** as the background. One swatch and hex field derive the shadow and highlight ramp. Page accents follow that hue; the background stays the dark reference neutral during this study.

Surface normals determine face illumination. GPU shadow rays account for occlusion from other solids. A slowly moving directional light and a smooth band travelling through world space change the highlight positions even with a stationary pointer. Stable per-cell variation and a few brighter marks create detail within each face. A flare lifts the already-bright marks while preserving the darkest areas.

This is an authored lighting model, not an extraction of Modal's shader. The resulting material and different candidate hues still need visual review.

## Large forms and small marks

| Form | Construction |
| --- | --- |
| Nested squares | Four square frames staggered in depth; sixteen beams. |
| Stepped blocks | Five adjacent columns sharing a baseline, facing the camera so both treads and risers are visible. |
| Stacked slabs | Three separated plates, slightly offset. |
| Rounded tiers | Three analytic elliptical cylinders with smooth side normals. |

Sixteen GPU slots accommodate the forms; unused slots have zero dimensions and are skipped. During the brief reshape, disappearing parts shrink toward nearby active target solids rather than collecting at a common central point. The camera scale stays fixed. The curved tiers retain analytic curved surfaces in their settled state.

The sixteen-mark atlas contains disks, rings, arcs, curved strokes, split disks, lenses, rounded crosses, triangles, three-dot clusters and droplets. Filled marks receive more samples than outlines. A 6.8 px glyph footprint on a staggered 5.4 px lattice leaves gaps between marks. Cell identity remains stable across frames.

## Choreography and interaction

Startup holds sparse, muted outline marks for about **0.96 seconds**. A center-out reveal fills the existing glyph positions over approximately **0.27 seconds**, with the highlight settling by **1.55 seconds**. There is no geometry zoom.

The autonomous cycle is **five seconds per form**: a **4.5-second hold** and a **0.5-second transition event**. Bright marks flare first; geometry reshapes between **0.20 and 0.40 seconds** into the event, then the light settles. This replaces both the earlier multi-second disassembly and the later hard cut. The values approximate the supplied recording and can be refined further.

Mouse position across the hero controls up to about **6 degrees of yaw** and **3.7 degrees of pitch**, with damping. The primary object and all repetitions use the same camera transform. Moving the mouse does not reset the automatic sequence or trigger the next form. Clicking the field has no form-changing handler.

The selector pins a form or plays the sequence. Selecting while paused displays a complete form immediately. A playing selection uses the short transition; retargeting starts at the displayed geometry without restarting the flare clock. Pause freezes the clock and pointer response; Escape pauses. **Restart reveal** resets pointer influence and replays startup, respecting reduced-motion preference. Reduced motion starts fully visible and paused. Touch drags scroll normally. Hidden and offscreen fields stop scheduling frames.

## Verification and boundaries

Ten current tests cover finite distinct formations, selective bright-area flaring, the short reshape interval, cycle closure, startup hold and radial reveal, palette bounds, limited pointer pose, continuous cylinder normals, interruption start/end geometry, and moving illumination with fixed geometry. The six preserved Modal tests also pass.

Browser review checks the actual WebGL output and shader logs, sparse hold and ignition, short in-between geometry, autonomous playback, ignored field clicks, pointer response, mobile layout without horizontal overflow, and the Canvas fallback. The fallback shares geometry, timing and travelling surface light at a lower density, with simpler shading and no GPU shadow rays.

There are no new runtime packages or build steps. Publication is limited to the playground, its tests and documentation. The homepage and all other repository blobs are compared against the latest parent tree.

The entry script and its geometry import carry the same recording-version query. Public verification caught the new HTML loading an earlier cached animation, so both module URLs change together for this release.

The recording improves the evidence for this pass. The different geometry, composition, glyph shapes and remaining lighting differences mean this is still an independent study rather than a pixel-perfect reproduction.
