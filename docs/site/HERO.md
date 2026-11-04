# Reusable magenta hero artwork

4 November 2026. `hero.js` mounts one original interlocking mineral form, with its shell and core both carrying the selected electric-magenta material. It depicts no logo, model activity, metric or research result.

## Integration

```js
import {initHero} from './site/hero.js';
const artwork = initHero(document.querySelector('.hero-art'));
// When removing/replacing the page or its artwork:
artwork.destroy();
```

The container should have a dark `#0d0a12` backdrop and a minimum height, normally at least 450 px desktop / 330 px mobile. Taller art columns (roughly 500–560 px) give the broad form more room beside a desktop headline. The module appends a scoped absolute-fill root and compact native controls. It preserves existing container content and only supplies relative positioning or a fallback minimum height if needed.

Return API: `destroy()`, `pause()`, `play()`, `resetView()`, `getState()`. Reinitializing the same container destroys the earlier instance first. Optional second argument: `{autoplay:true, intro:false, pixelRatio:1.5, renderer:'auto'}`. `renderer:'canvas'` deliberately selects the existing simplified Canvas 2D path for fallback QA. `intro:true` enables the inherited 1.55-second glyph ignition; the default renders a complete revealed pose immediately.

## Source and material

No external dependency, paid asset, image or framework is added. The component imports the unchanged, already published local modules from `playground/interlocking-reveal/`: its original keyed geometry, renderer, atlas and lighting/material implementation. Those preserve the polished glyph vocabulary, soft normal lighting, ambient occlusion, sixteen material tiers and bloom established in the accepted studies. The imported engine's unused reference formations are not drawn. Only `revealAt`'s original two keyed pieces and one core are used, with peripheral copies disabled.

`HERO_CONFIG` makes the initial pose, slow cycle speed, DPR, frame cap, pointer bounds and material emissions explicit. The shell is substantially more magenta than the earlier gray extraction comparison, while the core carries pink-white peaks. Small inherited selective flares are restrained. Layout is responsive and tested against all reveal stages and pointer extremes.

The inherited renderer uses an opaque dark internal framebuffer. CSS lightening compositing suppresses that base against the specified `#0d0a12` backdrop, and a soft edge mask avoids a rectangular illustration boundary. The wrapper itself is transparent. A materially different or isolated light backdrop would require a different compositing treatment; this module is intended for the stated dark hero.

## Input, motion and lifecycle

- Mouse movement turns the form directly, with no click required. Arrow keys, native Turn left / Turn right controls and Reset provide keyboard/tap equivalents.
- Pause animation / Play animation controls autonomous geometry movement. Space/Enter on the focused artwork toggles movement; Home resets the view; Escape pauses.
- Reduced motion opens on a still revealed pose, disables pointer-follow movement and uses direct positions for explicit view controls. Play is an explicit opt-in. Entering reduced motion later pauses and restores the still pose.
- The slow reveal/return cycle uses the established keyed clearance path. It is decorative choreography, not physics or live training.
- Hidden or offscreen artwork stops scheduling frames and freezes its clock. Paused, settled views also stop scheduling frames; direct input may schedule a short settling sequence.
- Default DPR is 1.5 and always capped at 2. WebGL paints at up to 30 frames per second when active; the simplified Canvas path is throttled further. No perpetual timer runs outside the active artwork.
- Context loss pauses drawing and restoration rebuilds the existing renderer. Canvas 2D is used if WebGL is unavailable. If neither canvas context exists, a plain artwork-unavailable fallback replaces the picture while the page remains readable.
- `destroy()` cancels RAF, disconnects observers, removes all listeners and component DOM, releases the WebGL context/resources, frees the visible canvas backing size and restores container styles owned by this mount.

## Verification and root QA

Completed: `node --check docs/site/hero.js`. An ephemeral Node geometry check imported the actual exported `heroLayout` and `heroScene`, sampling 101 reveal poses at 335×330, 600×450 and 760×560, with both pointer-axis extremes. All 96,960 projected corners were finite and inside artwork/control margins. Scene capacity remained forty slots with ten active volumes, and all active shell emissions stayed magenta-weighted.

Root rendered QA remains necessary: inspect actual shading and edge compositing against the final page backdrop; move the mouse both ways; pause and confirm movement stops while view controls still work; test keyboard, mobile controls, reduced motion, offscreen/hidden pause, context/fallback behavior and cleanup/reinitialization. The worker used no browser UI and changed only `docs/site/hero.js` and this file. Existing studies, homepage and research feeds remain untouched by this subtask.

## Focused material correction after initial homepage QA

Root found the first homepage rendering too uniform across the shell faces. Source inspection explains the risk: the accepted magenta palette boosts and normalizes many middle/high tiers to a peak channel of one, and the initial selected pose raised the shell's magenta blend to 0.82 (base 0.68 plus highlight 0.14). That left only 18% of the darker, more separated mineral tiers in the initial shell.

The correction changes only the shell material weights: base 0.68 → 0.54, selection highlight 0.14 → 0.04. The initial selected shell now mixes 58% magenta with 42% mineral tiers; the joined shell remains 54% magenta. This preserves the bright magenta hue while allowing the existing key/fill/AO lighting to separate dark and light faces. The magenta palette, core emission (1.25), bloom pipeline, glyph density, geometry, framing and motion are unchanged. Pink-white peaks stay concentrated in the core. These are source-based adjustments; root should judge the rendered contrast on the final page.

## Focused visibility and resize correction

Root reproduced a blank paused canvas after viewport/full-page capture changes, followed by a Play button whose render clock stayed stopped. The old cached `inView` flag could block a dirty redraw after the canvas backing size had been cleared.

The correction refreshes actual root geometry and `document.hidden` on scheduling, playback changes, resize and each active tick. IntersectionObserver remains an entry signal rather than the sole authority. Scroll/resize events supply a recovery path when its cached entry is stale. A visible resize and a pause/play action synchronously paint the current pose, and unchanged-size observer notifications no longer clear the canvas or reallocate its framebuffers. Truly offscreen/hidden views still cancel RAF and freeze their clocks; no offscreen polling loop was introduced.

An ephemeral synthetic lifecycle harness executed the actual hero source with only the graphics/DOM edges stubbed. It passed stale false IO → Play recovery, offscreen freeze and reentry without a new IO event, synchronous paused resize repaint, unchanged-size no-clear/no-reallocation, hidden/visible resume and complete destroy. Root should still repeat viewport/full-page capture, Pause/Play and return-to-top in the real browser. No renderer, geometry, color or density code changed in this correction.
