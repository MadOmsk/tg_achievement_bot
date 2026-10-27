import type { GameCard } from "../api/game/gameApiModels";
import { useApp } from "../app/context";
import { Icon } from "../ui/Icon";
import { GameTile } from "./GameTile";

/** A person's favorite games as a rail of game tiles, each with its heart; on
 * one's own Home a last card says how to add one. */
export function FavoriteGames({ games, hint }: { games: GameCard[]; hint?: string }) {
  const { locale, open } = useApp();
  return (
    <div className="rail favs">
      {games.map((g) => (
        <GameTile
          key={g.game_id}
          cover={g.poster || g.hero}
          name={locale === "ru" && g.name_ru ? g.name_ru : g.name}
          mark={
            <span className="fav-heart shape-cookie9">
              <Icon name="heart" size={18} filled />
            </span>
          }
          onOpen={() => open({ kind: "game", ref: { game_id: g.game_id, platform: "", title_id: "", name: g.name } })}
        />
      ))}
      {hint && <div className="fav-hint">{hint}</div>}
    </div>
  );
}
