# Granite Query light and form playground

Live: https://avisrikumeran.github.io/granite-query/playground/

An isolated study of depth shading, detailed glyphs, startup reveal, highlight-led shape switches and coordinated mouse rotation. Green is temporary for reference comparison. The research homepage is unchanged.

## Explore

- Move across the hero to turn the main form and all three faint repetitions in yaw and pitch. Click the field to advance.
- Choose **Play sequence**, **Nested squares**, **Stepped blocks**, **Stacked slabs** or **Rounded tiers**.
- **Pause / Resume** freezes or resumes the clock and pointer response. Escape pauses. Selecting a form while paused displays it immediately.
- **Restart reveal** clears pointer influence and replays startup from nested squares. It starts playback unless reduced motion is requested.
- The **Hue** swatch and hex field derive shadows, midtones and highlights from one color. Invalid input does not reach the renderer. **Reset hue** restores #78E865.
- Reduced-motion preference starts fully visible and paused. Touch drags scroll normally. Hidden and offscreen fields stop scheduling frames.

The automatic sequence holds for 4.8 seconds, then briefly flares bright areas and switches directly to the next intact geometry. There is no travelling disassembly or interpolated shape. Rounded tiers use actual analytic cylinder surfaces rather than a chain of boxes.

## Reference studies

The preserved Modal reconstruction and captured comparison remain at [modal-study.html](https://avisrikumeran.github.io/granite-query/playground/modal-study.html). The earlier cube, training diagram and evidence sidebar remain at components.html. Their rendering files and reference evidence are unchanged.

## Implementation

- granite/geometry.mjs: scene geometry, analytic cylinder and box sampling, reveal thresholds, highlight flares and direct-switch timeline.
- granite/field.js: shaded glyph field, three coordinated repetitions, smooth pointer response, palette controls, scheduling and Canvas fallback.
- granite/study.css: page composition and responsive layout.
- modal/: preserved Modal reconstruction.
- comparison.js and comparison.css: preserved comparison shell.

No paid service, runtime package or build step is needed. Serve docs over HTTP; relative URLs also work beneath the GitHub Pages repository subpath. Use /playground/?renderer=canvas to review the simpler renderer.

Run the current and preserved geometry suites:

~~~powershell
node --test design/granite-geometry.test.mjs design/modal-geometry.test.mjs
~~~

See design/GRANITE_MOTION_VARIATION.md for the review decisions, material model, chosen timings, extraction limits and validation.
