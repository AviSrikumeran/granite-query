# Granite Query light and form study

The current playground uses green temporarily to isolate the lighting and motion decisions. This replaces the blue/pink experiment after review. It is not the final project palette. The homepage and the separate Modal reference study remain outside this change.

## Review decisions

- Keep the nested-square idea; add legible stepped blocks and separated slabs.
- Remove the folded loop, weave and double helix. The loop and helix exposed their straight box segments and did not read as convincing curved objects.
- Improve both the large forms and the small marks. A curved subject must have an actual curved surface; a chain of boxes is not an adequate substitute.
- Replace the blue/pink material split with one hue and a broad light-to-dark range.
- Bright areas should flare briefly before the next intact form appears. Dark areas should stay dark. Avoid a visible disassembly or long travelling morph.
- The main form and its left, upper-right and faint lower-right repetitions should share the pointer-driven perspective.

## Observed reference and limits

Reference: [Modal homepage](https://modal.com/), inspected November 3, 2026.

A reload showed sparse marks around an outline before the full dense field appeared. The field includes brighter yellow-green marks, dark surfaces, muted repeated silhouettes and a subtle lower-right repetition. Moving the mouse across the field changes its perspective. These are visual observations.

The highlight-only flare followed by a near-instant shape change is the user's clarified motion target. The implementation below is an independent approximation. The exact source timings, lighting calculations, scene and shader have not been recovered. The earlier extraction did not capture the canvas choreography. A screen recording with timestamps would allow more precise frame comparisons.

## One-hue material

The default base is **#78E865** on **#040804**. One swatch and one hex field now control the material; it no longer blends between unrelated blue and pink materials according to world position.

The renderer derives a dark shadow and a pale, slightly yellow highlight from that base. Surface normals determine face illumination, and directional shadow rays test occlusion from other solids in the GPU renderer. Stable per-cell variation and a smaller set of brighter marks create detail within each face. The darkest faces stay dark instead of being lifted by the flare. The page accents follow the chosen hue. The background remains the dark reference neutral during this study.

The palette ramp is a working material model. Different hues still need visual review before becoming project branding.

## Large forms and small marks

| Form | Construction |
| --- | --- |
| Nested squares | Four square frames staggered in depth; sixteen beams with thicker edges. |
| Stepped blocks | Five adjacent columns sharing a baseline, oriented to expose both the treads and risers. |
| Stacked slabs | Three separated flat plates, slightly offset. |
| Rounded tiers | Three true elliptical cylinders with analytic curved side intersections and continuous surface normals. No box-segment approximation. |

Sixteen GPU slots accommodate these scenes. Unused slots have zero dimensions and are skipped. They do not gather in the center or travel between forms.

The independently drawn sixteen-mark atlas uses disks, rings, arcs, curved strokes, a split disk, lens, rounded crosses, triangles, a three-dot cluster and a droplet. Filled marks receive more samples than outlines. The 6.8 px glyph footprint on a staggered 5.4 px lattice leaves clearer gaps between marks. Identity and brightness variation remain stable at each cell rather than randomly replacing symbols each frame.

## Startup, switches and interaction

Startup fills the existing glyph locations over **1.15 seconds**. It begins with a few sparse edge marks, then reveals faces at slightly different thresholds. There is no camera zoom or particle flight.

Each form holds for **4.8 seconds**. During a **0.46-second** event, already-bright marks flare; the geometry switches directly at **0.17 seconds**; the highlight settles over the remainder. No intermediate broken or interpolated object is rendered. These are chosen reconstruction settings, not measured Modal timings. Retargeting an active manual change does not restart its flare.

Pointer movement controls damped yaw (up to about 17 degrees) and pitch (up to about 9 degrees). The same camera transform is used for the primary form and all three repetitions. A restrained local light response supplements the rotation. The lower-right repetition is weaker than the others and fades toward the edge of the field. Green-black atmosphere replaces the prior navy wash.

Clicking the field advances a form. The selector pins a form or plays the sequence. Pause freezes the animation; a paused selection shows the chosen complete form immediately. Escape pauses. **Restart reveal** resets the pointer and sequence and replays startup; it starts motion unless the system requests reduced motion. Reduced motion starts with a fully visible, paused form. Touch drags scroll rather than advancing the shape. Hidden and offscreen fields stop scheduling frames.

## Implementation and verification

- Rendering remains buildless and dependency-free, scoped to the playground.
- The GPU path shades oriented cuboids and analytic cylinders, casts directional shadows, and draws the glyph plus halo in one pass.
- Canvas 2D uses the same scene, ray intersections, palette, reveal and switch timing at a lower sampling density. Its lighting is simpler and does not cast the GPU shadow rays.
- Eight current geometry/material tests cover distinct finite forms, selective highlight flaring, direct shape commits, sequence closure, monotonic startup reveal, bounded palette ramps, dimension-preserving yaw/pitch, and continuous cylinder normals. The six preserved Modal tests also pass.
- Browser review covers the actual WebGL output, all forms, startup replay, pointer response, color editing and invalid-input recovery, a 390 px phone viewport without horizontal overflow, and the Canvas fallback.
- Publication is restricted to the playground renderer, controls, tests and these notes. The homepage blob and all files in the preserved Modal study are compared with the latest parent tree before publishing.

The nested squares remain the main review form. The rounded tiers provide a concrete test of curved representation. Visual quality and exact motion fidelity remain review questions; passing geometry tests does not establish a match to Modal.
