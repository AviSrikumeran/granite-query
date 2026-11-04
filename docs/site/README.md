# Granite Query public research site

The owner authorized the complete site refresh on 4 November 2026. The name is a text wordmark only. The magenta artwork is an original visual study, not a logo or model telemetry. Existing playgrounds, raw research feeds, training code and exporters are preserved.

## Content and presentation

- `../index.html` and `site.css`: the main narrative, measured results, method, limitations and dated accounting.
- `data.js`: protocol-aware adapters for three separately evaluated studies. It validates cohort identity, denominators, completion, paired arithmetic and source echoes. Missing metrics remain unknown; unknown study versions fail closed.
- `app.js`: one fetch per evidence file on load, plus the reader's explicit Reload evidence action. There is no homepage polling, model request or experiment control.
- `hero.js`: the accepted interlocking renderer adapted into an original magenta opening. See `HERO.md` for geometry, material and controls. Pause, keyboard view controls, reduced motion, hidden/offscreen handling and cleanup are built in.
- `../research/index.html`, `library.js`, `catalogue.json`: a metadata-driven research library. Reports use their original published Markdown; JSON evidence and existing HTML pages retain direct links.
- `markdown.js`: dependency-free, escaped Markdown rendering, including safe images and source-relative links. It does not execute source HTML. The original source remains visible if a document cannot load. Reload report explicitly revalidates a session-cached document.
- `research.css`: the common reading shell for the five retained research pages. Their existing research content, IDs and scripts are preserved. The historical dashboard is labeled an archive; its older saved-file polling remains separate from the new homepage.

The latest completed result is the local correction study, published at 09:25 UTC on 4 November. It is distinct from the earlier matched 200-question and token-matched 64-question studies. The eight taught mistakes becoming correct is seen-example fitting, not an established gain on separate questions. OPEN inference diagnostics remain separate from adapter training.

## Add research without rebuilding the layout

Add a record to `catalogue.json` with a unique `id`, `title`, `category`, `description`, `path`, `mode` and `source`. `mode: markdown` opens a report in the reader. Other records link to their original destination. Relative paths are rooted at the public documentation directory. The library derives its search, collections and counts from these records.

A new experiment protocol needs a reviewed adapter in `data.js`; do not silently pool a new cohort into an existing chart. Editorial claims and dated report excerpts also need review when the scientific conclusion changes. The page deliberately does not infer a global live-job status from old status snapshots or convert null results into zero.

## Checks

```text
node --test docs/site/data.test.mjs docs/site/markdown.test.mjs
node --check docs/site/app.js
node --check docs/site/library.js
node --check docs/site/hero.js
```

Render the homepage, library and five existing research routes at desktop and narrow widths. Check study/partition separation, explicit row selection, chart/record/JSON identity, original report navigation, source figures, report reload, mobile navigation and the artwork's controls. The full review is in `design/reviews/2026-11-04-site-remake.md` at the repository root.

Publish only the explicit site/research/design paths from a fresh GitHub main tree with a non-force expected-head update. Never include the shared workspace wholesale. Screenshots live in the design chat's artifact directory, rather than research data or model artifacts.
