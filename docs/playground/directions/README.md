# Three directions for Granite Query

Live: https://avisrikumeran.github.io/granite-query/playground/directions/

An isolated comparison of **interlocking blocks**, **proof branches** and **nested frames**. The accepted playground at /playground/, its source files, and the research homepage remain unchanged. This page adds no navigation or script to those pages.

## Compare

- Three equal columns on desktop; three stacked views on narrow screens.
- The same green material, key/fill lighting, contact shading, glyph atlas, six-level bloom, center-out ignition and selective transition flare in every view.
- One shared clock cycles **Locked → Open → Offset** poses. These are variations within each direction; a panel keeps its own identity.
- Move the mouse over a view to turn all three. Disable **Link mouse views** to inspect one independently.
- **Pause** holds the formation clock and lighting animation. Mouse and keyboard inspection still work.
- Use arrow keys on a focused view to turn it; Home resets its turn. Escape pauses the shared clock.
- Hide **Peripheral views** to compare the central silhouettes without the surrounding samples.
- **Replay reveal** resets all three together. The Pose selector can hold one shared pose.
- Reduced motion starts with completed, paused forms. Play is an explicit opt-in. Offscreen views stop drawing, and a hidden page stops scheduling frames. Touch scrolling is preserved.

These are geometric identity experiments, not a depiction of measured research results. The green remains a temporary common reference treatment.

## Formations

| Direction | Construction |
| --- | --- |
| Interlocking blocks | Six notched beams along three orthogonal axes. Full-depth ends and narrower central bridges leave visible channels. Eighteen solid sections. |
| Proof branches | One root, connected joints and five terminal blocks on different depth planes. Every path is routed continuously in 3D. Leaf placement is checked in the default camera so conclusions remain distinct. |
| Nested frames | Three complete cubic cages at different scales. Smaller frames move within a fixed outer frame, preserving open space. Thirty-six solid sections. |

Every formation has forty stable renderer slots, with unused or zero-length segments skipped. The accepted 200 ms reshape inside a short highlight event is retained. Geometry is interpolated between the same slots, without redistributing unrelated particles.

## Isolation and source

The engine directory is an independent snapshot of the accepted renderer and math from commit 09fa0a764a278c91e4cedddd09220fb7c5aaf0c7. All runtime imports resolve within this folder. Its scene capacity is expanded to forty parts; rays missing the formation skip contact-light probes. The peripheral switch and a small shared clearance are local additions.

- index.html and study.css: comparison layout and controls.
- forms.mjs: the three structures, three poses, interpolation and shared timeline.
- study.mjs: one clock, synchronized input, pause/reveal controls, viewport lifecycle and renderer setup.
- engine/: isolated lighting, glyphs, WebGL compositing and simpler Canvas fallback.

The WebGL drawing scheduler targets approximately forty updates per second, with immediate redraws for controls. The Canvas fallback uses lower sampling density and a lower update rate; its glow is approximate. No framework, external service, runtime dependency or build step is added.

## Reproduce a review

Serve docs over HTTP. Relative paths support the GitHub Pages repository prefix.

- ?at=4: a paused, settled comparison.
- ?at=4&pose=open: inspect a specified pose.
- ?at=1.1&intro: sample the shared ignition.
- ?at=4&ghosts=0: compare just the central structures.
- ?renderer=canvas&at=4: inspect the fallback.

Run the geometry, continuity, projected readability and import-isolation checks with:

~~~powershell
node --test design/directions-geometry.test.mjs
~~~

Visual QA covers all three poses, linked/unlinked mouse input, keyboard inspection while paused, the peripheral switch, shared reveal and playback, desktop columns, narrow-screen scrolling and the fallback. Publishing adds only this directory and its new test file to the freshest remote tree. Every pre-existing blob is preserved, including concurrent research updates.
