# Modal hero reconstruction study

Reference: https://modal.com/  
Capture and implementation: November 3, 2026  
Scope: isolated GitHub Pages playground; no change to `docs/index.html`.

## What is being reproduced

The study follows the original hero’s actual composition: a restrained navigation bar, centered production-AI statement, a short two-line description, two compact pill buttons and a large, luminous geometric symbol field. It replaces the earlier simplified cube demo as the playground entry point. The earlier studies remain at `docs/playground/components.html`.

The comparison is explicitly labeled: original captured image on the left, independently rendered implementation on the right. There is also a larger reconstruction mode and a phone preview.

## Measured desktop geometry

Reference viewport: 1280 × 900 CSS pixels, with a 1265 px content width after the scrollbar. The browser-exported capture is 1265 × 889 pixels; the comparison scales the capture and a 1280 × 900 live iframe into matching surfaces.

| Element | Reference measurement |
| --- | --- |
| Navigation | 64 px tall; bottom border at y=64; 64 px horizontal inset |
| Logo | approximately 105 × 18 px; left edge x=64 |
| Headline | top y=121; 48 px line height; 45 px ABC Diatype, weight 500; width about 594.6 px |
| Description | top y=193; 18 px type, 24 px line height; two lines |
| Primary and secondary actions | top y=273; height 36 px; gap 8 px; pill radius 48 px |
| Hero surface | #040804 |
| Main text / accent | #e3e5e1 / #7fee64 |
| Description text | #a8aba6 |
| Reference renderer | visible canvas identifies Three.js r180 |

Arial has different metrics. Its desktop headline is adjusted to 46.2 px to approximate the measured width. This does not recreate ABC Diatype exactly.

## How the field is derived

1. Establish a screen-aligned lattice at 7.2 px spacing. At the reference size this produces approximately 18,500 independently shaded glyph positions.
2. Project eight cube vertices into an isometric view and connect their twelve edges. Slow rotation changes depth while preserving the broad silhouette.
3. Measure each lattice position’s distance from those projected edges. Use wider, dimmer lanes around the core and smaller offset geometric echoes around it.
4. Draw eight symbol variants into a local Canvas atlas: disk, hexagon, star, cross, Y, triangle, diamond and a second star. Sample them in a WebGL point pass. Nearby cells share symbol families, with noise breaking up regular blocks.
5. Apply spatial noise, a soft envelope and moving light so the field contains dark gaps and uneven bright ridges. Mix green, teal and yellow light. A separate low-opacity pass adds bloom around bright symbols.
6. Convert pointer coordinates into local canvas coordinates. A local influence moves and lights symbols; clicks create a decaying expanding ring. These interactions belong to this reconstruction and are not claimed to be Modal’s exact interaction logic.
7. Stop frame scheduling when paused, hidden or outside the viewport. Start paused when reduced motion is requested. Keep touch scrolling available. A Canvas 2D fallback provides a simpler field without WebGL.

No Modal application JavaScript or shader source was copied. The mark and wordmark SVGs were taken from the visible reference navigation; the captured hero image remains an unmodified reference asset. Modal’s name, marks and copy are attributed in the page. This artifact is not affiliated with Modal.

## Integration boundary

The live implementation is self-contained under `docs/playground/modal/`. The review shell and its CSS/JavaScript live under `docs/playground/`. Links and assets are relative so GitHub Pages can serve the repository subpath. There are no runtime packages, hosted inference services, paid generation calls or Lovable requirements.

For a future Granite Query design, replace the reference brand and copy, then decide which geometric behavior helps explain the actual research. This study deliberately does not choose a custom palette or claim that the recreated hero alone establishes enterprise readiness.

## Validation

- Browser inspection compared the capture and live rendering side by side, then at larger size; pill shapes, typography, spacing, field brightness and surrounding echoes were refined against the reference.
- WebGL renderer was confirmed in the live iframe. Pause held the simulation time at 0.150 seconds across separate reads; reset while paused returned it to 0.000. Resume advanced time again.
- Native pointer clicks reached the canvas and produced pulse state. The live field supports pointer displacement and illumination.
- Phone preview measured 375 px of content in a 390 px iframe with no horizontal overflow; headline, buttons and navigation remained usable. Mobile navigation was opened and its expanded state confirmed.
- Reduced-motion initialization and hidden/offscreen scheduling were checked in source; an operating-system reduced-motion override was not exercised.
- JavaScript syntax and local asset references are checked before publishing. The published commit is restricted to playground files and this study document; the existing homepage blob is checked unchanged against its parent.

Known visual differences remain: font shapes, exact glyph selection, light distribution and animation choreography. The source is a static frame in the comparison; use the original-site link to compare its current motion directly.
