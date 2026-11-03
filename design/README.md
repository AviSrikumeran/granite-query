# Granite Query: website design research

Reviewed 3 November 2026. Status: reference review and implementation plan; visual direction pending user feedback.

The goal is a distinctive, enterprise-quality public research website: readable evidence, clear project status, carefully built components, and purposeful motion. This is a presentation-quality goal, not a claim that the model or service is production-ready.

## Start here

- [Component study with eight screenshots](COMPONENT_STUDY.md): what we observed, what is worth studying, reservations, and how each pattern could be built for Granite Query.
- [GitHub Pages implementation plan](IMPLEMENTATION_PLAN.md): component boundaries, data integration, autonomous and pointer interaction, rollout, and acceptance checks.
- [Capture manifest](references/2026-11-03/manifest.json): source URLs, capture date, dimensions, and file hashes.

## Current decisions

| Item | Status |
| --- | --- |
| Prior enterprise/research design direction | Set aside by the user; the old `VISUAL_RESEARCH.md` remains historical and is not design authority |
| Color palette and typography | Undecided; no palette is proposed here |
| Cubes, boxes, modular geometry | Explicit user interest; explore original geometry, not another company's mark |
| Motion that runs on its own | Required candidate; specify pause, offscreen suspension, and reduced-motion states from the start |
| Mouse interaction | Required candidate; pair meaningful actions with focus, keyboard, click/tap equivalents |
| References selected by the assistant | Candidates for review, not user-approved design choices |
| Live dashboard | Preserve while reviewing; no homepage, training, publishing, or telemetry code changed by this study |
| Later visual catalogue of “vibe-coded” patterns | Requested for a later chat; not created in this change |

## Feedback to collect

For each component ID in the study, record Keep / Adapt / Pass, plus the specific quality liked or disliked. Judge geometry, density, movement, and information clarity separately from the reference site's colors. For movement, a still image is only a starting point: the next review needs a working isolated specimen.

No user verdict has been inferred. GitHub source links establish implementation evidence where available; they do not establish conversion performance. Social-platform reactions have not been researched in this pass and should not be presented as consensus. User-supplied X or Reddit links can be appended with the specific claim, context, and whether we agree.

## Capture provenance

These are browser captures of the named public websites, not generated mockups. The original brand treatments belong to their respective owners. They are retained here as attributed design-study references, not assets for the production homepage. All local captures are linked from the component study. Screenshots cannot establish pointer behavior or animation timing; the build recipes are our proposals unless a source inspection is explicitly named.
