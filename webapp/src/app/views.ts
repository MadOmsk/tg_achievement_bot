import type { FeedItem, GameAchievement, GameRef } from "../api";
import { feedKey } from "../core/feed-utils";
import { pickLocale } from "../core/game-utils";
import type { Locale } from "../i18n";
import type { AchView } from "./layers";

export function achOfFeed(item: FeedItem): AchView {
  return {
    key: feedKey(item),
    name: item.name,
    description: item.description,
    icon: item.icon_url,
    rarity: item.rarity_percent,
    gamerscore: item.gamerscore || null,
    trophy: item.trophy_type,
    mythic: Boolean(item.mythic),
    secret: item.is_secret,
    unlockedAt: item.unlocked_at,
    platform: item.platform,
    titleId: item.title_id,
    achievementId: item.achievement_id,
    game: item.game,
    gameIcon: item.game_poster ?? item.game_icon_url,
    gameId: item.game_id ?? null,
    person: { id: item.person_id, name: item.person },
  };
}

export function achOfList(
  a: GameAchievement,
  list: { platform: string; titleId: string; game: string | null; icon: string | null; gameId?: number | null },
  person: { id: number; name: string } | null,
  locale: Locale,
): AchView {
  return {
    key: `${list.platform}:${list.titleId}:${a.achievement_id}:${person?.id ?? 0}`,
    name: pickLocale(locale, a.name_ru, a.name_en),
    description: pickLocale(locale, a.description_ru, a.description_en) || null,
    icon: a.icon_url,
    rarity: a.rarity_percent,
    gamerscore: a.gamerscore ?? a.score ?? null,
    trophy: a.trophy_type,
    secret: a.is_secret,
    unlockedAt: a.is_unlocked ? a.unlocked_at : null,
    platform: list.platform,
    titleId: list.titleId,
    achievementId: a.achievement_id,
    game: list.game,
    gameIcon: list.icon,
    gameId: list.gameId ?? null,
    person: a.is_unlocked ? person : null,
  };
}

export function gameRefOfFeed(item: FeedItem): GameRef {
  return {
    game_id: item.game_id ?? undefined,
    platform: item.platform,
    title_id: item.title_id,
    name: item.game,
    icon_url: item.game_poster ?? item.game_icon_url,
    person: { person_id: item.person_id, name: item.person },
  };
}

/** Which secrets the reader opened, for this session. */
export const revealed = new Set<string>();

export function isVeiled(secret: boolean, key: string, showSecrets: boolean): boolean {
  return secret && !showSecrets && !revealed.has(key);
}

export type Tier = "mythic" | "legendary" | "rare";

/** The app's own points (owner, 2026-10-27), one scale for every platform
 * in place of Xbox's gamerscore — the server counts them the same way
 * (`_sql.points`). Tens, so a step between can come later. */
export const POINTS = { common: 10, rare: 20, legendary: 30, mythic: 100 } as const;

export function pointsOf(rarity: number | null, special?: { trophy?: string | null; mythic?: boolean }): number {
  return POINTS[rareLevel(rarity, special) ?? "common"];
}

/** How a tier is named. */
export const TIER_NAME = {
  mythic: "rarityMythic",
  legendary: "rarityLegendary",
  rare: "rarityRareWord",
  common: "rarityCommon",
} as const;

/** One rarity scale for every platform, a game's item tiers: mythic — Xbox's
 * Mythic and PSN's platinum —, legendary at 1 % and under, rare at 10 % and
 * under (the posts' threshold); the rest none. */
export function rareLevel(rarity: number | null, special?: { trophy?: string | null; mythic?: boolean }): Tier | null {
  if (special?.mythic || special?.trophy?.toLowerCase() === "platinum") return "mythic";
  if (rarity == null) return null;
  if (rarity <= 1) return "legendary";
  if (rarity <= 10) return "rare";
  return null;
}
