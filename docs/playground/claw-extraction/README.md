# Branch claw extraction

Live: https://avisrikumeran.github.io/granite-query/playground/claw-extraction/

Proof branches reshape into a three-jaw claw, descend through the cleared shell, grip the magenta core and pull it out. The previous extraction runs beside it. The original core-extraction folder, other studies and homepage remain unchanged.

## Compare and inspect

The ordinary link plays automatically. Five stage buttons hold Branches, Clear, Reach, Grip and Lifted. The Sequence slider pauses and scrubs the forward action. Pause, Play and Replay reveal control the shared clock. Both panels use the same world scale, camera and magenta light ramp; the previous sequence is sampled at matching normalized progress, so its timing is stretched to the new sequence in this comparison only.

Review links start paused:

- `?progress=0`: original branch nodes above the closed shell.
- `?progress=.32`: formed, open claw and cleared shell.
- `?progress=.55`: fingers around the core, still open.
- `?progress=.69`: closed grip before lifting.
- `?progress=1`: claw and core lifted together.
- `?progress=1&renderer=canvas`: simplified fallback.

Mouse movement turns linked views; uncheck Link mouse views for independent inspection. Arrow keys turn a focused figure; Home resets it and Escape pauses. Touch scrolling remains native. Reduced motion starts at the held final pose with automatic pointer movement disabled. Hidden pages and offscreen views stop scheduling animation.

## Editable construction

The source proof-branch graph has ten joints and nine edges. Its node positions are scaled and turned over above the shell, then interpolated into a claw with three jaws and five contact pads. The links follow their endpoints as oriented boxes. The initial branch graph uses straight links for articulation, rather than the original axis-by-axis routes.

The shell opens before approach begins. Fingers reach the core before closing. Lifting begins only after the grip closes. The core and all claw joints share the same displacement during the pull, and the pads meet the core faces without drifting. The core stays compact while held; release and network expansion are later studies.

The scene contains 33 active parts within 40 slots. `forms.mjs` owns the sequence and contact poses. Local reference snapshots preserve the source branch graph and previous extraction. The isolated engine supports oriented glyph tracing, face normals and contact shading in WebGL and Canvas. The claw is subdued relative to the bright core. The Canvas fallback has fewer glyphs, simpler glow and coarser material blending.

The forward action takes 12 seconds, holds until 14.5 seconds, then reverses continuously to an 18-second loop. This is a deterministic visual mechanism, not a rigid-body simulation. All code is local and editable; no video, new dependency or paid service is added.

Run `node --test design/claw-extraction.test.mjs` from the repository root. See [the review](../../../design/reviews/2026-11-03-claw-extraction.md) for captures, checks and remaining design questions.
