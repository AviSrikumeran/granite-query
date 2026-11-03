# Granite Query component playground

Published at **https://avisrikumeran.github.io/granite-query/playground/**. This is a separate static page under the existing `docs/` GitHub Pages source. The research homepage and training/export code are not changed.

## Try it

- **Geometry:** let the field animate, move over it to lift nearby cubes, click to pin/release an inspected unit, switch Assemble/Expand, or use Inspect next cube with a keyboard or touchscreen.
- **Training diagram:** watch the sequence, hover/focus/select a stage to pin its explanation, switch BM25/random, use arrow keys/Home/End on stages, and use Play sequence or Replay to continue.
- **Evidence:** reads `../status.json`, refreshes every 60 seconds while visible, filters events, and opens event details. Try sidebar states provides explicitly labeled loading, empty, failed-refresh, and stale samples. Refresh returns to published data.
- **Motion:** Pause motion freezes the autonomous scene and pointer response. Static preview immediately removes motion. The operating system's reduced-motion preference initializes Static preview. Stage and event selection continue to work. Offscreen scenes and hidden tabs rest automatically.

The diagrams are illustrative. No control starts training, inference, provider API calls, or data writes. The sidebar is a published snapshot, not live Modal telemetry. Neutral review styling is temporary and does not approve a final palette.

## Files and local preview

`index.html`, `playground.css`, `playground.js`, and `data.mjs` are buildless; no external runtime, fonts, libraries, keys, or build step are required. Paths work below `/granite-query/playground/`. The only network request made by the component code is the existing public snapshot.

From the repository root:

```sh
python -m http.server 8765 --bind 127.0.0.1
```

Open `/docs/playground/`. For a realistic project-subpath preview, map `/granite-query/` to `docs/` in a local static server. Verify every relative URL under that prefix before publishing.

Data adapter checks:

```sh
node --test design/playground-data.test.mjs
node --check docs/playground/playground.js
```

Source inspiration and review decisions remain in [the component study](../../design/COMPONENT_STUDY.md). Artwork and component code in this playground are original. Reference screenshots are not shipped on the playground.
