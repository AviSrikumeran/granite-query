# Granite Query light and form playground

Live: https://avisrikumeran.github.io/granite-query/playground/

An isolated study of depth shading, detailed glyphs, sparse startup, brief highlight-led reshaping and gentle mouse rotation. The current motion pass uses the user's mouse-only Modal recording as its reference. Green is temporary. The research homepage stays unchanged.

## Explore

- Move the mouse across the hero to gently turn the main form and all three faint repetitions. Forms change automatically; no clicking is needed.
- Clicking the field does not advance the form.
- Choose **Play sequence**, **Nested squares**, **Stepped blocks**, **Stacked slabs** or **Rounded tiers** for review.
- **Pause / Resume** freezes or resumes the clock and pointer response. Escape pauses. A paused form selection displays it immediately.
- **Restart reveal** resets pointer influence and replays the sparse outline followed by central ignition. It starts playback unless reduced motion is requested.
- The **Hue** swatch and hex field derive shadow, midtone and highlight colors from one base. Invalid input does not reach the renderer. **Reset hue** restores #78E865.
- Reduced motion starts fully visible and paused. Touch drags scroll normally. Hidden and offscreen fields stop scheduling frames.

Each form occupies a five-second cycle. Bright areas flare first, then a short 200 ms reshaping window connects the geometry. The recording contains these in-between frames, correcting the prior hard-cut interpretation. Travelling surface illumination continues while the mouse is stationary. The camera scale stays fixed.

## Reference studies

The preserved Modal reconstruction and captured comparison remain at [modal-study.html](https://avisrikumeran.github.io/granite-query/playground/modal-study.html). The earlier cube, training diagram and evidence sidebar remain at components.html. Their files and reference captures are unchanged.

## Implementation

- granite/geometry.mjs: geometry, ray intersections, brief reshape timeline, startup reveal, pointer limits and travelling surface light.
- granite/field.js: WebGL glyph field, coordinated repetitions, independent pointer and automatic clocks, palette controls, scheduling and Canvas fallback.
- granite/study.css: page composition and responsive layout.
- modal/: preserved Modal reconstruction.
- comparison.js and comparison.css: preserved comparison shell.

No paid service, runtime package or build step is needed. Serve docs over HTTP; relative URLs also work beneath the GitHub Pages repository subpath. Use /playground/?renderer=canvas to review the simpler renderer.

~~~powershell
node --test design/granite-geometry.test.mjs design/modal-geometry.test.mjs
~~~

See design/GRANITE_MOTION_VARIATION.md for timestamped recording observations, review decisions, chosen settings and limits. The recording and extraction artifacts remain local.
