# Theming Vibedeck

How themes work, every token in the contract, and how to build your own —
whether you're a signed-in author on a hosted instance or a self-hoster
adding themes to the codebase.

For the in-product version of this guide, see the bundled *Crafting a
VibeDeck Theme* deck (`samples/vibedeck__crafting-a-vibedeck-theme.md`).

---

## What a theme is

Vibedeck components never hardcode visual values — every colour, font, and
shape reads a `--vd-*` CSS custom property. A theme is anything that defines
that set of tokens on `:root`. Define the tokens once and every card type,
the reader chrome, and the navigation restyle themselves.

The canonical token list lives in
[`frontend/src/styles/themes/default.css`](../frontend/src/styles/themes/default.css).
Visiting `/themes/default.css` on any instance downloads a copy to start from.

---

## Two ways to create a theme

### 1. The theme builder (signed-in authors — no code)

Open **`/account/theme`**. The builder presents every token as a form
control (colour pickers, font fields, sliders), previews the result live,
and saves the generated CSS under a name you choose. Because the form only
emits constrained token values, the result is safe by construction.

Use it in a deck by setting the theme name in frontmatter:

```yaml
theme: my-theme
```

Your theme renders for **every** reader of that deck — it's inlined
server-side, not just applied to your own view.

To iterate on an existing theme, the builder can load any of your saved
themes back into the form.

### 2. A CSS file in the repo (self-hosters)

Built-in themes are plain CSS files in `frontend/src/styles/themes/` —
one file per theme, where the frontmatter name maps to the filename
(`theme: fascicolo` → `themes/fascicolo.css`). To add one:

1. Copy `default.css` to `frontend/src/styles/themes/my-theme.css`.
2. Re-tune the `--vd-*` values. Don't invent new variable *names* without
   updating every theme — components assume the full set is defined.
3. Rebuild the frontend (`cd frontend && npm run build`). Themes are
   resolved by a build-time glob, so a new file is picked up automatically —
   no registration step.

File-based themes can go beyond tokens (see [Restyling components](#restyling-components-css-file-themes-only)).

---

## How a deck's theme resolves

The `theme` frontmatter field resolves in this order:

1. **A built-in theme** — the name matches a file in
   `frontend/src/styles/themes/` (`operazione-stile`, `fascicolo`,
   `default`, plus any the instance has added).
2. **The author's custom theme** — no built-in matches, so the deck's
   owner's saved themes are checked for that slug. A match is inlined
   into the page at render time for all readers
   (`GET /api/decks/{topic}/{deck}/theme.css` serves the raw CSS).
3. **Fallback** — no match anywhere: the deck renders with `default`.

Topics can also carry a `theme`, applied to their index pages the same way.

---

## The token reference

Defaults shown are from `default.css` (the dark baseline).

### Surfaces

| Token | Controls | Default |
|---|---|---|
| `--vd-bg` | Page/stage background | `#0f172a` |
| `--vd-card-bg` | Card and panel surfaces | `#1e293b` |
| `--vd-card-border` | Card, panel, and divider borders | `#334155` |

### Text

| Token | Controls | Default |
|---|---|---|
| `--vd-text` | Body text | `#e2e8f0` |
| `--vd-text-muted` | Secondary text, captions, hints | `#94a3b8` |
| `--vd-heading` | Headings and the title card | `#f8fafc` |

### Accent

| Token | Controls | Default |
|---|---|---|
| `--vd-accent` | Links, active states, quote rules, primary buttons | `#818cf8` |
| `--vd-accent-2` | Gradient partner / secondary accent | `#c084fc` |

### Typography

| Token | Controls | Default |
|---|---|---|
| `--vd-font-body` | Body font stack | system-ui stack |
| `--vd-font-heading` | Heading font stack | inherits `--vd-font-body` |
| `--vd-font-scale` | Master type-size multiplier for the theme | `1` |

### Layout

| Token | Controls | Default |
|---|---|---|
| `--vd-card-max-width` | Card column width | `40rem` |
| `--vd-card-padding` | Inner card padding | `clamp(1.5rem, 5vw, 3rem)` |
| `--vd-radius` | Corner radius for cards, buttons, inputs | `1rem` |

### Navigation chrome

| Token | Controls | Default |
|---|---|---|
| `--vd-nav-bg` | Reader nav bar background (translucent works well) | `rgba(15, 23, 42, 0.8)` |
| `--vd-progress` | "Page n / total" indicator | inherits `--vd-text-muted` |

---

## Light and dark mode

The site-wide toggle (OS-aware) sets `data-mode` on the page's root
element. A theme supports the other mode by overriding tokens under a
matching selector — define only what changes:

```css
:root[data-mode="light"] {
  --vd-bg: #f1ecdd;
  --vd-card-bg: #faf6ea;
  --vd-text: #2e231b;
  --vd-heading: #1a120c;
}
```

A theme with no `data-mode` block simply looks the same in both modes.

---

## Restyling components (CSS-file themes only)

A file-based theme can restyle component internals, not just recolour
them. Target a card's body with an ancestor chain specific enough to beat
the components' scoped styles:

```css
.reader__stage .reader__card .card-body--quote {
  border-left: 4px solid var(--vd-accent);
  font-style: italic;
}
```

This is how the bespoke built-in themes add stamps, rules, and textures —
see `operazione-stile.css` for a worked example.

The theme builder deliberately stays in token territory; uploaded theme
CSS is validated (below), so selector-based rules belong in repo files.

---

## Validation rules (custom themes)

CSS submitted through the API (`POST /api/themes` — which is what the
builder calls) is validated by `backend/services/themes.py`:

- Must define at least one `--vd-*` custom property (otherwise it isn't a
  theme).
- Maximum size: **64 KB**.
- Rejected outright: any `<` character (keeps HTML/`</style>` breakouts
  out), `@import`, `javascript:` URLs, `expression()`, `behavior:`,
  `-moz-binding`.
- `url(...)` may only reference relative paths or `data:image/*` —
  external `http(s)` fetches are blocked.

On the server edition, non-admin users can save up to `QUOTA_MAX_THEMES`
themes (default 20).

---

## API quick reference

| Endpoint | What it does |
|---|---|
| `POST /api/themes` | Save a theme (`{name, css}`) — validated as above |
| `GET /api/themes/mine` | List your themes |
| `GET /api/themes/mine/{slug}.css` | Raw CSS of one of your themes |
| `DELETE /api/themes/mine/{slug}` | Delete one of your themes |
| `GET /api/decks/{topic}/{deck}/theme.css` | Public: the custom theme a deck uses (404 if it uses a built-in) |

All `mine` routes require a session (`Authorization: Bearer <JWT>`).

---

## Tips

- **Start from `default.css`** — it's the complete contract with comments.
- **Check both modes.** Flip the dark/light toggle before publishing; if
  you only tuned dark tokens, light mode falls back to your dark values.
- **Use the sandbox.** Paste a scratch deck at `/sandbox` to preview
  content quickly; for theme work, the builder's live preview shows every
  card type.
- **Keep contrast honest.** `--vd-text` on `--vd-card-bg` is the pairing
  readers stare at longest.
