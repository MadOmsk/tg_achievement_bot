import type { FeedItem, OnlineMember, SummaryMember } from "../../api";
import type { Locale } from "../../i18n";

export function formatMonth(
  ym: string,
  locale: Locale,
  kind: "chip" | "sheet" = "sheet",
): string {
  const [year, month] = ym.split("-").map(Number);
  if (!year || !month) return ym;
  const tag = locale === "ru" ? "ru-RU" : "en-US";
  const nowYear = new Date().getFullYear();
  const opts: Intl.DateTimeFormatOptions =
    kind === "chip"
      ? { month: "short", ...(year === nowYear ? {} : { year: "numeric" }) }
      : { month: "long", year: "numeric" };
  return new Date(year, month - 1, 1)
    .toLocaleDateString(tag, opts)
    .replace(" г.", "");
}

export function rankPeople(members: OnlineMember[]): OnlineMember[] {
  return [...members].sort(
    (a, b) =>
      Number(b.playing) - Number(a.playing) ||
      Number(b.state === "Online") - Number(a.state === "Online"),
  );
}

export function countByPerson(
  items: FeedItem[],
  sinceMs?: number,
): Map<number, number> {
  const map = new Map<number, number>();
  for (const row of items) {
    if (sinceMs && row.unlocked_at) {
      const t = Date.parse(row.unlocked_at);
      if (!Number.isNaN(t) && t < sinceMs) continue;
    }
    map.set(row.tg_id, (map.get(row.tg_id) ?? 0) + 1);
  }
  return map;
}

export interface RareFinder {
  tgId: number;
  name: string;
  /** Rarest first. */
  items: FeedItem[];
}

/** Who unlocked what fewer than `maxPercent` of players ever got, most first. */
export function rareFinders(items: FeedItem[], maxPercent: number): RareFinder[] {
  const byPerson = new Map<number, RareFinder>();
  for (const row of items) {
    if (row.rarity_percent == null || row.rarity_percent >= maxPercent) continue;
    const cur = byPerson.get(row.tg_id) ?? {
      tgId: row.tg_id,
      name: row.person,
      items: [],
    };
    cur.items.push(row);
    byPerson.set(row.tg_id, cur);
  }
  for (const finder of byPerson.values()) {
    finder.items.sort(
      (a, b) => (a.rarity_percent ?? 100) - (b.rarity_percent ?? 100),
    );
  }
  return [...byPerson.values()].sort((a, b) => b.items.length - a.items.length);
}

export function sumMap(counts: Map<number, number>): number {
  let s = 0;
  for (const v of counts.values()) s += v;
  return s;
}

export function sumCounts(rows: SummaryMember[]): number {
  return rows.reduce((s, r) => s + r.count, 0);
}

export function pickCount(
  rows: SummaryMember[],
  meId: number,
  fallback: Map<number, number>,
): number {
  const row = rows.find((r) => r.tg_id === meId);
  return row ? row.count : fallback.get(meId) ?? 0;
}
