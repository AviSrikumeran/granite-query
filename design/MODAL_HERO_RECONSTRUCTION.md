# Modal hero: extraction and motion reconstruction

Reference: https://modal.com/  
Study date: November 3, 2026  
Scope: `docs/playground/` and design evidence only. The current research homepage stays unchanged.

## What changed after the first version

The first reconstruction varied lighting over one cube silhouette. It missed the source’s distinct box, separated layers, stairs and small-cube configurations. The revised renderer represents those as actual different geometry at a fixed camera scale and interpolates between them. Sixteen glyph variants replace the first eight. Pointer tilt and local light replace the old radial displacement/pulse; clicking advances the form.

The form selector lets a reviewer pin each configuration and compare it with its captured reference. Automatic playback holds each configuration for 2.6 seconds, then assembles the next over 2.4 seconds. These are reconstruction timings, not recovered source timings.

## Tools checked and used

| Tool | Verified role | What happened in this study |
| --- | --- | --- |
| [DesignLang](https://github.com/Manavarya09/design-extract) | Open-source design-token and motion extractor | Ran npm package 13.3.2 successfully against Modal with runtime motion capture. Generated reference DESIGN.md and tokens are retained in `design/extracts/modal-2026-11-03`. |
| [Pluck](https://www.pluck.so/) | Component captures as prompts, Figma layers or HTML | The official product matches the described capabilities; the spoken “Plug/getPlug.io” name appears to refer to this. No extension installation or credits were needed for this pass. |
| [Picker.design](https://picker.design/pick-element) | Element HTML and original stylesheet extraction | Verified the product documentation. Its [page clone](https://picker.design/clone-page) explicitly strips scripts, so that export alone cannot retain a JavaScript canvas scene. Not installed or purchased. |
| GETANYUI | Exact product identity unconfirmed | No authoritative match was established under that exact name. No claim is made that it was run. |
| DesignExtractor / CopyDesign.ai | Claims supplied in chat | Exact supplied domains were not accessible through web verification. No account, purchase, upload or extraction was performed there. |

DesignLang’s hosted Watch page currently asks for sign-in for the first free run; the local open-source CLI completed without that service. The npm command and extraction limitations are recorded alongside its outputs.

A DESIGN.md is a useful portable convention, not proof that an agent automatically follows it. The extracted file remains reference evidence rather than project-wide instructions. Its heuristic roles and grades need review: the generated “primary” color and aggregate “body” size do not describe the observed hero accurately. No custom Granite Query palette was chosen.

## What extraction recovers

The tool recovered DOM/CSS measurements, colors, typography, radii, transitions and Web Animations observations. The visible source hero identifies Three.js r180 and is not a video or Lottie element. CSS/Web Animations metadata does not expose its canvas scene graph, geometry or GLSL program. JavaScript motion is not necessarily implemented as CSS keyframes.

No Modal application JavaScript or shader source was copied. The scene is independently implemented from captured forms. The original mark/wordmark and hero copy remain attributed reference assets.

## Measured desktop basis

| Element | Source measurement |
| --- | --- |
| Viewport | 1280 × 900 CSS px; 1265 px content width after scrollbar |
| Header | 64 px plus 1 px border; 64 px horizontal inset |
| Headline | y=121; 45 px ABC Diatype, weight 500; 48 px line height; about 594.6 px wide |
| Description | y=193; 18 px / 24 px; two lines |
| Actions | y=273; 36 px high; 8 px gap; 48 px pill radius |
| Background / text / accent | #040804 / #e3e5e1 / #7fee64 |
| Description color | #a8aba6 |
| Navigation easing | 200 ms, cubic-bezier(0.165,0.84,0.44,1), found in extraction |

Arial is adjusted to 46.2 px to approximate the proprietary headline font’s width. It does not reproduce its letterforms.

## Rendering recipe

1. Define twelve beam boxes for the open cage, three thin plates for the layers, five adjacent solid stair sections, and eight small cubes. Pad each formation to twelve slots for interpolation.
2. Interpolate part centers and half-extents with small per-part delays and a single quintic easing. Avoid applying easing twice, which concentrates movement into a short burst in the middle of the transition. Keep the orthographic camera scale fixed. A slow small turn and pointer-dependent turn add depth without zooming.
3. At every position of the staggered 5.6 px glyph lattice, cast a ray through the scene’s cuboids. Shade the closest visible face and its edge margins. Render smaller dim echoes behind and beside the main form.
4. Build a local atlas of sixteen disks, rings, stars, crosses, Y marks, triangles, diamonds, squares and other geometric symbols. Keep symbol identities stable per cell and favor filled marks over hollow outlines. Apply uneven light with lifted midtones and restrained peaks. Draw each glyph and its soft halo in a single pass; use atlas mipmaps, a 1.5–2× backing resolution and softened contour coverage to reduce aliasing.
5. Map pointer movement to bounded tilt and a light response. A click smoothly advances to the next form. Manual selections and interrupted transitions capture the currently displayed geometry as their start, and keep the illumination clock continuous. Ignore touch drags so the page can scroll normally.
6. Keep pause, reset, manual selection, iframe messages, reduced-motion initialization and hidden/offscreen scheduling explicit. The fallback samples the same scene using Canvas 2D.

## Captures and comparison

The deployed comparison uses the earlier box capture and three new field captures (small cubes, stairs, layers). All were captured from Modal on November 3. They remain raster reference assets; the right-hand scene is live. The left uses the same captured header above separate field states to keep static text consistent across captures; it is a composite of captured regions, not a recorded animation or a synchronized source render.

Visual differences remain in glyph arrangement, face brightness, geometric proportions, lighting, font and choreography. Matching four named configurations is a concrete improvement, not a claim of pixel-perfect reproduction or enterprise readiness.

## Validation

Six geometry tests cover distinct bounded formations, a continuous automatic loop, stable manual selection, correct ray intersections, bounded movement per sampled 60 Hz frame, and exact start/end geometry for interrupted morphs. Browser verification checks the actual WebGL renderer, all form selections and reference swaps, pause/reset, pointer/click behavior, the phone view and the Canvas 2D fallback. Publication is restricted to playground/design files, with the homepage blob checked unchanged against the latest parent commit.


## Density and smoothness refinement

The earlier renderer sampled a 7.2 px grid (18,480 positions at the reference size). The revised staggered 5.6 px lattice samples 30,510 positions at a 1265 px content width: approximately 65% more positions. These are potential glyph positions, not a claim that every position is visible or that the source uses that exact count.

The earlier field had relatively sparse midtone coverage and prominent bright wire-like rims. The revised field favors filled glyphs, lifts face midtones, softens silhouette coverage and limits peak opacity. Glyph identities no longer change as animated noise crosses a cluster boundary. This reduces block-like patches and flicker. The single draw pass avoids repeating the scene ray tests separately for glow and glyphs.

Automatic transitions now use 2.4 seconds instead of 1.8 seconds within the same 20-second loop. The double-easing bug was removed. Selector changes and clicks also ease from the displayed scene; a new target can interrupt an in-flight transition without a geometry jump or a lighting-time reset. Paused selections remain immediate for comparison.

Browser validation confirmed the WebGL renderer and 30,510-position lattice, all four paused form selections, a frozen clock, reset to time 0, click-initiated morphing, a mid-transition pause, and retargeting before the previous morph finished. The retargeted form settled correctly while time continued forward. The phone preview measured 375 px of content without horizontal overflow; the Canvas 2D atlas fallback rendered successfully. The original reference images and homepage were not modified by this refinement.

Density, brightness and motion were compared visually against the existing captured states. The source’s exact shader, glyph distribution and timing remain unknown; this remains an independent reconstruction, not a pixel-perfect extraction.
