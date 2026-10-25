import type { GameCard } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { CoverImg, GlassWait, Row, RowsSection, useOpenGame } from "../../shared/lib";
import "./GameSearchHits.css";

/** The games a search found in our catalog; a tap opens the game's page. */
export function GameSearchHits({
  hits,
  busy,
  searched,
  locale,
}: {
  hits: GameCard[];
  busy: boolean;
  searched: boolean;
  locale: Locale;
}) {
  const openGame = useOpenGame();
  if (!busy && !searched) return null;
  return (
    <div className="game-hits">
      <RowsSection title={t(locale, "games")}>
        {busy && hits.length === 0 ? (
          <GlassWait />
        ) : hits.length === 0 ? (
          <p className="empty">{t(locale, "gpSearchEmpty")}</p>
        ) : (
          hits.map((hit) => (
            <Row
              key={hit.game_id}
              lead={<CoverImg src={hit.poster} kind="game" className="rows-art is-cover" />}
              title={(locale === "ru" && hit.name_ru) || hit.name}
              subtitle={hit.year ? String(hit.year) : undefined}
              onClick={
                openGame
                  ? () =>
                      openGame({ game_id: hit.game_id, platform: "", title_id: "", name: hit.name })
                  : undefined
              }
            />
          ))
        )}
      </RowsSection>
    </div>
  );
}
