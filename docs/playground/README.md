# Modal reference rendering study

Live: https://avisrikumeran.github.io/granite-query/playground/

The active playground follows the supplied Modal recording's four formations. This pass changes illumination, glyph treatment, reveal and the three peripheral views. The accepted geometry, camera response, responsive layout, research homepage and earlier Modal study are preserved.

## Explore

- The sequence is **Box → Separated plates → Small cubes → Stairs**, about five seconds per form.
- Move the mouse to turn the field. All peripheral views sample the same completed frame. Clicking the field does not advance the sequence.
- Pause freezes motion. Selecting a form while paused displays it immediately.
- Restart reveal replays the sparse outline, center-out ignition and brief increase in brightness.
- Hue controls remain for later review; Reset hue restores reference green.
- Escape pauses. Reduced motion starts fully visible and paused. Hidden/offscreen rendering stops. Touch drags scroll normally.

## Rendering

The renderer now separates scene illumination, glyph sampling and compositing:

1. Key and fill lights, smoothed edge normals and contact occlusion shade the accepted box geometry.
2. Sixteen green-to-citron tiers determine glyph color and most glyph choices. Limited stable variation keeps faces readable.
3. Three camera-projected offsets sample the finished image. They share its glyphs, mouse pose, reveal and transition; a radial fade produces partial peripheral views.
4. Six highlight bloom levels and smooth brightness rolloff connect bright marks without outlining every cell.

This corrects the earlier assumption that the side views were differently scaled and axis-reflected geometry. Inspecting Modal's public renderer showed a compositing method instead. The implementation here is independently written; no downloaded bundle, source shader, captured illustration or recording is shipped.

The formations and placement remain approximations accepted in the earlier pass. Keeping them unchanged means the overall scene is not a pixel-identical Modal reconstruction. Our analytic edge shading also differs from its rounded distance-field renderer.

## Source files and review

- granite/geometry.mjs: unchanged accepted formations, layout, timeline and camera response. Its older material/reflection helpers are retained for the preserved baseline tests; the active renderer uses material.mjs.
- granite/material.mjs: current lighting, tier palette, reveal and projected offsets.
- granite/renderer.mjs: WebGL scene, compositing, bloom and a simpler Canvas fallback.
- granite/field.js: atlas, animation lifecycle, pointer input and review controls.
- granite/study.css: unchanged presentation.

No build step, paid service or runtime package is required. Serve docs over HTTP. Relative module URLs work under the GitHub Pages repository subpath.

For reproducible visual review use /playground/?form=box&at=4 (or layers, cubes, stairs). Adding &intro samples the startup at the chosen time. These URLs start paused. The ordinary URL still plays automatically. /playground/?renderer=canvas selects the simpler fallback, which shares formations and projected fragments but uses approximate glow.

~~~powershell
node --test design/granite-material.test.mjs design/granite-geometry.test.mjs design/modal-geometry.test.mjs
~~~

The earlier comparison remains at [modal-study.html](https://avisrikumeran.github.io/granite-query/playground/modal-study.html). Earlier component experiments remain at components.html. See design/GRANITE_MOTION_VARIATION.md for evidence and remaining differences.
