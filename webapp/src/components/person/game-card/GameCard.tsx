import type { FeedItem } from "../../../api";
import { CoverImg, FitImg, gameRefOf, useOpenGame } from "../../shared/lib";

/**
 * A game in the profile's gallery: just its picture, nothing written on it.
 * A tap opens the game's page (with this person's progress first).
 */
export function GameCard({ item }: { item: FeedItem }) {
  const cover = item.game_icon_url || item.icon_url;
  const openGame = useOpenGame();
  const canOpen = Boolean(openGame && item.title_id);
  return (
    <div
      className={canOpen ? "unlock-card game-card has-fit is-link" : "unlock-card game-card has-fit"}
      role={canOpen ? "button" : undefined}
      onClick={canOpen ? () => openGame?.(gameRefOf(item)) : undefined}
    >
      <div className="unlock-card-art">
        <CoverImg src={cover} kind="game" className="game-card-art" />
      </div>
      <div className="unlock-card-fit">
        <FitImg src={cover} kind="game" />
      </div>
    </div>
  );
}
