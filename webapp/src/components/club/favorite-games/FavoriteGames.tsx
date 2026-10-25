import { useEffect, useState } from "react";
import { gameApi, type GameCard } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { CoverImg, Icon, useOpenGame } from "../../shared/lib";
import "./FavoriteGames.css";

/** Sent when a heart is set or taken off on a game's page: the strips on
 * screen read their list again. */
export const FAVORITES_CHANGED = "favorite-games-changed";

export function announceFavoritesChanged(): void {
  window.dispatchEvent(new Event(FAVORITES_CHANGED));
}

/**
 * A person's favorite games, as a strip under whom they follow (owner,
 * 2026-10-25): the latest first, a tap opens the game. One's own strip says
 * how to fill it when empty; somebody else's empty one is not shown.
 */
export function FavoriteGames({
  data,
  locale,
  personId,
  own,
}: {
  data: string;
  locale: Locale;
  /** Whose; none for one's own. */
  personId?: number | null;
  own: boolean;
}) {
  const openGame = useOpenGame();
  const [games, setGames] = useState<GameCard[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      gameApi
        .favorites(data, own ? null : personId)
        .then((answer) => {
          if (!cancelled) setGames(answer.games);
        })
        .catch(() => {
          if (!cancelled) setGames([]);
        });
    void load();
    window.addEventListener(FAVORITES_CHANGED, load);
    return () => {
      cancelled = true;
      window.removeEventListener(FAVORITES_CHANGED, load);
    };
  }, [data, own, personId]);

  if (games === null || (games.length === 0 && !own)) return null;
  return (
    <>
      <div className="section-head">
        <span className="section-title-group">
          <h1 className="kicker" style={{ margin: 0 }}>
            {t(locale, "gpFavoritesTitle")}
          </h1>
          {games.length > 0 && <span className="section-count">{games.length}</span>}
        </span>
      </div>
      {games.length === 0 ? (
        <div className="fav-games-empty">
          <Icon name="heart" size={20} />
          <p>{t(locale, "gpFavoritesEmpty")}</p>
        </div>
      ) : (
        <div className="fav-games">
          {games.map((game) => (
            <button
              key={game.game_id}
              type="button"
              className="fav-game"
              onClick={
                openGame
                  ? () =>
                      openGame({ game_id: game.game_id, platform: "", title_id: "", name: game.name })
                  : undefined
              }
            >
              <CoverImg src={game.poster} kind="game" className="fav-game-art" />
              <strong>{(locale === "ru" && game.name_ru) || game.name}</strong>
            </button>
          ))}
        </div>
      )}
    </>
  );
}
