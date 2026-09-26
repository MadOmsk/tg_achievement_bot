import { t, type Locale } from "../../../i18n";
import { CoverImg, FitImg, Icon } from "../../shared/lib";

/**
 * The top of a game's page: the picture across the full width (over a blurred
 * copy of itself for whatever its shape leaves bare) and, hanging off its lower
 * edge, how far along the person is — a plate with the percentage, a bar and
 * the count. A game with every achievement earned gets a big platinum medal
 * with a glow and sparkles instead of the plate.
 */
export function GameHero({
  cover,
  pct,
  unlocked,
  total,
  isCompleted,
  locale,
}: {
  cover: string | null;
  pct: number;
  unlocked: number;
  total: number;
  isCompleted: boolean;
  locale: Locale;
}) {
  const width = `${Math.min(100, Math.max(0, pct))}%`;
  return (
    <div className={isCompleted ? "game-hero is-done" : "game-hero"}>
      <div className="game-cover">
        <CoverImg src={cover} kind="game" className="game-cover-back" />
        <FitImg src={cover} mode="width" kind="game" />
      </div>
      {isCompleted ? (
        <div className="game-medal">
          <span className="game-medal-disc" aria-hidden>
            <Icon name="cup" size={52} filled />
            <i className="game-medal-spark is-a" />
            <i className="game-medal-spark is-b" />
            <i className="game-medal-spark is-c" />
            <i className="game-medal-spark is-d" />
          </span>
          <span className="game-medal-label">{t(locale, "gameCompleted")}</span>
          <span className="game-medal-count">
            {unlocked} / {total}
          </span>
        </div>
      ) : (
        total > 0 && (
          <div className="game-plate">
            <strong>{pct}%</strong>
            <span className="game-plate-bar" aria-hidden>
              <span className="game-plate-fill" style={{ width }} />
            </span>
            <small>
              {unlocked} / {total}
            </small>
          </div>
        )
      )}
    </div>
  );
}
