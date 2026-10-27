import type { GameCard } from "../api/game/gameApiModels";
import { useApp } from "../app/context";
import { tick } from "../core/haptic";
import { Icon } from "../ui/Icon";
import { Cover } from "../ui/Pic";

/** A person's favorite games as a rail of covers, each with its heart; on
 * one's own Home a last card says how to add one. */
export function FavoriteGames({ games, hint }: { games: GameCard[]; hint?: string }) {
  const { locale, open } = useApp();
  return (
    <div className="rail favs">
      {games.map((g) => (
        <button
          key={g.game_id}
          type="button"
          className="fav-card"
          onClick={() => {
            tick();
            open({ kind: "game", ref: { game_id: g.game_id, platform: "", title_id: "", name: g.name } });
          }}
        >
          <span className="fav-art">
            <Cover src={g.poster || g.hero} className="fav-cover" alt={g.name} />
            <span className="fav-heart shape-cookie9">
              <Icon name="heart" size={18} filled />
            </span>
          </span>
          <span className="fav-name clamp-2">{locale === "ru" && g.name_ru ? g.name_ru : g.name}</span>
        </button>
      ))}
      {hint && <div className="fav-hint">{hint}</div>}
    </div>
  );
}
