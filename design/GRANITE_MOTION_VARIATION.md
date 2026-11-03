# Granite Query blue and pink motion study

The playground now explores an original Granite Query direction using light blue, brighter rose pink and new three-dimensional structures. The dense glyph-field technique developed in the Modal study remains the rendering basis. The reference comparison is preserved at `docs/playground/modal-study.html`; the research homepage is outside this change.

## Color direction

| Role | Working value | Purpose |
| --- | --- | --- |
| Light blue | #81D9FA | Cool side of the field, headline accent, primary action |
| Rose pink | #FF79BD | Warm side of the field and the lower edges of the new mark |
| Deep navy | #080C18 | Quiet background for bright glyphs |
| Main text | #EDF0FA | Readable neutral foreground |
| Supporting text | #A3AEC7 | Descriptions and secondary navigation |

Pink is more saturated than baby pink, while blue stays light. Blue and pink blend through lavender where they meet. Light travels gently across the structure without introducing the green or yellow accents from the reference. The swatches and hex fields update the field and page accents immediately; Reset colors restores the working values. Changes stay in the current browser page and refresh returns to the defaults.

## Original forms

| Form | Construction |
| --- | --- |
| Folded loop | Sixteen connected ribbon sections follow a closed loop with a half twist. |
| Nested frames | Four square frames are staggered in depth and offset in size and position. |
| Weave | Two sets of eight crossing beams form an open interlaced surface. |
| Double helix | Two ribbons curl around one another, with eight sections per strand. |

Every formation uses sixteen active oriented solids. Part positions, dimensions and orientations move between configurations. Unlike the reference study’s axis-aligned shapes, these structures use quaternion orientations, so ribbons can fold and turn in three dimensions. The camera scale remains fixed.

## Motion and interaction

The sequence holds each form for 2.4 seconds and morphs into the next over 3.2 seconds, for a 22.4-second loop. Quintic easing provides zero velocity and acceleration at the endpoints. Quaternion interpolation takes the shorter rotation path to avoid an unnecessary spin. A new target captures the currently displayed geometry, so mid-transition changes do not jump back to a previous pose or reset the illumination clock.

Pointer movement adds bounded rotation and local light. Clicking advances the form. Pause freezes the simulation; selecting a form while paused displays it immediately for review. Restart returns to the first form while preserving pause status and the current colors. Reduced-motion preference starts paused. Touch drags scroll the page rather than advancing the form.

## Rendering and composition

The renderer casts orthographic rays through oriented solids at each point of a staggered 5.6 px glyph lattice. Sixteen glyph variants have stable identities, with a distribution favoring filled marks. Mipmapped filtering, a 1.5–2× backing resolution, soft edge coverage and a combined glyph/halo pass retain the dense, smooth field from the preceding refinement.

Face normals contribute depth shading. World position determines the blue-to-pink mix, with subtle highlights and dim echoes around the primary structure. The Canvas 2D fallback samples the same oriented scene and uses the same glyph atlas with a simpler color treatment.

The desktop composition places project-specific copy on the left and the field on the right. Smaller screens stack them. The new page uses an independently drawn geometric mark and the project’s existing “Learning more from less” research theme. Research and methods links lead to existing project evidence; the page does not present new accuracy or deployment claims.

## Boundaries and validation

The new page contains no Modal logo, product copy or captured images. The Modal reconstruction and its assets remain available separately for comparison. The current palette is a reviewable visual direction, not a completed project-wide design system.

Six new geometry tests check finite formations, normalized rotations, shortest-path interpolation, loop continuity, bounded changes between sampled frames, interruption continuity and oriented-ray intersections. The six existing Modal geometry tests also pass. Browser checks verify all four forms, editable colors and reset, ongoing transitions, pause/restart, a phone viewport without horizontal overflow, the Canvas fallback and the preserved reference study. The GitHub commit is limited to playground files and design documentation; the research homepage blob is checked unchanged against its parent.
