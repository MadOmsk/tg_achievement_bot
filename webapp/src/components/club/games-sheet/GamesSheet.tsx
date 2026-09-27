import type { SummaryGame } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { CoverImg, Sheet, useOpenGame } from "../../shared/lib";

export function GamesSheet({
  games,
  locale,
  onClose,
}: {
  games: SummaryGame[];
  locale: Locale;
  onClose: () => void;
}) {
  const openGame = useOpenGame();
  return (
    <Sheet onClose={onClose} closeLabel={t(locale, "close")} noClose mid>
      <div className="sheet-content score-sheet picker-sheet games-sheet">
        <h2>{t(locale, "monthGames")}</h2>
        <div className="picker-list games-sheet-list">
          {games.map((g) => {
            const meta = [
              `${g.count} ${t(locale, "achievements")}`,
              (g.score > 0) && `+${g.score} G`,
            ]
              .filter(Boolean)
              .join(" · ");
            return (
              <button
                key={`${g.platform}:${g.title_id}`}
                type="button"
                className="picker-row is-game"
                onClick={() =>
                  openGame?.({
                    platform: g.platform,
                    title_id: g.title_id,
                    name: g.name,
                    icon_url: g.icon_url,
                  })
                }
              >
                <span className="picker-game-art">
                  <CoverImg
                    src={g.icon_url}
                    kind="game"
                    className="picker-game-cover"
                  />
                </span>
                <span className="picker-row-copy">
                  <strong>{g.name || "—"}</strong>
                  <p>{meta}</p>
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </Sheet>
  );
}
