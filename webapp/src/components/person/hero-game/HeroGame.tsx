import type { FeedItem } from "../../../api";
import { en, ru, t, type Locale } from "../../../i18n";
import { CoverImg, gameRefOf, useOpenGame } from "../../shared/lib";
import { ProgressBar } from "../progress-bar/ProgressBar";

// The server names a title's base trophy group after the game itself or,
// for PSN, literally "Основная игра"/"Main Game" (see services/achievements.py
// on the bot side) — either way it repeats the game name already on the line
// above, so it's suppressed rather than shown twice. Compared against both
// locale catalogs' own "mainGame" string, not a hand-copied literal, so a
// wording change on either side can't silently reopen this gap.
const MAIN_GROUP_NAMES = [ru.mainGame.toLowerCase(), en.mainGame.toLowerCase()];

export function HeroGame({
  item,
  locale,
  link = false,
}: {
  item: FeedItem;
  locale?: Locale;
  /** Tapping the block opens the game's own page. */
  link?: boolean;
}) {
  const openGame = useOpenGame();
  if (!item.game && !item.platform) return null;
  const progress = item.progress;
  const showBar = Boolean(progress && progress.total > 0);
  const group = progress?.group;
  const showGroup = Boolean(
    group &&
      group.name &&
      !group.is_default &&
      !MAIN_GROUP_NAMES.includes(group.name.trim().toLowerCase()),
  );
  const dlc = Boolean(progress?.has_dlc && locale);
  const canOpen = Boolean(link && openGame && item.title_id);
  return (
    <span
      className={
        ["hero-game", showGroup ? "has-mid" : "", canOpen ? "is-link" : ""]
          .filter(Boolean)
          .join(" ")
      }
      role={canOpen ? "button" : undefined}
      onClick={
        canOpen
          ? (e) => {
              e.stopPropagation();
              openGame?.(gameRefOf(item));
            }
          : undefined
      }
    >
      {(item.game || item.game_icon_url) && (
        <CoverImg
          src={item.game_icon_url}
          kind="game"
          className="hero-game-art"
        >
          {dlc && locale && <span className="dlc-badge">{t(locale, "dlcBadge")}</span>}
        </CoverImg>
      )}
      <span className="hero-game-text">
        <span className="hero-game-head">
          {item.game && (
            <span className="hero-game-name">
              <strong className="hero-game-title">{item.game}</strong>
            </span>
          )}
          {showBar && progress && (
            <span className="hero-game-count">
              {progress.unlocked}/{progress.total}
            </span>
          )}
        </span>
        {showGroup && group && (
          <span className="hero-game-mid">
            <span className="hero-game-group">{group.name}</span>
          </span>
        )}
        {showBar && <ProgressBar progress={progress} hideCount />}
      </span>
    </span>
  );
}
