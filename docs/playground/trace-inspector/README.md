# Trace inspector

4 November 2026, America/Chicago. Original, buildless hierarchy/detail interface study. Intended route: `/playground/trace-inspector/`.

One authored research packet contains eleven records and three illustrative source documents. The opening selection is **Research packet → Interpretation note → Uncertainty note**. The interface makes the selected record's identity, parent, children and attached source visible before any additional interaction.

The tree represents saved-document relationships. It is not a model's private reasoning, a chronological execution trace, live training telemetry or a claim of measured model performance. All content is labeled illustrative. No network/model calls, scores, verified hashes or actual run receipts are invented.

## Reference, observation and adaptation

At most two reference sources were used:

1. [Langfuse current homepage](https://langfuse.com/), inspected through public web content on 4 November 2026. The root agent rendered an Observability / Metrics / Prompt Management / Evaluation / Annotations / Playground demo with auto-advance and Escape-to-pause. Its Observability panel is an image described as nested observations with latency/cost. Root selected Observability, paused it and retained a capture. This supports nested inspection and explicit context; no exact interactive-tree pointer behavior is claimed. These are product-presentation observations; exact animation timing and hover behavior were not captured here.
2. [langfuse/langfuse-docs](https://github.com/langfuse/langfuse-docs), inspected as the matching public website repository. Its README identifies it as the `langfuse.com` repository, built with Fumadocs and Next.js App Router; its repository license is MIT. A particular landing component was not copied or claimed as the source of this study.

All implementation, content, icons and layout here are original. The adaptation is a dense light workspace, stable record selection, context-preserving search, a hierarchical navigator and synchronized Input / Output / Source inspection. No Langfuse logos, screenshots, website assets, code or exact composition were reused. This study explores an interaction principle, not visual parity or conversion performance.

## Interaction

- Click/tap a tree row or use Up/Down to move through visible records. Selection updates the breadcrumb, input, statement, source and parent/child references.
- Click a branch chevron or use Right/Left to open/close branches. Right enters an open child; Left can return to a parent. Home/End select the first/last visible row.
- Search by label, type, code or content. Type filtering can isolate Sources, Checks, Qualifications, References or Findings. Matching descendants retain their ancestor context.
- Filtering or collapsing does not silently change the selected record. If it leaves the visible tree, a message offers Show in tree, which restores its path.
- Overview / Input / Output / Source keep the same selected identity. Tab views support Left/Right and Home/End.
- Breadcrumbs, parent references and child buttons navigate explicit relationships. Read source opens exact authored excerpts for that record.
- `/` focuses search; Escape in search clears filters. No autonomous motion is present. Reduced-motion CSS disables future incidental animation/transition.
- A held review URL can select any valid ID, for example `?record=cohort` or `?record=receipt`.

## Files and verification

- `model.mjs`: authored records/source excerpts; ancestry, matching and visible-row derivation.
- `inspector.mjs`: stable selection, tree navigation, filter context, details and accessible tabs.
- `index.html`: responsive workspace, semantic controls and persistent illustrative labels.
- `style.css`: precise light material, dense aligned type, restrained magenta selection and responsive hierarchy/detail layout.

Passed syntax checks: `node --check docs/playground/trace-inspector/model.mjs` and `node --check docs/playground/trace-inspector/inspector.mjs`.

Passed model checks verify parent/source integrity, cycle-free complete ancestry, matching descendants retaining context, collapsed visibility and the no-match state. Root owns rendered browser QA: desktop/narrow overflow, tree/search/filter controls, collapse/selection stability, keyboard tree/tab navigation, exact source matching, focus visibility, console and screenshot.

Recommendation: **Adapt pending review**. The dense inspector supplies clear identity and context, but density, contrast and narrow-screen navigation still need visual judgment. Homepage, accepted studies, catalogue, registry, training and publishing are outside this implementation scope.

## Root rendered review

Desktop and 390 × 844 inspection completed on 4 November. Primary controls, selection/context relationships and narrow layouts passed the checks in the [batch02 review](../../../design/reviews/2026-11-04-overnight-batch-02.md). No document horizontal overflow or preview console warning/error was observed. Reduced-motion and hidden/offscreen handlers were inspected in code rather than through an OS preference override. Owner acceptance remains pending.
