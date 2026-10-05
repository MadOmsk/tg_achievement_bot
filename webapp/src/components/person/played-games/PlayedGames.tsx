import type { CSSProperties } from "react";
import type { FeedItem } from "../../../api";
import { t, timeAgo, type Locale } from "../../../i18n";
import { CoverImg, gameRefOf, useOpenGame } from "../../shared/lib";
import "./PlayedGames.css";

interface Played {
  key: string;
  last: FeedItem;
  count: number;
}

/**
 * A person's games for the month, the one with the newest achievement first
 * (the feed arrives newest first, so the order of first appearance is it).
 * Each row: the cover, the name with how far along they are, and the progress
 * bar — its last stretch, the part earned this month, bright, the
 * older part toned down — then this month's gain and when the last
 * achievement came. A finished game is platinum. A tap opens the game's page
 * with their progress.
 */
export function PlayedGames({
  items,
  locale,
  sort = "recent",
}: {
  items: FeedItem[];
  locale: Locale;
  /** "recent" keeps the feed's own newest-first order; "progress" ranks by completion percentage, games with no known total last. */
  sort?: "recent" | "progress";
}) {
  const openGame = useOpenGame();
  const games = new Map<string, Played>();
  for (const row of items) {
    if (!row.game) continue;
    const key = `${row.platform}:${row.title_id}`;
    const cur = games.get(key);
    if (cur) cur.count += 1;
    else games.set(key, { key, last: row, count: 1 });
  }
  const ordered = [...games.values()];
  if (sort === "progress") {
    ordered.sort((a, b) => {
      const ap = a.last.progress;
      const bp = b.last.progress;
      const aPct = ap && ap.total > 0 ? ap.unlocked / ap.total : -1;
      const bPct = bp && bp.total > 0 ? bp.unlocked / bp.total : -1;
      return bPct - aPct;
    });
  }
  return (
    <div className="played-games">
      {ordered.map(({ key, last, count }) => {
        const progress = last.progress;
        const known = Boolean(progress && progress.total > 0);
        const done = Boolean(progress && known && progress.unlocked >= progress.total);
        return (
          <button
            key={key}
            type="button"
            className={done ? "played-game is-done" : "played-game"}
            onClick={openGame ? () => openGame(gameRefOf(last)) : undefined}
          >
            <CoverImg
              src={last.game_icon_url}
              kind="game"
              className="played-game-cover"
            />
            <span className="played-game-body">
              <span className="played-game-head">
                <strong>{last.game}</strong>
                {known && progress && (
                  <span className="played-game-count">
                    {progress.unlocked}/{progress.total}
                  </span>
                )}
              </span>
              {known && progress && (
                <span className="played-bar" aria-hidden>
                  <span
                    className="played-bar-fill"
                    style={
                      {
                        width: `${(100 * progress.unlocked) / progress.total}%`,
                        "--month": `${(100 * Math.min(count, progress.unlocked)) / progress.unlocked}%`,
                      } as CSSProperties
                    }
                  />
                </span>
              )}
              {/* When the last one came at the left, this month's gain at the right. */}
              <span className="played-game-when">
                {timeAgo(last.unlocked_at, locale)}
                <span className="played-game-gain">
                  +{count} {t(locale, "gainThisMonth")}
                </span>
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
