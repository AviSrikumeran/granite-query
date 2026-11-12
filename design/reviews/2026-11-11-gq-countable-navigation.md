# Navigation correction: countable glyphs

The owner rejected the first navigation integration: it was too small, its glyph texture became noise, and a separate background did not match the page. The large-format prototype did not translate successfully by scaling alone.

The corrected navigation mark is authored as 41 individual symbols: 19 in G and 22 in Q. It uses the established atlas's Y, asterisk, ring, filled circle and hexagonal forms. Both letters have deliberate complete strokes and the Q tail stays attached to the whole artwork's gentle turn. A small vertex shader replaces the dense surface sampler for this navigation-sized treatment.

The desktop box is 154 by 88 px; mobile is 136 by 80 px. An intermediate size and header spacing keep tablet navigation usable. Transparent composition, no backing tile and localized two-level bloom remove the mismatched rectangle. Light pages use richer magenta for contrast. The original homepage sculpture and research content remain untouched.

Verification: staged rendering confirmed exactly 41 submitted glyphs, a transparent link background on dark and light pages, and readable letter silhouettes. Keyboard pause, reduced-motion and graphics fallback behavior are retained from the prior integration. This correction supersedes the dense navigation treatment in the earlier integration review.
