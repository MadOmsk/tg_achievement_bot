import type { FeedResponse, MeResponse, OnlineMember, PersonPayload, SummaryResponse } from "../../../../api";

/**
 * The last Home this device was shown, kept between openings (owner,
 * 2026-10-07): the app opens on it at once and the fresh answers replace it
 * as they come. Only this device's own viewer is kept — a Telegram account
 * other than the one stored, or a browser signed out, finds nothing.
 */

const KEY = "home-cache-v1";
// Older than this, the page is not worth showing even for a moment.
const MAX_AGE_MS = 7 * 24 * 3600 * 1000;

export type HomeParts = {
  feed?: FeedResponse;
  online?: { members: OnlineMember[] };
  summary?: SummaryResponse;
  mine?: PersonPayload;
};

type Stored = { who: string; at: number; me: MeResponse; home: HomeParts };

/** Who opens the app here: the Telegram account the Mini App runs in, or the browser. */
export function cacheViewer(): string {
  const id = window.Telegram?.WebApp?.initDataUnsafe?.user?.id;
  return id ? `tg:${id}` : window.Telegram?.WebApp?.initData ? "" : "web";
}

function read(): Stored | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const stored = JSON.parse(raw) as Stored;
    if (!stored.who || stored.who !== cacheViewer()) return null;
    if (Date.now() - stored.at > MAX_AGE_MS) return null;
    return stored;
  } catch {
    return null;
  }
}

function write(stored: Stored): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(stored));
  } catch {
    // Full or forbidden: the app simply opens as it did before.
  }
}

/** The viewer as last seen on this device, to open on before `/me` answers. */
export function cachedMe(): MeResponse | null {
  return read()?.me ?? null;
}

/** Home's answers as last seen, when they are this person's. */
export function cachedHome(personId: number): HomeParts | null {
  const stored = read();
  return stored && stored.me.person_id === personId ? stored.home : null;
}

export function rememberMe(me: MeResponse): void {
  const who = cacheViewer();
  if (!who) return;
  const stored = read();
  const home = stored && stored.me.person_id === me.person_id ? stored.home : {};
  write({ who, at: Date.now(), me, home });
}

export function rememberHome(personId: number, home: HomeParts): void {
  const stored = read();
  if (!stored || stored.me.person_id !== personId) return;
  write({ ...stored, at: Date.now(), home: { ...stored.home, ...home } });
}

/** Signed out or gone: nothing of the person stays on the device. */
export function forgetHome(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    // Nothing to do.
  }
}
