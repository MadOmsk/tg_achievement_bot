import { createContext, useContext } from "react";
import type { FeedItem, GameRef } from "../../../../api";

type OpenGame = (game: GameRef) => void;

/**
 * Whoever renders the game page provides this; a card just asks to open one.
 * Without a provider the game block simply isn't a link.
 */
export const GameOpenContext = createContext<OpenGame | null>(null);

export function useOpenGame(): OpenGame | null {
  return useContext(GameOpenContext);
}

type OpenAchievement = (item: FeedItem) => void;

/**
 * Opens an achievement's own page over everything (owner, 2026-10-09): a tap
 * on a post or a gallery card. Its game opens only from the game's own line.
 */
export const AchievementOpenContext = createContext<OpenAchievement | null>(null);

export function useOpenAchievement(): OpenAchievement | null {
  return useContext(AchievementOpenContext);
}

/** The game an achievement or a game card belongs to, as the game page wants it. */
export function gameRefOf(item: FeedItem): GameRef {
  return {
    platform: item.platform,
    title_id: item.title_id,
    name: item.game,
    icon_url: item.game_icon_url,
    person: item.person_id ? { person_id: item.person_id, name: item.person } : null,
  };
}
