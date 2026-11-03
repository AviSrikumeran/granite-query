# Modal reference reconstruction playground

Live: https://avisrikumeran.github.io/granite-query/playground/

The active playground now follows the supplied Modal recording's forms, order, compact scale, empty space and reflected fragments. Custom forms have been removed. The research homepage is unchanged.

## Explore

- The live sequence runs **Box → Separated plates → Small cubes → Stairs**, about five seconds per form.
- Move the mouse to gently turn the main form and its reflected views. No clicking is required, and clicking the field does not advance it.
- Use the selector to inspect a form. **Pause / Resume** freezes or resumes the clock. A paused selection displays the complete form immediately.
- **Restart reveal** replays the sparse outline hold and center-out ignition.
- The reference base is **#7FEE64**. The hue control remains available for later review; Reset hue restores the reference green.
- Reduced motion starts fully visible and paused. Escape pauses. Touch drags scroll. Hidden and offscreen fields stop scheduling frames.

The main object is approximately a quarter of the desktop content width. Glyph size and spacing scale with it. The reflected views reverse different scene axes, reveal different faces, fade directionally, and disappear behind the foreground volume. They show fragments rather than three full, uniformly scaled duplicates.

## Preserved studies

The earlier Modal reconstruction and captured comparison remain at [modal-study.html](https://avisrikumeran.github.io/granite-query/playground/modal-study.html). Earlier cube, training diagram and evidence sidebar experiments remain at components.html. Their source and captured references are unchanged.

## Implementation

- granite/geometry.mjs: the four reference formations, reflected-view parameters, compact responsive layout, ray sampling and recorded-style timeline.
- granite/field.js: live glyph atlas, reflected geometry, foreground occlusion, material, mouse response and Canvas fallback.
- granite/study.css: centered composition and responsive presentation.
- modal/: preserved earlier comparison renderer.

There is no paid service, runtime package or build step. Serve docs over HTTP; relative URLs work beneath the GitHub Pages repository subpath. Use /playground/?renderer=canvas to inspect the fallback.

~~~powershell
node --test design/granite-geometry.test.mjs design/modal-geometry.test.mjs
~~~

See design/GRANITE_MOTION_VARIATION.md for the recording observations, reflection construction, current parameters and verification. The recording and local extracts are not published.
