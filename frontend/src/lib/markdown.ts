/**
 * Markdown rendering for card bodies.
 *
 * Card bodies are raw markdown stored in the canonical deck file and are
 * authored by authenticated users (trusted content), so output is not
 * sanitised in v1. TODO(v2): sanitise if/when decks accept untrusted input.
 */

import { marked } from "marked";

marked.setOptions({ gfm: true, breaks: false });

export function renderMarkdown(md: string): string {
  return marked.parse(md, { async: false }) as string;
}

/**
 * A short label for a card in the index modal: the first heading/line text,
 * falling back to the capitalised card type.
 */
export function cardLabel(body: string, type: string): string {
  for (const raw of body.split("\n")) {
    let line = raw.trim();
    if (!line) continue;
    // Image-only line (graphic cards): use the alt text.
    const img = line.match(/^!\[([^\]]*)\]/);
    line = img ? img[1] : line.replace(/^[#>\-*\s]+/, "");
    // Drop emphasis/inline-code markers for a clean label.
    line = line.replace(/[*_`]/g, "").trim();
    if (line) return line.length > 60 ? line.slice(0, 57) + "…" : line;
  }
  return type.charAt(0).toUpperCase() + type.slice(1);
}
