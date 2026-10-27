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
    secret: item.is_secret,
    unlockedAt: item.unlocked_at,
    platform: item.platform,
    titleId: item.title_id,
    achievementId: item.achievement_id,
    game: item.game,
    gameIcon: item.game_icon_url,
    person: { id: item.person_id, name: item.person },
  };
}

export function achOfList(
  a: GameAchievement,
  list: { platform: string; titleId: string; game: string | null; icon: string | null },
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
    person: a.is_unlocked ? person : null,
  };
}

export function gameRefOfFeed(item: FeedItem): GameRef {
  return {
    platform: item.platform,
    title_id: item.title_id,
    name: item.game,
    icon_url: item.game_icon_url,
    person: { person_id: item.person_id, name: item.person },
  };
}

/** Which secrets the reader opened, for this session. */
export const revealed = new Set<string>();

export function isVeiled(secret: boolean, key: string, showSecrets: boolean): boolean {
  return secret && !showSecrets && !revealed.has(key);
}

/** Whether the rarity is worth a mark: 10 % and under, as the posts' threshold. */
export function rareLevel(rarity: number | null): "ultra" | "rare" | null {
  if (rarity == null) return null;
  if (rarity <= 1) return "ultra";
  if (rarity <= 10) return "rare";
  return null;
}
