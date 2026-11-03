# Rendering refinement of the Modal reference study

This pass addresses the user's criticism that recognizable shapes were still rendered with inaccurate shading, weak ignition and crude peripheral duplicates. The accepted main geometry and layout remain unchanged. The research homepage and preserved Modal comparison are outside the publishing scope.

## Evidence and corrected interpretation

Reference evidence is the user's 45.4-second modal hero.mov recording, supplied November 3, 2026; extracted frames at five, ten, fifteen and twenty seconds; and the public modules loaded by [Modal's homepage](https://modal.com/) on the same date.

The previous reconstruction guessed that the peripheral fragments came from mirrored 3D geometry with independent scales and directional fades. That was incorrect. The inspected renderer samples the completed glyph scene at camera-projected neighboring offsets, with luminance tinting, radial attenuation and foreground coverage. Its default peripheral sampling is translated rather than reflected. Changing the view changes those projected offsets too.

The public implementation also separates scene lighting, a sixteen-tier color/glyph treatment, startup glyph scale and flash, scene bloom and highlight rolloff. Those architectural observations informed an independently written implementation. Downloaded bundles and literal source shaders remain local and are not published.

## Preserved constraints

The geometry module and stylesheet are byte-for-byte unchanged from the accepted playground baseline. That preserves:

- Twelve-beam box, three separated plates, eight small cubes and five stair sections, in that order.
- Main object scale, screen placement, sampling pitch and responsive breakpoints.
- Five-second cycle with the accepted brief reshape.
- Damped mouse yaw/pitch, pause, selector and reduced-motion behavior.
- Page copy, navigation, controls and homepage.

The latest user feedback specifically requests better shading and reveal. Those material changes apply to the primary view too; its geometry and placement do not change.

## Active renderer

The drawing pipeline is **lit surface → color and glyph tiers → completed scene → peripheral samples → bloom and composite**.

### Illumination and glyphs

Static key and fill lights give different faces different brightness. A softened normal near an existing edge provides a bevel-like light gradient without changing its silhouette. Four distance probes estimate contact occlusion, replacing the previous all-or-nothing ray shadow.

The previous travelling sinusoidal light band and independent random brightness multiplier are removed from the active renderer. Sixteen dark-green through yellow-green material tiers carry the shading. Brightness influences glyph family, with limited stable variation. Small marks include branching junctions, asterisks, corner marks and filled/split hexagons. Square stamps and hollow rings no longer dominate lit faces.

A restrained moving haze adds soft energy behind the field. It does not change geometry. Bloom extracts highlights into six progressively smaller targets, spreads them back across the field, and applies smooth highlight compression at compositing. Framebuffers are recreated on resize and released first.

### Peripheral views

Three lattice neighbors are projected through the inverse of the current camera turn. At neutral pose the offsets, in the unchanged illustration unit, are approximately:

| View | Horizontal | Vertical |
| --- | ---: | ---: |
| Left | -3.464 | 0 |
| Upper right | 1.732 | -3 |
| Lower right | 1.732 | 3 |

Unlike the old implementation, each peripheral sample uses the actual completed scene texture. It therefore inherits the same glyph identities, brightness tiers, highlight surge, geometry interpolation and startup in the same frame. No separate side-view clock, shading pass, aspect squeeze or mirrored-box scene is needed.

A shared radial falloff, pale luminance tint, glyph coverage and field boundary fade leave fragments around the main object. Empty space remains important. The lower-right fragment is visible where it reaches the permitted field, with its outer portion fading away.

### Reveal and transition

Startup keeps sparse muted marks, then reveals cells outward from the center with a small stable timing offset per cell. Each glyph scales in place and briefly exceeds settled brightness while becoming visible. The bright front blooms into surrounding space, instead of adding an equal halo to every glyph.

During the accepted short form change, the highlight surge acts mainly on already-bright material. Peripheral views inherit that surge and reshape automatically from the same texture. Geometry timing is unchanged.

## Review URLs and fallback

For repeatable snapshots, /playground/?form=box&at=4 starts paused at a chosen clock value. Valid forms are box, layers, cubes and stairs. Adding &intro keeps the startup active at that sampled time. Default navigation still starts automatic playback.

The Canvas fallback shades the same accepted geometry, draws the same glyph tiers and projects three fragments from the same frame. Its contact shading and blur are simpler; it is not a claim of WebGL image parity.

## Verification and limits

Six new material tests exercise projected neighbor positions and camera response, monotonic peripheral attenuation, startup brightness/scale, face illumination, contact occlusion and bounded hue adaptation. Seventeen existing geometry/baseline tests remain. These numerical tests verify mechanics, not visual fidelity.

Visual review compares all four forms with recording extracts at corresponding scale, plus startup samples, pointer response, a narrow viewport, runtime logs and the Canvas fallback. Recording mouse pose varies; neutral snapshots are not exact camera matches.

Remaining differences are explicit: accepted geometry proportions and sharp analytic silhouettes differ from Modal's rounded distance-field geometry; atlas marks are independently drawn rather than extracted; energy and bloom are approximated. The comparison is intended to expose these differences, not certify an exact reproduction.

Publishing is limited to the playground entry version, active field/material/renderer, this documentation and the new material tests. Before publishing, every unrelated blob, including docs/index.html and the earlier Modal study, is checked against the latest remote parent. Recording extracts, comparison captures, downloaded scripts and local baselines are not committed.

## Accepted baseline and original direction

The user accepted the rendering after the lighting pass. The remaining cube adjustment adds 0.08 illustration units of radial clearance between the large box and each peripheral view, approximately one glyph pitch on desktop. It moves the surrounding views rather than changing the main cube. Clearance blends with the existing form transition and returns to zero for the other three formations. Both renderers use the same offsets.

The next design work should retain this accepted study as a visual benchmark and develop an original variant separately. The renderer, smooth shading, selective flashes, empty space and gentle mouse response are reusable infrastructure. The formation sequence, glyph vocabulary and interaction should express Granite Query's own research.

A proposed first sequence is **many example blocks → a selected connected group → a compact interlocking cube**. This is a visual metaphor for selecting verified training examples, not a display of measured research results. Compare three distinct silhouettes in the same temporary monochrome treatment: interlocking blocks, connected proof branches and nested open frames. Judge their readability at small size, lighting and transitions before choosing a color direction. Avoid the rejected spiral and ambiguous rounded forms.

Once a silhouette is selected, draw a coherent set of small mathematical and provenance marks, then explore a mouse response that reveals connections or highlights a selected group. Test each change against the accepted study for brightness, quiet space, smoothness, pointer response and mobile clarity. This proposal does not change the active shapes or introduce a new brand palette.
