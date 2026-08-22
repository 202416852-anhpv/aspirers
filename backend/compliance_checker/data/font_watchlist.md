# Font Watchlist — Commercial fonts commonly used without a license in POD

*Source: manually compiled from common knowledge in the Print-on-Demand design industry (not an automated crawl from MyFonts/Adobe Fonts). Last updated: 2026-08-20.*

⚠️ **Important limitation** (agreed during the brainstorming session, see `CLAUDE.md` section 9.5): accurately identifying a commercial font's exact name from a raster image is a specialized problem (like WhatTheFont/Fontspring Matcherator) — NOT feasible with a general-purpose Vision LLM at high confidence. This list mainly helps the agent write a `fix_suggestion` pointing in the right direction ("this may be one of the following fonts — please verify the license manually"), not to confidently assert an exact font name.

## Font groups most often involved in POD license violations

- **Premium script/handwritten**: Mishka, Sloop Script, Bickham Script Pro — often used without a license for personalized cards/mugs.
- **Display/branding**: Gotham, Proxima Nova, Futura PT — usually require a paid commercial license, often mistaken for "free" because they resemble free alternatives (Montserrat, Poppins).
- **Fonts tied to a specific brand** (double risk — both a font-license violation and a brand association): the Disney typeface (Waltograph), the Harry Potter typeface (Harry P), the Coca-Cola script.
- **Popular "quote/motivational" fonts on Etsy**: Amsterdam, Sweet Sunday Script — many copies circulating with unclear license provenance.

## How the agent should handle this (approximate description, not exact identification)

1. Describe the general letterform style (e.g. "bold condensed sans-serif", "elegant script with long letter tails") — do NOT assert a specific commercial font name unless it is extremely distinctive and unmistakable.
2. Always include the fixed disclaimer (injected at the orchestrator layer, see `CLAUDE.md` section 3): *"Font detection is best-effort. Recommend manual verification against font license databases (MyFonts, Adobe Fonts, Font Squirrel)."*
3. (2026-08-22, policy update) There is no reliable static name-list to cross-reference fonts against — verdict for this category depends entirely on the agent's own reasoning. Even without a confirmed database match, if the resemblance to a specific commercial/branded font is highly distinctive and the agent explains it thoroughly (which font, why it's confident), this can still escalate to BLOCKED — same policy as the other candidate categories (logo/character/artwork). The agent has the authority to flag it, provided the reasoning clearly states which font it resembles and explicitly recommends a quick manual license check, precisely because there is no database confirmation behind it.
