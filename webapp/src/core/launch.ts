import { WEB_SESSION, type GameRef, type MeResponse } from "../api";
import type { Locale } from "../i18n";
import { asLaunchTab, SCREEN_NAMES, type LaunchTab } from "./constants";

export type LoadState =
  | { status: "loading" }
  | { status: "need-telegram" }
  | { status: "login" }
  | { status: "error"; message: string }
  | { status: "ok"; me: MeResponse };

// Open in a plain browser, signed in through Telegram Login (#157): the session
// cookie signs requests, and this stands in for Init Data.
let webSession = false;

export function setWebSession(on: boolean): void {
  webSession = on;
}

export function initData(): string {
  return window.Telegram?.WebApp?.initData || (webSession ? WEB_SESSION : "");
}

export function localeOf(me: MeResponse): Locale {
  return me.settings.locale === "en" ? "en" : "ru";
}
/** The reverse of `bot/services/mini_app.py::_encode_game` — base64url,
 * padding restored, back to "platform:titleId". `null` on anything that
 * doesn't actually decode, rather than a page that opens on garbage. */
function decodeGameToken(token: string): string | null {
  try {
    const padded = token + "=".repeat((4 - (token.length % 4)) % 4);
    const std = padded.replace(/-/g, "+").replace(/_/g, "/");
    return atob(std);
  } catch {
    return null;
  }
}

// Where the app was, kept for this tab's session (owner, 2026-10-06): a reload
// — a new build, a pull of the browser — comes back to the same screen, the
// same person and the same game instead of Home. A link that names where to
// go always wins.
export const PLACE_KEY = "app-place";
export type Place = { screen: string; personId: number | null; game: GameRef | null };

function savedPlace(): Place | null {
  try {
    const raw = sessionStorage.getItem(PLACE_KEY);
    return raw ? (JSON.parse(raw) as Place) : null;
  } catch {
    return null;
  }
}

export function savePlace(place: Place): void {
  try {
    sessionStorage.setItem(PLACE_KEY, JSON.stringify(place));
  } catch {
    // No storage: a reload opens Home.
  }
}

export function launchContext(): {
  chatId: number | null;
  personId: number | null;
  /** A post's button from before person ids (#156) names a Telegram id. */
  legacyTgId: number | null;
  tab: LaunchTab;
  game: GameRef | null;
  /** A game's post a push opens (`n=appid:gid`, owner 2026-10-08), its game
   * in its head. */
  news: { appid: number; gid: string; game: GameRef | null } | null;
  /** A push about a new post names its achievement (`a=`). */
  achievement?: string | null;
  /** The screen a reload comes back to. */
  screen?: string;
} {
  const q = new URLSearchParams(window.location.search);
  const start = window.Telegram?.WebApp?.initDataUnsafe?.start_param ?? "";
  let chatId = q.get("c");
  let personId = q.get("p");
  let legacyTg = q.get("u");
  let tab = q.get("t");
  // From the query string (a DM's own https URL): plain "platform:titleId",
  // already percent-decoded by URLSearchParams.
  let game = q.get("g");
  // From a group's startapp value: base64url of the same string — Telegram's
  // start_parameter only allows [A-Za-z0-9_-], which a literal ':' falls
  // outside of (found live, 2026-09-30 review of #145: every group deep
  // link to a game was silently broken). See bot/services/mini_app.py's
  // `_encode_game`, which this must stay in sync with.
  const parsed = /^c(-?\d+)(?:([pu])(\d+))?(?:t([a-z]+))?(?:g([A-Za-z0-9_-]+))?$/.exec(start);
  const linked = Boolean(start) || ["c", "p", "u", "t", "g", "n"].some((key) => q.has(key));
  const newsMatch = /^(\d+):(.+)$/.exec(q.get("n") ?? "");
  const place = linked ? null : savedPlace();
  if (parsed) {
    chatId ??= parsed[1];
    if (parsed[2] === "p") personId ??= parsed[3] ?? null;
    else legacyTg ??= parsed[3] ?? null;
    tab ??= parsed[4] ?? null;
    game ??= parsed[5] ? decodeGameToken(parsed[5]) : null;
  }
  // A group post's token may carry its achievement as a third part
  // (`platform:titleId:achievementId`, bot/services/mini_app.py).
  let tokenAch: string | null = null;
  if (game && parsed?.[5]) {
    const parts = game.split(":");
    if (parts.length >= 3) {
      tokenAch = parts.slice(2).join(":");
      game = `${parts[0]}:${parts[1]}`;
    }
  }
  // Split on the first ":" only — a title_id is never expected to hold one,
  // but nothing stops it from someday.
  const colon = game?.indexOf(":") ?? -1;
  const personNum = personId ? Number(personId) : null;
  if (place) {
    return {
      chatId: null,
      personId: place.personId,
      legacyTgId: null,
      tab: SCREEN_NAMES.HOME,
      game: place.game,
      news: null,
      screen: place.screen,
    };
  }
  // Whose progress the game page opens on: the achievement's own owner, not
  // necessarily whoever tapped the link — the name is filled in once the game
  // page's own fetch resolves who that is (see TitleSheet).
  const gameRef: GameRef | null =
    game && colon > 0 && colon < game.length - 1
      ? {
          platform: game.slice(0, colon),
          title_id: game.slice(colon + 1),
          // A post's button from before person ids names a Telegram id: the
          // game page asks by it and learns the person from the answer.
          person: personNum
            ? { person_id: personNum, name: "" }
            : legacyTg
              ? { tg_id: Number(legacyTg), name: "" }
              : null,
        }
      : null;
  return {
    chatId: chatId ? Number(chatId) : null,
    personId: personNum,
    legacyTgId: legacyTg ? Number(legacyTg) : null,
    tab: asLaunchTab(tab),
    // A push about a game's post opens the post, its game a tap away in its
    // head — not the game page under it, which took the phone's first back.
    news: newsMatch ? { appid: Number(newsMatch[1]), gid: newsMatch[2], game: gameRef } : null,
    game: newsMatch ? null : gameRef,
    achievement: gameRef ? (q.get("a") ?? tokenAch) : null,
  };
}
