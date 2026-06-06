---
title: Crafting a VibeDeck Theme
author: Rob Wall
topic: vibedeck
keywords: [theming, css, customization, reference]
theme: operazione-stile
description: How VibeDeck themes work, the token contract every theme fills in, and how to build or tweak your own.
---
---
type: title
---
# Crafting a VibeDeck Theme
### One CSS file, a handful of tokens
---
type: concept
---
## One file per theme

A theme is a single CSS file in `src/styles/themes/`. A deck picks one with its frontmatter:

```
theme: operazione-stile
```

That name maps straight to `themes/operazione-stile.css`. Unknown names fall back to `default.css`.
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

`default.css` is the canonical list. Copy it, retune the values — but don't invent new variable *names* without adding them to every theme.
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
## Restyling components

For a distinct look beyond colours, target a card's body with an ancestor chain — specific enough to beat the components' scoped styles:

```
.reader__stage .reader__card .card-body--quote {
  border-left: 4px solid var(--vd-accent);
  font-style: italic;
}
```

This is how the bespoke themes add stamps, rules, and textures.
---
type: summary
---
## Make your own

- Copy `default.css` to `themes/my-theme.css`
- Retune the `--vd-*` values to taste
- Add a `:root[data-mode="light"]` block if you want light mode
- Layer ancestor-chain rules for any deeper restyling
- Set `theme: my-theme` in a deck and reload
---
type: quote
---
> Define the tokens once; every card, the reader, and the nav restyle themselves.

— The theming contract
