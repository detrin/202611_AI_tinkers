---
name: product-ui
description: Shared visual and copy rules for the outfit app PWA, the marketing website and the pitch slides, so all three look like one product. Use before writing any UI, CSS, component, landing page section or slide.
---

# Product UI — one look across PWA, website and slides

The product makes one decision for you in the morning. The interface should feel the same: calm, one answer, nothing to configure. Sun's mockup is the reference for layout: four tabs (Today, My Closet, My Style, Settings).

## Tokens

These follow Sun's mockup and are the ones the PWA uses. The source of truth is the `:root` block in `pwa/src/styles.css`; copy from there.

```css
:root {
  --bg: #f7f6f2;          /* warm off-white page */
  --surface: #ffffff;     /* cards */
  --soft: #f0efea;        /* quiet panels, image backgrounds */
  --ink: #1c1c1a;
  --ink-2: #6f6e69;       /* secondary text */
  --line: #e7e5df;
  --accent: #1f5a3d;      /* deep green: primary button, active tab */
  --accent-soft: #e3efe7;
  --ok: #2f8f5b;
  --danger: #b8443a;
  --radius: 18px;
  font-family: Inter, ui-sans-serif, system-ui, sans-serif;
}
```

Spacing on a 4px grid: 4, 8, 12, 16, 24, 32, 48, 72. Type scale: 13, 15, 17, 22, 32, 48. One sans-serif family throughout; page titles are 28px bold.

## Rules

- One accent element per screen: the primary action or the single most important fact.
- No gradients, glassmorphism, glows, purple-to-blue anything, drop shadows heavier than `0 1px 2px rgb(0 0 0 / .06)`, or emoji as icons. Use one icon set (Lucide), 1.5px stroke.
- No cards inside cards. Separate with space first, a hairline second, a surface third.
- Left-aligned text. Centre only the outfit headline on the home screen.
- Motion: 180ms ease-out, opacity and 8px translate only. Respect `prefers-reduced-motion`.
- Tap targets at least 44px. Contrast at least 4.5:1 for text.

## PWA home screen, top to bottom

1. Date and one-line day summary: "Fri 13 Nov · 6° and dry · 3 meetings".
2. The outfit, as the headline: the pieces by name, with images if we have them.
3. The reason, one sentence, in plain words: "Client meeting at 10 and you're cycling, so the wool blazer over a tee."
4. Two actions only: "Wear this" (accent) and "Something else".
5. Collapsed "Why" drawer listing the inputs used: calendar events, weather, route.

Every state must be designed: loading (skeleton of the same layout, not a spinner), empty (no calendar connected), error (show last good outfit and say it is from earlier), offline.

## Copy

- The app speaks like a friend who knows your wardrobe: short, specific, no exclamation marks.
- Buttons are verbs: "Wear this", "Something else", "Connect calendar".
- Never write "AI", "smart" or "powered by" in the interface. Show the reasoning instead.
- Numbers with units, times in 24h, temperatures in °C.

## Website

Same tokens. One page: headline that states what it does in under ten words, a real screenshot of the PWA, three short sections (what it reads, what it decides, who it is for), one call to action. No stock photos, no feature grid of six icons, no testimonials we made up.
