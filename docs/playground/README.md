# Modal hero playground

Live: https://avisrikumeran.github.io/granite-query/playground/

This isolated reference study compares Modal’s captured homepage hero with an independently implemented live reconstruction. The research homepage at `docs/index.html` is outside this change.

## Review controls

- **Side by side:** captured reference on the left, live reconstruction on the right, matched to a 1280 × 900 desktop viewport and scaled to fit.
- **Reconstruction:** a larger live view that responds to available width.
- **Phone:** a 390 px iframe viewport (375 px content width with its desktop scrollbar) to inspect responsive behavior.
- **Pause / Resume:** stop or resume motion. System reduced-motion preference starts paused. Escape also pauses the field.
- **Reset field:** restart the animation and clear pointer/pulse state.
- Move the pointer through the live field to displace/light symbols; click for an expanding pulse. Touch scrolling remains available.
- Open **Full size** for the standalone study.

The earlier cube, training diagram and evidence sidebar remain at `components.html`. Their CSS, JavaScript and evidence source are unchanged.

## Implementation

No build, paid API, Lovable credits, npm install or external JavaScript dependency is required. `comparison.js` manages review modes and same-origin iframe messages. `modal/field.js` renders a vector-drawn glyph atlas using WebGL points over projected geometry. It uses Canvas 2D when WebGL is unavailable. To check that fallback directly, open `modal/hero.html?renderer=canvas`.

Serve the `docs` directory over HTTP and visit `/playground/` (or mount it at the repository’s `/granite-query/` Pages path). All local assets use relative URLs.

## Reference and limitations

Original: https://modal.com/ — captured November 3, 2026. Modal’s mark, wordmark, headline and copy are used only in this clearly labeled reference study. This is independent and not affiliated with Modal. Source links go to Modal’s actual site.

The original uses ABC Diatype and a Three.js-rendered field. The reconstruction uses Arial and a new renderer. Composition and measured spacing follow the reference; typography, individual glyph arrangements, lighting and motion are approximations. The left pane is a static capture, not a live video.

See `design/MODAL_HERO_RECONSTRUCTION.md` for measurements, derivation and validation. This playground is a comparison artifact, not the proposed Granite Query brand or homepage.
