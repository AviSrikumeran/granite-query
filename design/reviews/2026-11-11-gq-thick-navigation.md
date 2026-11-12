# Approved thicker GQ navigation

The owner approved the top, bright-magenta treatment in the actual-size dark-header preview, then authorized publication. This replaces the sparse single-row outline with the exact approved 37-glyph drawing: paired structural glyphs, a faint connected letter face, larger solid forms and selected open accents.

`gq-thick-material.mjs` preserves the preview's positions, glyph kinds, color ramps, face opacity, depth offset, localized glow and traveling shine. The navigation wrapper uses the approved five-degree slow turn and 1.8-degree tilt. Rendering now uses Canvas 2D, which also avoids requiring WebGL for this compact mark. The prior renderer and symbol modules remain as historical source.

The mark stays 154 by 88 px on desktop/tablet and 136 by 80 px on mobile. Its background is transparent; light headers retain the matching deeper-magenta adaptation. The original homepage sculpture, research text, data and inference infrastructure are unchanged.

Validation: source parity review against the approved preview; staged browser checks for 37 rendered glyphs, desktop and light-header rendering, keyboard pause, working mobile menu, no overflow at 651px/320px, reduced-motion still state and a visible unavailable-canvas fallback. Existing site tests passed.
