/**
 * Curated font set for the form-based theme builder.
 *
 * Custom themes are injected as plain CSS and may NOT use @import (the theme
 * validator blocks it), so a theme can only use fonts the *app* has already
 * loaded. This is the single source of truth for that set: the builder's font
 * dropdowns read `label`/`stack`, and BaseLayout preloads the `google` ones so
 * every page (and therefore every custom theme) can render them.
 */
export interface CuratedFont {
  label: string;
  /** The `font-family` value emitted into the theme's --vd-font-* token. */
  stack: string;
  /** Google Fonts `family=` spec; omit for system stacks (no external load). */
  google?: string;
}

export const CURATED_FONTS: CuratedFont[] = [
  { label: "System sans", stack: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif' },
  { label: "System serif", stack: 'Georgia, "Times New Roman", serif' },
  { label: "System mono", stack: 'ui-monospace, "SF Mono", Menlo, Consolas, monospace' },
  { label: "Inter", stack: '"Inter", system-ui, sans-serif', google: "Inter:wght@400;600;700" },
  { label: "Lora", stack: '"Lora", Georgia, serif', google: "Lora:ital,wght@0,400;0,600;1,400" },
  { label: "Space Grotesk", stack: '"Space Grotesk", system-ui, sans-serif', google: "Space+Grotesk:wght@400;500;700" },
  { label: "Playfair Display", stack: '"Playfair Display", Georgia, serif', google: "Playfair+Display:wght@400;700" },
  { label: "Bebas Neue", stack: '"Bebas Neue", Impact, sans-serif', google: "Bebas+Neue" },
];

/** The single Google Fonts stylesheet URL covering every curated web font. */
export function googleFontsHref(): string {
  const families = CURATED_FONTS.filter((f) => f.google).map((f) => `family=${f.google}`);
  return `https://fonts.googleapis.com/css2?${families.join("&")}&display=swap`;
}
