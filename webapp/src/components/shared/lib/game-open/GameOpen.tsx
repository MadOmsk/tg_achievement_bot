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

/** The game an achievement or a game card belongs to, as the game page wants it. */
export function gameRefOf(item: FeedItem): GameRef {
  return {
    platform: item.platform,
    title_id: item.title_id,
    name: item.game,
    icon_url: item.game_icon_url,
    person: item.tg_id ? { tg_id: item.tg_id, name: item.person } : null,
  };
}
