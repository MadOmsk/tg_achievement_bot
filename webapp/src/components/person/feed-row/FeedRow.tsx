import type { FeedItem } from "../../../api";
import { CoverImg, Icon } from "../../shared/lib";
import { HeroMarks } from "../hero-marks/HeroMarks";
import { ProgressBar } from "../progress-bar/ProgressBar";

/**
 * One achievement as a compact plate: icon, name, game with its progress
 * and the score/rarity. The profile's list and the stats drawers share it.
 */
export function FeedRow({
  row,
  secret,
  detailed = false,
  onOpen,
}: {
  row: FeedItem;
  secret: boolean;
  /** The drawer form: name, game and person, no progress. */
  detailed?: boolean;
  onOpen: (row: FeedItem) => void;
}) {
  // The frame marks the "platinum" of a game: a platinum trophy, or any
  // achievement of a game its owner has completed (100%).
  const done =
    row.trophy_type === "platinum" ||
    Boolean(
      row.progress &&
        row.progress.total > 0 &&
        row.progress.unlocked >= row.progress.total,
    );
  return (
    <button
      type="button"
      className={[
        "feed-row",
        secret ? "is-secret" : "",
        done ? "is-done" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      onClick={() => onOpen(row)}
    >
      <CoverImg
        src={row.icon_url}
        kind="achievement"
        className="feed-cover"
        imgClassName="cover"
      >
        {secret && (
          <span className="feed-lock">
            <Icon name="lock" size={18} />
          </span>
        )}
      </CoverImg>
      <span className="feed-copy">
        <span className="feed-copy-head">
          <p className="unlock-title">
            <span className={secret ? "secret-blur" : undefined}>{row.name}</span>
          </p>
          <HeroMarks
            compact
            score={row.gamerscore ? `${row.gamerscore} G` : null}
            tier={row.tier_badge ? row.trophy_type : null}
            rarity={
              row.rarity_percent != null ? `${row.rarity_percent}%` : null
            }
          />
        </span>
        <span className="feed-copy-foot">
          {row.game && (
            <p className="unlock-game">
              <span className="unlock-game-lead">
                <span className="unlock-game-name">{row.game}</span>
              </span>
              {!detailed && row.progress && row.progress.total > 0 && (
                <span className="unlock-game-count">
                  {row.progress.unlocked}/{row.progress.total}
                </span>
              )}
            </p>
          )}
          {detailed && row.person && (
            <p className="unlock-game unlock-person">
              <span className="unlock-game-name">{row.person}</span>
            </p>
          )}
          {!detailed && row.progress && row.progress.total > 0 && (
            <span className="feed-row-progress" aria-hidden="true">
              <ProgressBar progress={row.progress} hideCount />
            </span>
          )}
        </span>
      </span>
    </button>
  );
}
