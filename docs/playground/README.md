# Modal hero playground

Live: https://avisrikumeran.github.io/granite-query/playground/

An isolated comparison of Modal’s captured hero and an independent live reconstruction. `docs/index.html` is outside this change.

## Review

- **Form:** play the sequence, or pin Box, Layers, Stairs, or Small cubes. Pinning keeps geometry stable while light and pointer motion continue.
- **Side by side:** captured field state on the left and live reconstruction on the right, using the same 1280 × 900 desktop viewport scaled to fit. The left combines one shared captured header with separate static field captures; it is not a video.
- **Reconstruction / Phone:** inspect the larger view or a 390 px iframe.
- **Pause / Resume:** freeze or resume simulation. Reduced-motion preference starts paused; Escape also pauses.
- **Reset field:** return to automatic playback at its first form, clear pointer state and preserve pause status.
- Move the pointer to gently tilt and light the form. Click to advance. Touch scrolling remains available.

Earlier cube, training diagram and evidence-sidebar studies remain at `components.html`, unchanged.

## How it works

`modal/geometry.mjs` defines four configurations of cuboids: twelve beams for the open box, three thin plates, a five-step solid, and eight separated cubes. Part positions and dimensions interpolate at a fixed camera scale. Each five-second segment holds for 3.2 seconds and assembles the next form over 1.8 seconds. These timings are authored approximations.

`modal/field.js` ray-tests those cuboids from a fixed orthographic camera at each glyph position. It shades faces, rims and dim geometric echoes, then draws sixteen locally generated symbol variants with WebGL. The Canvas 2D fallback uses the same scene and ray-box geometry at lower density. Test it at `modal/hero.html?renderer=canvas`.

The renderer stops scheduling while paused, hidden or offscreen. Pointer tilt replaces the previous displacement/ripple effect. There is no global zoom pulse.

No build, paid API, Lovable credits, external runtime package or npm installation is required to run the deployed playground. It uses ES modules, so serve `docs` over HTTP. All local assets are relative for the GitHub Pages repository subpath.

## Extraction and provenance

[DesignLang](https://github.com/Manavarya09/design-extract) 13.3.2 was actually run against Modal. Its generated reference DESIGN.md and tokens are retained under `design/extracts/modal-2026-11-03`. The tool measures DOM/CSS and Web Animations; it does not recover this WebGL hero’s geometry or shader. Geometry and timing remain independently reconstructed from observed box/layer/stair/cube states.

Original: https://modal.com/ — captures November 3, 2026. Modal’s name, marks and copy are included only in this labeled reference study. This is independent and not affiliated with Modal; source links lead to Modal itself. Arial replaces proprietary ABC Diatype. Glyph arrangement, illumination, exact geometry and transition choreography differ from the original.

Validation: `node --test design/modal-geometry.test.mjs`; browser comparisons and interaction checks. See `design/MODAL_HERO_RECONSTRUCTION.md`. This artifact is not a proposed Granite Query brand or homepage.
