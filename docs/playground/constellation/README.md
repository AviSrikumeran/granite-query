# Evidence constellation

An isolated, deliberately more expressive motion experiment. Eight evidence tiles and a modular core move through Archive, Scatter, Trace and Resolve. The homepage and previous studies remain unchanged.

Open `/playground/constellation/` for a paused, organized evidence map: three source records at the top, five checks in the middle and the conclusion at the bottom. The question, observed result and numbered key appear before the map. Play animation explicitly starts the sequence; Read the map restores the organized view. Animation options contains the held scenes, restart and range control. Expand diagram enlarges the artwork; Escape exits and pauses it. Drag a tile to pull it from the field, then release it to spring back. Moving through empty space turns the sculpture and gently displaces nearby records.

Select a tile to isolate its evidence route. Select the core or a scene button to restore the complete field. The record picker provides the same evidence on narrow screens and by keyboard. Focus a tile and use arrows to nudge it; Home and Reset position clear displacement. Reduced motion starts in the same static conclusion pose, disables pointer-follow movement and uses direct positioning. Play explicitly opts into the sequence.

Held reviews: `?pose=archive`, `?pose=scatter`, `?pose=trace` and `?pose=resolve`. `?progress=0..1` holds any cycle position. Add `&renderer=canvas` to inspect the simplified renderer. Normal catalogue entry has no held query.

## Construction

- `forms.mjs`: 32 active oriented volumes in 40 fixed slots, quaternion interpolation, responsive spatial layouts, ancestry selection, cubic connections, projected hulls and the damped release spring.
- `studio.mjs`: bounded render clock, pointer/drag/keyboard controls, pause and held scenes, SVG filaments and travel marks, projected button positions, full-canvas state and public evidence loading.
- `engine/`: independent copy of the established glyph renderer. The magenta ramp, shading and bloom remain. The inherited vignette is widened for the larger spatial field.
- `data.mjs`: independent unchanged copy of the validated public study contract. The scene fetches the public human-reference aggregate on load and explicit refresh. Missing or unsupported evidence stays unavailable; there is no example-score fallback.

The curves are SVG over the glyph scene. Projected hull masks hide the curves behind the solid surfaces, and their control points follow the displaced records. The sculpture is a choreographed visual metaphor, not a physics simulation, provider activity indicator or model's private reasoning.

Pause stops autonomous motion; input and release remain responsive. Hidden/offscreen views stop scheduling frames. No new framework, external asset, paid service or provider call was added.

Run `node --test design/constellation.test.mjs` from the repository root. See the [clarity review](../../../design/reviews/2026-11-03-constellation-clarity.md), [initial review](../../../design/reviews/2026-11-03-constellation.md), [feedback registry](../../../design/experiments.json), [branch baseline](../results-branches/) and [All experiments](../experiments/).

## Owner feedback and revision

On 3 November the owner found the kinetic presentation confusing. The opening view now prioritizes the research question and result, uses plain source/check labels and stays still. Selection explains the tile and links to its record detail. These changes are a response to feedback; their clarity still needs the owner's review. The sculpture remains a presentation of existing records, not a running query or model reasoning.
