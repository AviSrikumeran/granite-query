# Record switcher

4 November 2026, America/Chicago. Separate original interface study for the overnight Granite Query design lab. The implementation edits only this directory.

Question: can one research record change between readable prose, a protocol contract and JSON without losing its identity or selected field?

Live destination: [Record switcher](https://avisrikumeran.github.io/granite-query/playground/record-switcher/). This comparison stays separate from the homepage and all earlier studies. Root rendered verification is recorded in the batch review below.

## Public references and boundaries

- [Resend homepage](https://resend.com/), inspected 4 November 2026. The public Integrate section offers language choices and code; another section pairs a specific API interaction with a response. These are concrete demonstrations, not decoration without context.
- [Resend Node SDK](https://github.com/resend/resend-node), inspected the same day. Its README demonstrates input and response usage and identifies an MIT license. It is an SDK repository, not the homepage source. Its license does not establish the homepage's asset or code license.

The root's rendered reference inspection also confirmed that choosing Python changes the code, Node.js has nested framework tabs, and the React Email demonstration pairs file selection with preview controls. A source screenshot was saved by the root. The external Send demonstration was not used.

The adaptation is original: a consistent record ID, linked field selection and three reading modes. The pale editorial view, dark JSON view, field ribbon and 230ms user-triggered transition are our implementation decisions. Exact Resend geometry and transition timing remain inferred. No logos, website assets, snippets, fonts or framework code were copied. No dependencies or services were added.

## Content and behavior

`record.mjs` contains one visibly authored fixture. It has no accuracy number, measured outcome, generated answer or provider execution. All three representations read that same object. The question, finding, source labels and limitations retain their selected state when changing views. The JSON representation is an exact serialized version of the record; syntax and line numbers remain intact while field blocks are selected.

The initial view is static. Tabs and field controls work by mouse, tap and keyboard; Left/Right/Home/End move between tabs, and Up/Down/Home/End move through fields. Selecting content in a representation also updates the field ribbon. There is no automatic sequence to pause. User-triggered transitions finish in 230ms, respect reduced motion and cancel when the document is hidden or the representation leaves the viewport. The actual-research link points to the separate real results study; the toy record does not pretend to be that study.

## Files and checks

- `index.html`: immediate explanation, stable ID, accessible tabs/panel, field rail and provenance notes.
- `record.mjs`: single fixture, field definitions, exact JSON grouping.
- `studio.mjs`: representations, persistent selection, roving tab focus and finite transitions.
- `studio.css`: editorial/code treatments, selected-field continuity, responsive rail and contained JSON horizontal scrolling.
- `verify.mjs`: record/field completeness, exact JSON roundtrip, line numbering and field-group ownership checks.

Run `node --check docs/playground/record-switcher/studio.mjs`, `node --check docs/playground/record-switcher/record.mjs` and `node docs/playground/record-switcher/verify.mjs`.

Root browser QA before publication: inspect desktop and ~390px layouts; select Sources then Readable → Protocol → JSON and verify the same selection/value; select a content block directly; test tab and field arrow keys; verify no document overflow while long JSON lines scroll inside their panel; verify reduced motion and console errors; save a screenshot.

Provisional recommendation: **Adapt**. The same record can serve different audiences while keeping caveats and identity visible. This is a design judgment, not a usability measurement or owner acceptance. It deliberately explores representation continuity rather than repeating source extraction or a moving glyph field.

## Root rendered review

Desktop and 390 × 844 inspection completed on 4 November. Primary controls, selection/context relationships and narrow layouts passed the checks in the [batch02 review](../../../design/reviews/2026-11-04-overnight-batch-02.md). No document horizontal overflow or preview console warning/error was observed. Reduced-motion and hidden/offscreen handlers were inspected in code rather than through an OS preference override. Owner acceptance remains pending.
