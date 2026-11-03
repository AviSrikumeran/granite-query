# Granite Query color and motion playground

Live: https://avisrikumeran.github.io/granite-query/playground/

An original blue-and-pink variation of the dense glyph-field technique, with a folded loop, nested frames, weave and double helix. This isolated playground does not replace the research homepage.

## Explore

- Move the pointer through the field to turn and light the structure; click to advance.
- Choose **Play sequence** or pin a form. A playing selection eases from the displayed geometry. A paused selection displays the selected form immediately.
- **Pause / Resume** freezes or resumes simulation. Escape pauses. System reduced-motion preference starts paused.
- **Restart** returns to the beginning and clears pointer influence. It preserves pause state and selected colors.
- Use the **Blue** and **Pink** swatches or their hex fields to recolor the field and accents. Invalid hex input does not reach the renderer. **Reset colors** restores #81D9FA and #FF79BD.

The default color direction is light blue and a brighter rose pink on deep navy. It is a working variation, not a finished project-wide brand palette.

## Reference studies

The green Modal reconstruction and captured-state comparison remain at [modal-study.html](https://avisrikumeran.github.io/granite-query/playground/modal-study.html). The earlier cube, training diagram and evidence-sidebar studies remain at `components.html`. Their original rendering and evidence files are unchanged.

## Implementation

- `granite/geometry.mjs`: sixteen oriented solids per form, quaternion interpolation, a continuous 22.4-second sequence, and the fallback ray test.
- `granite/field.js`: dense stable glyphs, blue/pink material shading, mouse interaction, live palette controls, pause/visibility handling and Canvas fallback.
- `granite/study.css`: independent page composition, typography and responsive layout.
- `modal/`: the preserved independent Modal reconstruction.
- `comparison.js` and `comparison.css`: the preserved Modal comparison shell.

The new renderer is isolated so changes to the variation do not alter the reference study. It reuses the authored glyph-atlas and dense sampling approach, while adding oriented geometry, new forms, new material colors and project-specific composition. There is no paid service, runtime package or build step. Serve `docs` over HTTP; relative paths work beneath the GitHub Pages repository subpath. Force the simpler renderer with `/playground/?renderer=canvas`.

Run both geometry suites with:

```powershell
node --test design/granite-geometry.test.mjs design/modal-geometry.test.mjs
```

See `design/GRANITE_MOTION_VARIATION.md` for color choices, construction and validation. The original extraction evidence remains under `design/extracts/modal-2026-11-03`; it describes Modal and is not the new palette’s source of authority.
