# Granite Query public research site

The owner authorized the complete site refresh on 4 November 2026. The name is a text wordmark only. The magenta artwork is an original visual study, not a logo or model telemetry. Existing playgrounds, raw research feeds, training code and exporters are preserved.

## Content and presentation

- `../index.html`, `home.css` and `home.js`: a short public introduction using the original Electric Magenta block, one qualified finding and three reading routes. No specimen toolbar or research dashboard is mounted on the homepage.
- `../results/index.html` and `site.css`: the detailed measured comparisons, method, limitations and dated accounting, moved off the homepage at the owner's request.
- `data.js`: protocol-aware adapters for three separately evaluated studies. It validates cohort identity, denominators, completion, paired arithmetic and source echoes. Missing metrics remain unknown; unknown study versions fail closed.
- `app.js`: one fetch per evidence file on the Results page, plus the reader's explicit Reload evidence action. Asset, evidence and report links resolve from the public documentation root. The homepage loads no research feeds.
- `hero.js`: the exact earlier Electric Magenta interlocking block, with its unchanged material, pose cycle and renderer. See `HERO.md`. There are no visible testing controls; reduced motion, keyboard input, hidden/offscreen handling and cleanup remain built in.
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

Render the homepage, Results page, library and retained research routes at desktop and narrow widths. Check study/partition separation, explicit row selection, chart/record/JSON identity, original report navigation, source figures, report reload, mobile navigation and the artwork's pointer/keyboard response. Old homepage result, method and cost anchors route to their section on Results. The original integration review is in `design/reviews/2026-11-04-site-remake.md`; the owner's correction and simplified composition are in `design/reviews/2026-11-04-home-simplification.md`.

Publish only the explicit site/research/design paths from a fresh GitHub main tree with a non-force expected-head update. Never include the shared workspace wholesale. Screenshots live in the design chat's artifact directory, rather than research data or model artifacts.
