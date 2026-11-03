# Component playground verification

3 November 2026. Isolated release at `/granite-query/playground/`; not a homepage redesign.

## Scope

Added the buildless HTML/CSS/JavaScript playground under `docs/playground/`, plus a pure public-snapshot adapter and its Node tests. No runtime dependencies, training calls, API keys, or third-party artwork are included. The only component fetch is the existing public `../status.json`.

## Checks performed

- `node --check docs/playground/playground.js` passes.
- `node --test design/playground-data.test.mjs`: six tests pass. These cover invalid snapshots, inconsistent counts, event validation/order/deduplication, older responses, failure/resolution filtering, and publication age.
- Browser preview served with the actual `/granite-query/` project prefix. Page, stylesheet, JavaScript module, data module, and snapshot loaded successfully in the browser.
- Desktop pointer movement changes the cube field and inspected unit. Click pins a unit; Assemble/Expand changes arrangement. Inspect next cube works without hovering.
- Stage selection pauses the explanatory sequence. Arrow-key navigation moves focus and selection; Random control changes the selected method and its explanation. Replay resumes the walkthrough.
- Sidebar loading, empty, failed-refresh, and stale samples display explicit sample labels. Empty samples show no invented metrics. Failed refresh retains real cached data. Returning to Published data restores the actual record.
- Event filtering and detail inspection work. The selected event and filter remain selected after Refresh.
- Static preview stops both scene and sequence motion while preserving selection controls. The operating system reduced-motion preference is wired to initialize this mode; OS-level preference switching was not separately emulated.
- Responsive views checked at 390×844, 768×1024, and 1440×1000; no page-level horizontal overflow. Mobile pipeline becomes vertical and evidence moves into document flow. The cube viewBox adapts to keep the artwork legible.
- Browser error/warning log was empty during local verification.

## Publication checks

Publish only `docs/playground/*`, `design/playground-data.test.mjs`, and this verification note. Construct the commit on the latest remote `main` tree and verify that `docs/index.html` retains its existing blob SHA in the final tree. Existing research status files and publishing/training code are outside this change. Retain the latest remote tree if the parallel research workstream publishes while this change is prepared.

Remote homepage blob at the beginning of this task: `d03c6f91254c375bd0d1603828fd2b89ce94e8b4`. Publication preserves the latest remote homepage blob, rather than uploading any untracked local homepage copy from the shared workspace.

## Limits

This is a working component review with temporary neutral styling. It is not a complete accessibility audit, field-performance study, or approval of a final visual system. No Lighthouse score, conversion improvement, or production model readiness is claimed. The sidebar's freshness reflects snapshot publication time, not a direct Modal stream. Continuous motion and method illustration never alter the research record.
