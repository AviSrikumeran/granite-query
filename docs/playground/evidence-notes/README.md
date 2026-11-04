# Evidence in the margins

4 November 2026, America/Chicago. An original, buildless editorial component study for Granite Query. It explores whether an evidence link can remain attached to its exact sentence, with a calmer reading view one action away.

Live path after publication: `/playground/evidence-notes/`.

## Public reference and boundary

Inspected the official [Liveblocks example catalogue](https://liveblocks.io/examples) and its [Text Editor Comments example](https://liveblocks.io/examples/text-editor-comments/nextjs-comments-tiptap) on 4 November. The component page explicitly describes contextual comments in a collaborative editor using Liveblocks, Tiptap and Next.js, and links its implementation. This establishes the contextual-annotation pattern, not exact animation timing or a screenshot match. Rendered pointer behavior still requires root browser observation.

The [public repository](https://github.com/liveblocks/liveblocks) is mixed-license. Its [LICENSE](https://github.com/liveblocks/liveblocks/blob/main/LICENSE) says most code is Apache-2.0; `packages/liveblocks-server` and `tools/liveblocks-cli` are AGPL-3.0-or-later, with each package declaring its applicable license. The official text-editor example page labels its example Apache License 2.0. No Liveblocks source, SDK, branding, screenshot or asset is copied or imported here. This study uses original HTML, CSS, JavaScript and fixture content.

## Observation versus adaptation

Observed: a public product example specifically couples document editing with contextual comments and provides a source-code route.

Adapted here: comments become research source notes. A numbered, underlined sentence and its margin note share an ID. The selected note expands; the exact passage highlights and a fine connector marks the relationship. Selecting a note returns to its passage. A raw-record disclosure makes the same note inspectable as JSON. Reading view removes the annotation layer without changing the prose.

Warm paper, an editorial type hierarchy, magenta ink accents, numbering, the read/inspect split and connector placement are our design choices. They are not asserted to reproduce Liveblocks' CSS or motion. There is no collaboration or simulated online presence.

## Content and behavior

`records.json` contains four **illustrative interface fixtures** about presenting evidence. It reports no Granite model experiment, numeric result or positive outcome. The page says this above the document and at its end. In production, a validated public research contract would populate the claim/source identities; these fixtures must not be relabeled as measured evidence.

- Hover, keyboard focus or click a highlighted sentence to expand its matching note.
- On a narrow screen, clicking a sentence moves to its note below the document. Selecting a note returns to the sentence.
- Arrow keys, Home and End navigate the marked sentences. Previous/Next source buttons provide another route.
- Show record reveals the selected fixture JSON. Example file opens the actual local fixture file.
- Reading view disables the annotation controls and hides the margin. With evidence restores it.

There is no autoplay, background timer, canvas loop or provider request. Only direct-input color transitions run, and reduced-motion disables them. Line positions update on interaction and layout changes. A failed fixture load leaves the document readable and declares the notes unavailable instead of fabricating records.

## Files and verification

`index.html` is the semantic editorial document; `notes.css` owns its responsive layout; `notes.mjs` binds the claims to `records.json`, builds source notes and positions the connector. No dependencies or build step.

Completed: `node --check docs/playground/evidence-notes/notes.mjs`; JSON parse/integrity check for four distinct fixture IDs and explicit illustrative states. No files outside this study folder were edited.

Root browser QA before publication:

1. Desktop: verify paper, margin, underlines and connector align without overlap. Hover/focus claims 1–4; confirm only the corresponding note expands.
2. Click a source note; verify its passage scrolls into view. Try Next source and arrow/Home/End keys.
3. Reveal a record and confirm the JSON/Example file route; inspect note positioning after expanded content changes.
4. Toggle Reading view and back; document stays complete, annotations restore.
5. At roughly 390 px wide, verify no horizontal overflow, notes stack below, and sentence/note round trips work.
6. Confirm reduced-motion layout and direct interactions remain usable; record a rendered screenshot. Exact visual fidelity to the reference is not claimed.

Provisional recommendation: **Adapt**. The shared claim/source identity is directly useful for a research site and addresses the earlier confusion about what a visual object represents. Final typography, integration with actual public evidence and owner acceptance remain open.

## Root rendered review

Desktop and 390 × 844 browser inspection completed on 4 November. No document horizontal overflow was observed. The principal selections, view/record controls and applicable replay/pause controls worked; screenshots are retained with the overnight design chat. Reduced-motion and offscreen handlers were inspected in source rather than tested through an OS preference change. See the [batch review](../../../design/reviews/2026-11-04-overnight-batch-01.md). Owner acceptance remains pending.
