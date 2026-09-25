import type { FeedItem } from "../../api";
import { UI_CONFIG } from "../shared/constants";

const HOME_SLIDES = UI_CONFIG.HOME.MAX_CAROUSEL_SLIDES;

/** Newest unlock per game, capped — home carousel shows games, not achievements. */
export function recentGames(
  items: FeedItem[],
  limit = HOME_SLIDES,
): FeedItem[] {
  const seen = new Set<string>();
  const out: FeedItem[] = [];
  for (const row of items) {
    const key = `${row.platform}:${row.title_id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(row);
    if (out.length >= limit) break;
  }
  return out;
}

export function gameKey(item: FeedItem): string {
  return `${item.platform}:${item.title_id}`;
}

export function feedKey(row: FeedItem): string {
  return `${row.platform}:${row.title_id}:${row.achievement_id}:${row.tg_id}`;
}

export function veiled(
  item: { is_secret: boolean },
  key: string,
  revealed?: Set<string>,
  showSecrets?: boolean,
): boolean {
  return Boolean(
    item.is_secret && !showSecrets && revealed && !revealed.has(key),
  );
}

export function matchQuery(haystack: string, query: string): boolean {
  const h = haystack.trim().toLowerCase();
  const q = query.trim().toLowerCase();
  return Boolean(q && h && h.includes(q));
}
