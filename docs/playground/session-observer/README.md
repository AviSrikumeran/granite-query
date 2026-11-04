# Session observer

4 November 2026, America/Chicago. Original buildless authored-browser-replay study. Intended route `/playground/session-observer/`.

A large mock browser viewport stays synchronized to five stable event IDs and a frame strip. Selecting an event changes the document, exact target, replay cursor and Input / Visible change / Outcome detail together. The initial frame is still and readable. The route moves from an illustrative finding through its source passage and scope to a qualified note.

This is authored HTML, not a recording, live browser session, real automation, provider telemetry or actual model job. The UI labels that boundary persistently. It contains no measured research scores, verified receipts, brand assets or private reasoning. No browser/provider call is made.

## References and boundaries

Two public sources were inspected on 4 November 2026:

1. [Browserbase official homepage](https://www.browserbase.com/). Root rendered a dominant pixel/dither mountain hero, use-case tabs Research / Extract / Fill & submit / Testing / Browser agent, and platform lists including Observability / Identity. A session-replay UI did not appear in the inspected homepage AX content. Root retained a reference capture. The mock viewport/event trail here is an original adaptation, not exact current-homepage parity; the official guide below supplies the concrete session/live-view relationship.
2. [Browserbase official research-agent guide](https://docs.browserbase.com/integrations/vercel/quickstart). The guide links a session ID to a live debug-view URL and streams status, live-view and finding events. This supports retaining an action/session identity next to the visible browser state. Its real API execution is not used in this demo.

No Browserbase source, code sample, illustration, logo, screenshot, font or exact composition was copied. Public documentation and marketing pages are references, not an asset-reuse license; no reuse permission is assumed. The editorial document, frame content, event model, cursor treatment and layout are original. The authored replay is our adaptation, not a claim of matching the reference's live behavior or conversion performance.

## Controls

- Select an event in the trail or frame strip. The document page, highlight, cursor and detail retain its stable event ID. Hover never changes selection.
- Up/Down or Left/Right select a neighboring event/frame. Home/End choose the first/last. Previous/Next and the integer frame scrubber provide the same choices.
- Buttons inside the mock document follow the authored reading route: open the source, inspect scope, read the qualified note or revisit a reference. They only select saved demo frames.
- Replay 5 frames starts a finite guided presentation: each frame is held for three seconds, then replay stops on the fifth. Pause replay, Escape or any manual frame selection stops it.
- Hidden or offscreen views stop replay; it does not resume by itself. Reduced-motion CSS removes cursor/highlight transitions, and enabling the preference stops an active replay. The initial view never autoplays.
- Held review URLs use `?frame=0` through `?frame=4`.

## Implementation and checks

`index.html`, `style.css`, `model.mjs` and `observer.mjs` are the complete buildless implementation. No dependencies or external assets are required. Frame addresses are visible illustrative labels, not network destinations.

The target ring is measured against the current document element after selection and viewport resizing. The cursor is constrained inside the viewport. Source-page events E–02 and E–03 share the same authored page but highlight different targets, preserving the document context.

Passed syntax checks: `node --check docs/playground/session-observer/model.mjs` and `node --check docs/playground/session-observer/observer.mjs`.

Passed model checks verify unique event IDs, target elements belonging to their assigned page, valid authored navigation edges, bounded frame inputs and finite non-looping playback order. Root browser QA: large viewport composition, desktop/narrow overflow and target bounds, every event/frame/document link, synchronized state/detail, keyboard focus, scrubber, replay/pause/end behavior, reduced-motion/offscreen handling and console.

Recommendation: **Adapt, owner review pending**. Selecting an event has a concrete visible consequence. Its presentation quality and document density still need visual judgment. Homepage, accepted studies, shared catalogue/registry, training and publishing remain outside this subtask.

## Focused rendered correction

Root's narrow screenshot caught the target ring while its geometry was interpolating from the source title to the quotation. Target geometry now snaps to the selected element immediately; the replay cursor retains its optional travel. The narrow paper uses its document height with a 460 px minimum rather than a fixed 620 px field, and source text explicitly wraps inside its grid track. All five frame targets belong to their corresponding authored page; content-sized narrow paper keeps source/scope actions in the document flow. Desktop sizing is preserved.

The replay's live status also now announces its actual final or paused event. Automatic completion reports E–05 and a Completed state rather than leaving the earlier E–01 announcement. Root should recheck all five target rectangles after refresh, plus the narrow source and scope actions.


## Root rendered review / 4 November

Desktop and 390 x 844 review completed. Screenshot artifacts: `session-observer-desktop.png` and `session-observer-mobile.png` in the design chat overnight artifact directory. The [batch04 review](../../../design/reviews/2026-11-04-overnight-batch-04.md) records exact interactions, fixture limits and corrections. Provisional **Adapt**, owner acceptance pending. Reduced-motion handlers were inspected in source; no OS preference override was performed.

## Playback visibility correction

A resize/reentry race could leave the control showing Playing while an old offscreen flag prevented its timer from starting. Scheduling now reads the observer's current viewport intersection directly. If the document is hidden or the view is offscreen, it immediately returns to paused state; an observer callback can repair an active timer gap without reviving a paused replay. Offscreen reentry alone never resumes playback. A synthetic event/timer regression passed: stale offscreen state followed by visible explicit Play advances through E–05; offscreen stops; reentry stays paused; hidden Play leaves no dormant Playing state. Syntax check passed.
