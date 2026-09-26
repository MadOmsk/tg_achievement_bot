import { t, type Locale } from "../../../i18n";
import { CoverImg, FitImg, Icon } from "../../shared/lib";

/**
 * The top of a game's page: the picture across the full width (over a blurred
 * copy of itself for whatever its shape leaves bare), and along its lower edge
 * how far along the person is. Nothing else is written here — the name, the
 * platform and the counts are already in the bar and the heading below. A game
 * with every achievement earned gets a badge and the "platinum" colour.
 */
export function GameHero({
  cover,
  pct,
  isCompleted,
  locale,
}: {
  cover: string | null;
  pct: number;
  isCompleted: boolean;
  locale: Locale;
}) {
  return (
    <div className={isCompleted ? "game-hero is-done" : "game-hero"}>
      <div className="game-cover">
        <CoverImg src={cover} kind="game" className="game-cover-back" />
        <FitImg src={cover} mode="width" kind="game" />
        <span className="game-cover-bar" aria-hidden>
          <span
            className="game-cover-bar-fill"
            style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
          />
        </span>
      </div>
      {isCompleted && (
        <div className="game-medal">
          <span className="game-medal-disc" aria-hidden>
            <Icon name="cup" size={34} filled />
            <i className="game-medal-spark is-a" />
            <i className="game-medal-spark is-b" />
            <i className="game-medal-spark is-c" />
          </span>
          <span className="game-medal-label">
            {t(locale, "gameCompleted")}
          </span>
        </div>
      )}
    </div>
  );
}
