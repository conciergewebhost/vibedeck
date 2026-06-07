/**
 * Typed client for the Vibedeck FastAPI backend.
 *
 * SSR pages call these on each request. The backend base URL is read from
 * API_BASE_URL (see .env.example). 404s resolve to `null` so pages can
 * return their own 404 Response; other non-2xx throw.
 */

const API_BASE =
  (import.meta.env.API_BASE_URL as string | undefined) ??
  (typeof process !== "undefined" ? process.env.API_BASE_URL : undefined) ??
  "http://localhost:8000";

export interface TopicSummary {
  slug: string;
  display_name: string;
  description: string | null;
  theme: string | null;
  deck_count: number;
  top_keywords: string[];
}

export interface DeckListItem {
  slug: string;
  title: string;
  author: string;
  description: string | null;
  theme: string;
  keywords: string[];
  card_count: number;
}

export interface TopicDetail {
  slug: string;
  display_name: string;
  description: string | null;
  theme: string | null;
  decks: DeckListItem[];
}

export interface Card {
  type: string;
  meta: Record<string, unknown>;
  body: string;
}

export interface DeckDetail {
  slug: string;
  title: string;
  author: string;
  description: string | null;
  topic: string;
  theme: string;
  keywords: string[];
  cards: Card[];
}

async function getJson<T>(path: string): Promise<T | null> {
  const res = await fetch(`${API_BASE}${path}`);
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(`Backend ${path} responded ${res.status}`);
  }
  return (await res.json()) as T;
}

export interface PublicDeckItem {
  topic: string; // slug
  topic_name: string;
  slug: string;
  title: string;
  author: string;
  card_count: number;
  url: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface SiteMeta {
  edition: string;
  allow_public_signup: boolean;
  allow_anon_read: boolean;
  moderation_enabled: boolean;
  visibility_enabled: boolean;
  quotas_enabled: boolean;
}

/** Non-secret deployment flags (edition + feature toggles) for UI adaptation. */
export const fetchMeta = () => getJson<SiteMeta>("/api/meta");

export const fetchTopics = () => getJson<TopicSummary[]>("/api/topics");
export const fetchPublicDecks = () =>
  getJson<PublicDeckItem[]>("/api/decks/public");
export const fetchTopic = (slug: string) =>
  getJson<TopicDetail>(`/api/topics/${encodeURIComponent(slug)}`);
export const fetchDeck = (topic: string, deck: string) =>
  getJson<DeckDetail>(
    `/api/decks/${encodeURIComponent(topic)}/${encodeURIComponent(deck)}`,
  );

/**
 * Parse raw deck markdown via the public sandbox endpoint (no persistence).
 * Returns the parsed deck on success, or the parser's error message on a 400
 * so the sandbox can show authors exactly what's wrong.
 */
export async function previewDeck(
  markdown: string,
): Promise<{ ok: true; deck: DeckDetail } | { ok: false; error: string }> {
  const res = await fetch(`${API_BASE}/api/decks/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ markdown }),
  });
  if (res.ok) {
    return { ok: true, deck: (await res.json()) as DeckDetail };
  }
  const data = (await res.json().catch(() => ({}))) as { detail?: string };
  return { ok: false, error: data.detail ?? `Preview failed (${res.status}).` };
}
