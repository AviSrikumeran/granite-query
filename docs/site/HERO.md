# Electric magenta homepage artwork

4 November 2026. The owner chose the earlier **Electric magenta** moving block over the extraction sculpture used in the first integrated homepage. The production wrapper now imports that exact study's unchanged geometry, renderer, material and glyph atlas from `playground/purple/`. The named `initHero` API is retained.

## What is shown

The accepted clear-joint interlocking form contains eighteen notched beam volumes. It cycles through **Locked → Open → Offset** on the original 15-second clock: 4.5-second holds and 0.5-second selective-flash transitions. Original magenta tiers, face shading, AO, six-level bloom, brightness rolloff and pointer easing remain in the source renderer. This is the full luminous material, without the mineral blend or extracted core added in the first homepage.

One primary view fills the hero. At the owner's request, the study's existing peripheral shadow/reflection effect is enabled: three dim, cropped projections follow the same frame, transition and pointer angles. This is the renderer's original `ghosts` option, not a new floor-shadow animation. The main geometry, scale, material and layout are unchanged. No green comparison, testing labels or visible Pause/Reset/turn controls are mounted. The code-defined artwork depicts no logo, model activity or research result. Existing playgrounds remain unchanged.

## Mounting and lifecycle

```js
import {initHero} from './site/hero.js';
const artwork = initHero(document.querySelector('#hero-material'));
// If the component is removed:
artwork.destroy();
```

The container supplies its dimensions, typically 600×520 desktop and approximately 350 px high on mobile. The wrapper centers and scales the original silhouette to preserve clearance through every pose and both pointer extremes. An unobtrusive edge mask and lightening composite blend the renderer's opaque near-black plum base into the surrounding dark hero.

Optional settings: `{autoplay:true, intro:false, pixelRatio:1.5, renderer:'auto'}`. The default starts on a fully formed Locked block; `intro:true` enables the original short glyph ignition. `renderer:'canvas'` deliberately selects the accepted simplified fallback for QA. DPR is capped at 2; the default WebGL cap is 30 fps.

Mouse movement turns the block using the original ±0.105 / ±0.065 radian bounds. A focused canvas accepts arrow keys; Home restores the view, Escape pauses, and Space/Enter toggles movement. These inputs have no visible specimen controls. Reduced motion starts on a still fully revealed block, disables pointer-follow and pauses if the preference changes. Explicit keyboard movement remains available.

Hidden and offscreen views cancel animation frames and freeze the clock. Actual viewport geometry is checked on scheduling, playback, resize and each tick; IntersectionObserver is an entry signal rather than the sole source of truth. Pause/play and visible resize repaint synchronously, and unchanged-size callbacks do not clear the canvas. Cleanup cancels RAF, aborts listeners, disconnects observers and releases graphics resources.

Return API remains `destroy()`, `pause()`, `play()`, `resetView()`, `getState()`. It supports integration and QA without adding a control bar to the public page.

## Verification

The module passes `node --check docs/site/hero.js`. An ephemeral Node harness compared 301 returned geometry/state samples with the exact imported study and checked 520,128 projected corners across 600×520, 350×350 and 300×320 artwork sizes, all three poses and both pointer-axis extremes. Every corner was finite and stayed more than 10 px inside the artwork. Root performs browser checks for the integrated page, actual shading, live motion, pointer/keyboard response and responsive layout before publication. No engine or accepted study file is modified.
