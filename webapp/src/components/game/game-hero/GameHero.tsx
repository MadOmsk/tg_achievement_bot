import { t, type Locale } from "../../../i18n";
import { CoverImg, FitImg, Icon } from "../../shared/lib";

/**
 * The top of a game's page: the picture across the full width (over a blurred
 * copy of itself for whatever its shape leaves bare) and, hanging off its lower
 * edge, how far along the person is — a plate with an achievement icon, a bar and
 * the percentage. A game with every achievement earned gets a big platinum medal
 * on a glow instead of the plate, with light rays, a passing shine and a lit
 * edge across the picture.
 */
export function GameHero({
  cover,
  pct,
  total,
  isCompleted,
  loading = false,
  locale,
  compact = false,
}: {
  cover: string | null;
  pct: number;
  total: number;
  isCompleted: boolean;
  /** The game is still being fetched: an empty plate stands in. */
  loading?: boolean;
  locale: Locale;
  /** Collapsed (HeroPeek at rest): a plain platinum plate instead of the big
   * glowing medal — the rays and shine are sized for the full picture and
   * only make sense once it's actually open. */
  compact?: boolean;
}) {
  const width = `${Math.min(100, Math.max(0, pct))}%`;
  const done = isCompleted && !loading;
  return (
    <div
      className={[
        "game-hero",
        done && "is-done",
        done && compact && "is-compact",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <div className="game-cover">
        <CoverImg src={cover} kind="game" className="game-cover-back" />
        <FitImg src={cover} mode="width" kind="game" />
        {done && !compact && (
          <>
            <i className="game-rays" aria-hidden />
            <i className="game-shine" aria-hidden />
            <i className="game-edge" aria-hidden />
          </>
        )}
      </div>
      {done && compact ? (
        <div className="game-plate is-platinum">
          <span className="game-plate-icon" aria-hidden>
            <Icon name="cup" size={26} filled />
          </span>
          <span className="game-plate-bar is-platinum" aria-hidden>
            <span className="game-plate-fill is-platinum" style={{ width: "100%" }} />
          </span>
          <strong>100%</strong>
        </div>
      ) : done ? (
        <div className="game-medal">
          <span className="game-medal-disc" aria-hidden>
            <Icon name="cup" size={52} filled />
          </span>
          <span className="game-medal-label">{t(locale, "gameCompleted")}</span>
        </div>
      ) : (
        (loading || total > 0) && (
          <div className="game-plate">
            <span className="game-plate-icon" aria-hidden>
              <Icon name="cup" size={26} filled />
            </span>
            <span className="game-plate-bar" aria-hidden>
              <span className="game-plate-fill" style={{ width: loading ? "0%" : width }} />
            </span>
            {loading ? (
              <span className="skel game-plate-pct" aria-hidden />
            ) : (
              <strong>{pct}%</strong>
            )}
          </div>
        )
      )}
    </div>
  );
}
