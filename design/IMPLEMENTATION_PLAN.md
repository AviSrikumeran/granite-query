# Enterprise-quality GitHub Pages implementation plan

3 November 2026. Proposed plan; no palette or typography selection and no production redesign in this commit.

## 1. Product and presentation contract

Granite Query studies whether verified teacher-data selection improves Granite mathematical reasoning more efficiently than random selection. A reader should quickly understand the research question, the current stage, what evidence exists, and what is still uncertain. Enterprise-quality presentation means consistent construction, readable technical content, truthful states, reproducibility links, and working interaction. Styling cannot establish enterprise operational readiness.

The old `VISUAL_RESEARCH.md` is historical and superseded as design direction. Start the component review from [this study](COMPONENT_STUDY.md), with all proposed choices awaiting user feedback.

## 2. Proposed information order

1. Project identity, plain research question, latest-snapshot timestamp, links to evidence and methodology.
2. One bounded explanatory diagram: teacher → verification → selection → Granite fine-tuning → evaluation, including rejection and random-control branches.
3. Evidence: results with split, sample count, selection method, seed/budget context, and limitations. “Not measured” remains explicit when appropriate.
4. Experiment explorer: approved run summaries and details.
5. Research journal, methods, reproducibility, and source repository.

The evidence rail can accompany the main column on wide screens. On small screens it becomes an in-flow status block. The precise layout, fonts, colors, spacing tokens, and final graphic remain review decisions.

## 3. Component boundaries

| Component | Reference | Responsibility | Proposed integration |
| --- | --- | --- | --- |
| SignatureGeometry | F1 or M1 | Original geometric vocabulary; autonomous + bounded pointer response | Choose one after review; must not carry factual status |
| ResearchPipeline | M2, T2 | Explain stages, branches, verification and random control | HTML controls + SVG; static description always available |
| MethodTabs | T1 | Switch a small set of methods and their implementation status | One selected ID controls text, diagram and example |
| ExamplePair | F2 | Recorded question/verification or future evaluated response comparison | Curated public-safe fixture data; label recorded/illustrative |
| EvidenceRail | L1 | Stage, latest event, snapshot age, evidence links | Existing public status/journal sources |
| ExperimentExplorer | L2 | Run list with selected detail and evidence context | New approved export fields only when provided by research pipeline |
| MotionControls | L2 source patterns | Pause/replay and reduced-motion/static behavior | Shared motion state for the isolated component area |

Naming above is a proposed source organization, not new consumer-facing jargon. Native HTML/CSS/ES modules are sufficient for the first implementation. Do not migrate the current static page to React merely to reproduce these patterns. Motion's JavaScript core is an optional dependency to evaluate, not a required stack choice.

## 4. Motion specification to prototype early

These timings and limits are proposed starting values, not measurements of reference sites.

### Autonomous behavior

- A diagram sequence runs over roughly 8–12 seconds with a short rest. Highlight one relationship at a time. Use an “Illustration” or “How it works” label rather than a live-status badge.
- Provide visible Pause and Replay controls. The diagram and explanation remain intelligible at any paused frame. Do not autoplay changes to long text that a user is reading.
- Suspend the animation when the component is offscreen or the document is hidden. Reduced-motion preference starts in a static state with manual step selection. Do not continuously announce decorative updates to assistive technology.
- Data refresh is separate: actual statuses change only on a newer valid snapshot. A paused illustration never pauses or fabricates research events.

### Mouse, keyboard, and touch behavior

- A bounded geometric field may react to pointer proximity or use up to roughly 3 degrees of tilt. Pointer movement must never reposition body text or controls. Reset on leave. Enable spatial movement only for fine pointers and when reduced motion is off.
- Meaningful stages are actual buttons. Hover/focus emphasizes the stage; click, Enter/Space, or tap pins its explanation. No essential information exists only on hover.
- Tabs support arrow keys, Home/End, a selected state, and a visible focus ring. Pointer interaction must not reset the user's selected method or run.
- Initial control transitions: approximately 120–200ms; diagram stage transitions: approximately 250–400ms. Begin with transform/opacity or a small number of SVG updates; avoid repeated layout reads/writes per pointer event.
- Use one requestAnimationFrame loop for a pointer-driven field when necessary; stop it when idle, offscreen, hidden, or disabled. Interpolate toward a target rather than update every glyph on every raw pointer event.

### State model

Keep `selectedStage`, `selectedMethod`, `selectedRun`, `motionPaused`, `reducedMotion`, `isVisible`, `snapshot`, and `fetchState` distinct. The illustration's playhead has no authority over snapshot data. A user's explicit selection pauses any automatic illustration stepping until they resume it. Clean up timers, animation frames, and listeners when a specimen is unmounted or disabled.

## 5. Existing data and Pages integration

The current repo publishes `docs/` from `main` through GitHub Pages. `docs/index.html` is a static dashboard that polls `status.json` every 60 seconds. The current public data includes `stage`, `next_action`, `generated_at_utc`, `metrics`, `caveat`, `events`, and optional `training_progress`. This snapshot is asynchronously published; it is not a direct connection to Modal.

