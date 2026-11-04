# Interlocking reveal

An isolated Granite Query prototype: two original keyed mineral pieces and one electric magenta core. One large view, three rigid moving groups, no brand artwork or external assets. The homepage and all earlier studies are protected.

Open `/playground/interlocking-reveal/` for automatic playback. Use `?progress=0`, `?progress=.37` or `?progress=.61` for held Joined, Unlocked and Revealed poses. The `progress` query covers the entire select/unlock/reveal/return loop, including its return. `?renderer=canvas&progress=.61` forces the simplified fallback.

Move the pointer to tilt the sculpture. Focus it and use arrow keys; Home recenters. Pause, Replay, pose buttons and the native range control work without a pointer. Escape pauses. Reduced-motion preference starts with a static revealed pose; Play is an explicit opt-in. Hidden and offscreen views stop scheduling frames.

## Construction

- `forms.mjs`: two keyed bracket profiles, one core, movement phases and framing. Each bracket is the rigid union of touching axis-aligned volumes. The .08-wide notched joint is negative space rather than an extra object. Edit `LEFT` and `RIGHT` for profiles, `offsets` for travel and `PERIOD` for cycle duration.
- `study.mjs`: one bounded render clock, eased pointer pose, review queries, controls, visibility and context recovery.
- `engine/`: independent copy of the existing editable glyph renderer. The established magenta ramp, mineral shading, ambient occlusion, startup reveal and six-level bloom are retained. No runtime dependency on another specimen.
- `study.css`: responsive single-view presentation and compact controls.

The core first clears the rear key, then rises slightly. It returns before the pieces close. The return uses smooth quintic easing and a small positive separation settle to avoid interpenetration. This is a choreographed visual metaphor, not a physics simulation or live model activity.

Run `node --test design/interlocking-reveal.test.mjs` from the repository root. The test samples rigid grouping, cross-piece clearance, phase order, loop continuity, pointer-extreme framing and material preservation.

See [the review](../../../design/reviews/2026-11-03-interlocking-reveal.md) and [all experiments](../experiments/).
