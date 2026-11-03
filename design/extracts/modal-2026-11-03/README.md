# Modal extraction evidence

Source: https://modal.com/  
Extractor: [DesignLang](https://github.com/Manavarya09/design-extract), npm package `designlang@13.3.2`  
Captured: November 3, 2026

Command actually run:

```powershell
npm exec --yes --cache .tmp/npm-designlang-cache --package=designlang@13.3.2 -- designlang https://modal.com --out design/extracts/modal-2026-11-03 --motion-runtime --wait 4000 --width 1280 --height 900
```

The CLI completed successfully. Retained outputs in GitHub are the generated reference DESIGN.md, DTCG design tokens and motion tokens. Other generated previews/configurations remain local and are not needed by the playground.

These files describe the reference site. They are evidence, not repository-wide instructions, a Granite Query palette, or a recovered implementation of Modal’s hero.

## Review the extraction before using it

The measured headline (45 px / 48 px / weight 500), the green accent (#7fee64), background (#040804) and pill radius (48 px) agree with browser inspection. The 200 ms navigation transition and `cubic-bezier(0.165,0.84,0.44,1)` easing inform the study’s small UI transitions.

Some generated classifications do not describe the hero correctly: the file labels #cce218 as a primary action color, while the observed hero primary button is #e3e5e1; the generated 9.854 px body size is an aggregate, not the hero description size. Generated tonal ramps and suggested semantic roles are not measured source tokens. The tool’s automatic quality/a11y grades are not evidence that the reconstruction is enterprise ready.

The runtime observations cover CSS/Web Animations, not the Three.js canvas scene graph or GLSL behavior. The hero’s shapes and choreography were reconstructed from captured states, with independently authored timing. Do not claim the tool extracted the hero’s shader or recovered its original motion.
