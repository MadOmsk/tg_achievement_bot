import type { FeedItem } from "../../../api";

export function ProgressBar({
  progress,
  hideCount,
}: {
  progress: FeedItem["progress"];
  /** The compact feed row shows the count in its own title row instead —
   * see FeedList.tsx — so the bar here needs to render on its own. */
  hideCount?: boolean;
}) {
  if (!progress || progress.total <= 0) return null;
  const total = progress.total;
  const unlocked = progress.unlocked;
  const pct = Math.min(100, (100 * unlocked) / total);
  const done = unlocked >= total;
  return (
    <span className={done ? "hero-game-bar-row is-done" : "hero-game-bar-row"}>
      <span className="hero-game-bar" aria-hidden="true">
        <span className="hero-game-bar-fill" style={{ width: `${pct}%` }} />
      </span>
      {!hideCount && (
        <span className="hero-game-count">
          {unlocked}/{total}
        </span>
      )}
    </span>
  );
}
