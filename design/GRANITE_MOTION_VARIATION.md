# Modal reference reconstruction in the Granite Query playground

The current task is to reproduce the supplied Modal reference before exploring variations. The custom nested frames, weave, folded loop, helix and rounded tiers have been removed from the active playground. The research homepage and the earlier Modal comparison files remain unchanged.

## Current visual target

Reference evidence is the user's 45.4-second **modal hero.mov** recording, supplied November 3, 2026, plus the earlier captured Modal fields. The user confirmed mouse movement without clicking. Recording extracts remain local; they are not uploaded with this change.

The source's compact object, empty surrounding area, limited glyph population and fragmentary reflections are part of the target. Filling the hero with a large stippled sculpture missed that composition. The page now places the text above a smaller, centered field.

At desktop sizes the box spans approximately a quarter of the content width. The illustration unit is 7.4% of that width, with responsive limits. The glyph spacing and mark size scale with the illustration rather than staying as large fixed screen pixels on a phone. The sampling grid is anchored to the scene center, preserving the structure's proportions and cell identities when resized.

The nominal 95 px illustration unit uses a 6.4 px staggered pitch and a 7.4 px glyph footprint; the visible ink is smaller than that footprint. The renderer samples only the compact field region. Empty holes in the cage and the space between the small cubes remain empty.

## Recorded formations and order

| Form | Reconstructed geometry |
| --- | --- |
| Box | Twelve beams form the twelve edges of an open cubic cage. |
| Separated plates | Three thin, aligned square plates with vertical gaps. |
| Small cubes | Eight cubes at the corners of a larger cube; front and back projections overlap differently as the mouse turns the view. |
| Stairs | Five contiguous stair sections, with visible treads, risers and a continuous side wall. |

The sequence is **box → plates → small cubes → stairs**, matching the supplied recording. It uses a fixed camera scale. The four configurations are proportioned to a consistent projected width. There are twelve scene slots, with unused slots skipped.

The atlas now follows the visible symbol vocabulary: disks, hearts, stars, Y marks, triangles, crosses, rings, diamonds and squares. Filled marks receive more samples than outlines. Glyph identity stays stable during the animation.

## Reflected fragments

The earlier renderer placed three smaller, identically oriented copies around the main object. This made complete duplicates easy to recognize.

The current reconstruction casts rays through axis-reflected geometry:

- The left view reverses the depth axis, exposing the stairs' flat back.
- The upper view reverses the vertical axis, exposing undersides.
- The lower-right view reverses the horizontal axis and is substantially weaker.

Each view has its own offset, scale, directional fade and depth falloff. The upper and lower views are vertically foreshortened to match the flatter reference fragments. All share the same damped camera turn. The foreground volume occludes reflected geometry, including behind the cage's holes, leaving partial silhouettes outside the primary object. The lower-right view is a faint hint rather than another complete, equally prominent form.

These are authored transforms selected to match the observed appearance. They are not recovered Modal scene parameters or proof of its internal mirror implementation.

## Color and illumination

The reference green is **#7FEE64** on **#040804**, with dark green shadows and pale yellow-green highlights. The working palette is a reference match, not a custom Granite Query brand direction.

Face normals, directional shadow tests, a moving light and a travelling surface band create the changing brightness. Stable per-cell variation adds detail. Bright areas flare while the darkest areas remain muted. Reflections use a much less saturated material.

The headline, description and actions are centered above the field. Project-specific branding, copy and working research links remain. The illustration uses no captured Modal raster image as a replacement for the live geometry.

## Motion evidence and implementation

The recording was inspected as an overview and in 50 ms sampled clips; timecodes are approximate because it has variable frame timing.

| Recording time | Observation |
| --- | --- |
| Around 2.50–2.95 s | Sparse, muted outline marks hold before ignition. |
| Around 3.00–3.25 s | Illumination rapidly spreads through the field from the center. |
| Around 7.95–8.05 s | Bright sections flare before the change. |
| Around 8.10–8.25 s | A few in-between frames reshape the box into plates. |
| Later cycles | Changes recur roughly five seconds apart while the mouse moves or remains nearly still. |

The reconstruction retains the sparse startup hold, center-out ignition, short highlight-led reshape and five-second automatic cycle. The chosen event has a 4.5-second hold plus a 0.5-second event; geometry reshapes for 200 ms within that event. It is not the earlier multi-second disassembly or a literal hard cut.

Mouse movement adds up to about six degrees of yaw and 3.7 degrees of pitch. It does not restart the sequence or require a click. Clicking the field does not advance a form. The selector is an explicit review control.

Pause freezes the clock and pointer response. Selecting while paused shows a complete form immediately. Escape pauses. Restart replays startup and clears pointer influence. Reduced-motion preference starts fully visible and paused. Touch drags scroll normally, and hidden/offscreen fields stop scheduling frames.

## Verification and publishing

Eleven current tests cover reference geometry counts, projected scale and empty space, cage holes, reflected stair silhouettes, foreground occlusion, selective flaring, brief morph bounds, startup, palette ranges, pointer pose, retargeting and moving light. The six preserved Modal geometry tests also pass.

Browser review checks all four configurations, the reflected back/underside views, compact desktop composition, proportional mobile glyphs without horizontal overflow, actual WebGL shader logs and the Canvas fallback. The fallback uses the same reflected views and foreground clipping at a lower sampling density, with simpler light/shadow treatment.

The entry script, geometry import and stylesheet carry the same version query to avoid stale mixed releases. No runtime packages or build step are added. Publishing is restricted to playground code, its tests and these notes. Every other repository blob, including the homepage and preserved Modal comparison, is checked against the latest parent tree.

This study now follows the reference formations and composition. Glyph placement, shading and reflection falloff remain independently authored approximations rather than extracted source code.
