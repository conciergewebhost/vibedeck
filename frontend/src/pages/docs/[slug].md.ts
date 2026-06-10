/**
 * /docs/{slug}.md — the raw markdown source of a documentation page.
 *
 * Serves as text/plain so browsers display it inline; this is also what the
 * "copy as markdown" buttons fetch.
 */
import type { APIRoute } from "astro";
import { DOCS } from "../../lib/docs";

export const GET: APIRoute = ({ params }) => {
  const doc = DOCS[params.slug ?? ""];
  if (!doc) {
    return new Response("Not found", { status: 404 });
  }
  return new Response(doc.raw, {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
};