1. Keep the existing publishing/export process and file contract during the visual work. Add a small front-end data adapter that validates required types and treats optional fields as optional.
2. Reuse `status.json` for public status and events; do not fetch private Modal logs or provider APIs from the page. A future live inference demonstration needs a separate authenticated/rate-limited backend with server-held credentials; GitHub Pages does not execute that backend.
3. Show timestamp, snapshot age, loading, empty, stale, and failed-refresh states. Preserve the last valid snapshot on a failed fetch, mark it stale as appropriate, and expose Retry. Never leave “live” indicators moving indefinitely without fresh data.
4. Stage-specific progress can lag the overall stage. If `training_progress.stage` differs from `stage`, display it with its own stage label as the last reported substage or omit the percentage. Do not present stale ranked-arm steps as random-arm progress. A stage change does not authorize changing the research exporter in this visual task.
5. An experiment-results table needs approved fields beyond the initial teacher counters. Define an optional versioned export only with the research workstream: run ID, method, model revision, split, n, seed, token budget, metric value, cost provenance, timestamps, artifact links, and limitations. Render missing fields as unavailable. Do not derive held-out accuracy from teacher-verification counts.
6. Use relative asset/data URLs or resolve against the page/module URL so the project subpath `/granite-query/` works. Test direct navigation, refresh, anchor links, and asset loading under that subpath, not only at a server root.
7. Keep this study and source screenshots in `design/` outside the deployed `docs/` tree. Third-party captures remain research references. Production SVGs and component code must be original or intentionally licensed and attributed.

## 6. Proposed implementation layout

```text
design/                         # This study, feedback, source references
docs/
  index.html                    # Existing dashboard; replace only in redesign phase
  assets/
    site.css                    # Shared typography, layout, and interaction rules
    app.js                      # Page composition and status refresh
    data.js                     # Snapshot validation and display adapter
    motion.js                   # Shared pause/reduced-motion/visibility policy
    components/
      research-pipeline.js
      method-tabs.js
      evidence-rail.js
      experiment-explorer.js
  lab/
    components.html             # Isolated review specimens before integration
  status.json                   # Existing published export; preserve contract
  journal.md
```

This tree is a future proposal, not a statement that these files exist. The lab should contain a static specimen, an autonomous version, and an interactive version of each shortlisted component, using neutral temporary styling until visual decisions are made. Specimens must be labeled as demos and must not trigger training or paid inference.

## 7. Delivery sequence and review artifacts

| Phase | Output | Completion condition |
| --- | --- | --- |
| A — Reference capture | This study and the eight attributed images | Screenshots inspectable in chat and GitHub; source versus inferred behavior distinguished |
| B — Preference decisions | Component IDs with Keep / Adapt / Pass and written reasons | User feedback recorded; no palette inferred from a reference's brand |
| C — Motion specimens | Pipeline + one geometric field + evidence rail; controls and static fallbacks | Review the movement in a browser; record desktop/mobile states, pause/replay, keyboard and pointer behavior |
| D — Visual system | Typography, spacing, borders, shapes, palette, component state matrix | Explicit review of complete components, including error/empty/stale states |
| E — Pages integration | Real data adapter, readable evidence/explorer, responsive composition | All links/assets work under project subpath; data freshness and research limitations remain clear |
| F — Release | Focused GitHub diff, preview captures and verification record | Compare against the agreed component choices and quality checks; publish using existing Pages workflow |

The next implementation phase starts with functional motion specimens, not a polished generic homepage. Build the animation and interaction structure early so reduced motion, keyboard use, loading, and performance are part of the architecture.

## 8. Acceptance checks for an enterprise-quality result

- Consistent spacing, alignment, border treatment, icon vocabulary, and control states; one dominant explanatory visual in a section.
- Readable body text and diagrams at desktop and mobile widths; no full-page horizontal overflow. Code can scroll inside its own panel.
- Test keyboard navigation, visible focus, pause/replay, reduced motion, touch/click equivalents, 200% zoom, and contrast. Target WCAG AA contrast: 4.5:1 normal text, 3:1 large text and applicable control boundaries.
- Test 390px, 768px, and 1440px viewports plus short laptop height. Do not hide core evidence on mobile. No scroll hijacking or default cursor replacement.
- Measure the production page with Lighthouse and browser performance tools. Initial targets: LCP ≤2.5s, CLS ≤0.1, INP ≤200ms when real-user data exists. Lab results are not field performance claims. Avoid a new 3D runtime unless a measured specimen justifies it.
- First read and evidence navigation work without motion. Provide a meaningful static explanation when JavaScript fails; JavaScript-dependent data areas show an honest unavailable state.
- Verify loading/empty/failure/stale/success cases with representative snapshot fixtures; check method/run selection survives refresh. A new event does not steal focus or rebuild unrelated controls.
- Every numerical research claim links to context: split, count, method, budget, and limitations. Pending work stays labeled pending; failed and unchanged outcomes remain visible.
- “Enterprise-ready” presentation never adds invented certifications, customer logos, testimonials, benchmarks, uptime, or simulated live telemetry.
- A release review includes the actual GitHub diff, static and motion captures, and any unresolved limitations. Existing training work and unrelated local files stay outside the design change.

## 9. Later comparison catalogue

In the later chat requested by the user, create a separate visual catalogue of generic or unfinished website patterns to cross-check against. Use side-by-side examples, concrete failure modes, and corrective alternatives. Do not classify a color, library, rounded card, gradient, or AI assistance alone as evidence of poor quality. Evaluate hierarchy, repetition, relevance, state completeness, accessibility, data honesty, and finish. No such catalogue is created in this change.

## 10. Research evidence

- [Captured component study](COMPONENT_STUDY.md), with source sites and exact Langfuse source links.
- [Langfuse feature-tab implementation](https://github.com/langfuse/langfuse-docs/blob/1f3ea78b75515191f873939d4563472eec27e1d7/components/home/feature-tabs/FeatureTabs.tsx): useful state and interaction reference; our visible pause and mobile policies remain explicit requirements.
- [Motion official GitHub repository](https://github.com/motiondivision/motion): an optional implementation tool, not a visual direction or evidence that the reference sites use it.

No X/Reddit opinion review or conversion study was performed. Add social findings only with direct links and a separation between opinion, observed behavior, and measured evidence.
