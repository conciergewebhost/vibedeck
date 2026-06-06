/**
 * Markdown rendering for card bodies.
 *
 * Decks can be uploaded by any signed-in user and are viewable publicly, so
 * the rendered HTML is sanitised: scripts, event handlers, iframes, inline
 * styles, etc. are stripped while safe markup (links incl. `download`, lists,
 * images, emphasis, code, blockquotes) is kept. This is the real XSS guard;
 * the backend additionally rejects blatant code at upload time.
 */

import { marked } from "marked";
import DOMPurify from "isomorphic-dompurify";

marked.setOptions({ gfm: true, breaks: false });

// Allowlist tuned to what card bodies legitimately use.
const SANITIZE_CONFIG = {
  ALLOWED_TAGS: [
    "p", "br", "hr", "span", "div",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li",
    "strong", "em", "b", "i", "del", "code", "pre", "blockquote",
    "a", "img",
    "table", "thead", "tbody", "tr", "th", "td",
  ],
  // No `target`: links open in the same tab, which avoids reverse-tabnabbing
  // and stops a link from framing-out of the reader's preview iframe.
  ALLOWED_ATTR: ["href", "title", "alt", "src", "download"],
  // Only allow safe URL schemes (no javascript:, etc.).
  ALLOWED_URI_REGEXP: /^(?:https?:|mailto:|tel:|\/|#|data:image\/)/i,
};

export function renderMarkdown(md: string): string {
  const html = marked.parse(md, { async: false }) as string;
  return DOMPurify.sanitize(html, SANITIZE_CONFIG);
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
