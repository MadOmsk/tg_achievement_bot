import type { CSSProperties } from "react";
import type { FeedItem } from "../../../api";
import { timeAgo, type Locale } from "../../../i18n";
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
 * Each row: the cover, the name with their overall count, and the progress
 * bar — its last stretch, the part earned this month, stays bright while the
 * older part is toned down — and
 * when the last achievement came. A tap opens
 * the game's page with their progress.
 */
export function PlayedGames({
  items,
  locale,
}: {
  items: FeedItem[];
  locale: Locale;
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
  return (
    <div className="played-games">
      {[...games.values()].map(({ key, last, count }) => {
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
              <span className="played-game-when">
                {timeAgo(last.unlocked_at, locale)}
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
