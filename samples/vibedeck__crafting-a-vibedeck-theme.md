---
title: Crafting a VibeDeck Theme
author: Rob Wall
topic: vibedeck
keywords: [theming, css, customization, reference]
theme: operazione-stile
description: How VibeDeck themes work — the in-browser theme builder, the token contract every theme fills in, and the CSS-file route for self-hosters.
---
---
type: title
---
# Crafting a VibeDeck Theme
### A handful of tokens, two ways to set them
---
type: concept
---
## Two ways to a theme

**In the browser** — sign in and open the theme builder. Pick your colours, fonts, and shape tokens, save under a name, and set that name as your deck's `theme:`. No code, and it can't break anything: the builder only writes the safe token block.

**As a CSS file** — running your own instance? Built-in themes are plain CSS files in `src/styles/themes/`, and you can add your own.

Either way, every reader of your deck sees your theme — not just you.
---
type: concept
---
## How a deck picks its theme

A deck names its theme in frontmatter:

```
theme: operazione-stile
```

Built-in names map straight to a file — `themes/operazione-stile.css`. Any other name looks up a theme *you* built under that name. No match? The deck falls back to `default`.
---
type: concept
---
## The token contract

Components never hardcode colours — they read `--vd-*` variables. A theme's whole job is to define that set on `:root`:

```
:root {
  --vd-bg: #0f172a;
  --vd-text: #e2e8f0;
  --vd-accent: #818cf8;
}
```

`default.css` is the canonical list. The theme builder exposes the same tokens as controls — same contract, no syntax.
---
type: summary
---
## The tokens, grouped

- **Surfaces** — `--vd-bg`, `--vd-card-bg`, `--vd-card-border`
- **Text** — `--vd-text`, `--vd-text-muted`, `--vd-heading`
- **Accent** — `--vd-accent`, `--vd-accent-2`
- **Type** — `--vd-font-body`, `--vd-font-heading`, `--vd-font-scale`
- **Layout** — `--vd-card-max-width`, `--vd-card-padding`, `--vd-radius`
- **Chrome** — `--vd-nav-bg`, `--vd-progress`
---
type: concept
---
## Light and dark

The toggle sets `data-mode` on the page's root element. A theme supports light mode by overriding the same tokens under a matching selector:

```
:root[data-mode="light"] {
  --vd-bg: #f1ecdd;
  --vd-text: #2e231b;
}
```

Define only what changes; everything else inherits from the dark defaults.
---
type: concept
---
## Restyling components (CSS-file themes)

In a theme file, you can go beyond colours by targeting a card's body with an ancestor chain — specific enough to beat the components' scoped styles:

```
.reader__stage .reader__card .card-body--quote {
  border-left: 4px solid var(--vd-accent);
  font-style: italic;
}
```

This is how the bespoke themes add stamps, rules, and textures. (The in-browser builder deliberately stays in token territory — that's what keeps it safe.)
---
type: summary
---
## Make your own

- **No code:** sign in → theme builder → tune the tokens → save as `my-theme`
- **Self-hosting:** copy `default.css` to `themes/my-theme.css` and retune the `--vd-*` values
- Add a `:root[data-mode="light"]` block if you want light mode
- In a theme file, layer ancestor-chain rules for deeper restyling
- Set `theme: my-theme` in a deck and reload

<a href="/themes/default.css" download>↓ Download default.css</a> to start from.
---
type: quote
---
> Define the tokens once; every card, the reader, and the nav restyle themselves.

— The theming contract
