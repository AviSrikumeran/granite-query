# Magenta core extraction

Live: https://avisrikumeran.github.io/granite-query/playground/core-extraction/

An isolated comparison between the current magenta interlocking blocks and an original mineral-shell extraction. The left reference stays assembled. On the right, a dark shell identifies a core through its seams, clears its lid and one side, then lifts eight luminous modules through the opening.

## Controls

The normal link plays automatically. Pause and Replay reveal control the clock. Closed, Selected, Open and Extracted hold key poses. The Sequence slider pauses and scrubs the complete forward action. Play resumes from the held progress. The 12-second motion loop includes an eight-second forward sequence, a two-second hold and a two-second return; the initial ignition precedes it.

Mouse movement turns both views. Uncheck Link mouse views to inspect one. Arrow keys turn a focused figure; Home resets it, and Escape pauses. Touch scrolling remains native. Reduced motion starts with the extracted pose held and suppresses automatic pointer rotation. Play is an explicit opt-in. Hidden pages and views outside the viewport stop scheduling animation.

Review links start paused and skip ignition:

- `?progress=0`: closed housing.
- `?progress=.22`: selected core, shell still closed.
- `?progress=.52`: cleared opening before extraction.
- `?progress=1`: released core.
- `?progress=1&renderer=canvas`: simplified fallback.

## Construction

The local engine and `baseline.mjs` are independent snapshots of the material study. No accepted study module is imported at runtime. The baseline keeps the exact clear-joint interlocking geometry and magenta ramp. Each view uses the same world scale; the candidate occupies more space as the shell opens.

`forms.mjs` defines six shell sections and eight stable core modules. Translation and easing are deterministic functions of normalized progress. The opening is fully clear before lifting starts. The final core is above the remaining housing. Part dimensions remain fixed, and a small final increase in core spacing exposes the modules.

The isolated renderer adds a material value to each center uniform, so the shell can use mineral tones while the core uses the existing magenta light tiers and bloom. Lighting, glyph vocabulary, face shading and pointer easing come from the previous material study. The Canvas fallback has approximate glow and switches material during selection instead of continuously blending it.

No framework, generated video, external asset or paid service is used. The housing is an editable geometric placeholder, not the final Granite Query logo. The gripper, fracture detail and evidence branches are deliberately deferred to subsequent questions.

Run `node --test design/core-extraction.test.mjs` from the repository root. See [the review](../../../design/reviews/2026-11-03-core-extraction.md) for verification and remaining differences.
