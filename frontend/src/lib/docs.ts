/**
 * Registry for the on-site documentation pages (/docs).
 *
 * The markdown sources are the repo's own docs/ files, imported raw at
 * build time — the site always serves the docs that shipped with it, and
 * there's exactly one copy to maintain. Each entry renders at
 * /docs/{slug}, with the raw markdown at /docs/{slug}.md (which is what
 * the "copy" buttons read).
 */

import themingRaw from "../../../docs/THEMING.md?raw";
import formatRaw from "../../../docs/VIBEDECK_FORMAT.md?raw";

export interface DocEntry {
  slug: string;
  title: string;
  blurb: string;
  raw: string;
}

export const DOCS: Record<string, DocEntry> = {
  format: {
    slug: "format",
    title: "The Vibedeck File Format",
    blurb:
      "The complete authoring reference — every frontmatter field, all five " +
      "card types, the validation rules, and a worked example. Written to " +
      "double as AI-assistant context for generating decks.",
    raw: formatRaw,
  },
  theming: {
    slug: "theming",
    title: "Theming Vibedeck",
    blurb:
      "How themes work and how to build your own — the --vd-* token " +
      "contract, the in-browser theme builder, and CSS-file themes for " +
      "self-hosters.",
    raw: themingRaw,
  },
};

export const DOC_LIST: DocEntry[] = Object.values(DOCS);
