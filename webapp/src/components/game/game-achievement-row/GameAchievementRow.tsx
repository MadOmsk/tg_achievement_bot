import type { AchievementTip, GameAchievement } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { Avatar, CoverImg, Icon } from "../../shared/lib";
import { HeroMarks } from "../../person";
import { pickLocale } from "../utils";

export function GameAchievementRow({
  row,
  isRevealed,
  locale,
  onToggleReveal,
  compare,
  fallbackIcon,
  tip,
  onOpen,
}: {
  row: GameAchievement;
  isRevealed: boolean;
  locale: Locale;
  onToggleReveal: (id: string) => void;
  /** Shown when the achievement has no picture of its own (most catalog rows do not). */
  fallbackIcon?: string | null;
  /** What the Steam guides say about getting it: the row is marked, its page shows it. */
  tip?: AchievementTip;
  /** Opens the achievement's own page (AchievementPage). */
  onOpen: (id: string) => void;
  /** Both people's state on this achievement (the compare view). */
  compare?: {
    me: { id: number; name: string; has: boolean };
    them: { id: number; name: string; has: boolean };
  };
}) {
  const isSecret = row.is_secret && !isRevealed;

  const name =
    pickLocale(locale, row.name_ru, row.name_en, row.achievement_id) ||
    t(locale, "secret");

  const desc = pickLocale(locale, row.description_ru, row.description_en);

  const score = row.gamerscore ? `${row.gamerscore} G` : null;
  const blur = isSecret ? "secret-blur" : undefined;

  const rarity = row.rarity_percent != null ? `${row.rarity_percent}%` : null;

  // A secret still needs a tap to reveal it; after that (or straight away for
  // an ordinary row) a tap opens the achievement's own page.
  const onTap = isSecret
    ? () => onToggleReveal(row.achievement_id)
    : () => onOpen(row.achievement_id);
  const hasTip = !isSecret && tip !== undefined;

  return (
    <div
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") onTap();
      }}
      className={[
        "feed-row",
        "has-wrap",
        isSecret ? "is-secret" : "",
        hasTip ? "has-tip" : "",
        row.is_unlocked ? "" : "is-locked-row",
      ]
        .filter(Boolean)
        .join(" ")}
      onClick={onTap}
    >
      <CoverImg
        src={row.icon_url || fallbackIcon}
        kind="achievement"
        className="feed-cover"
        imgClassName="cover"
      >
        {isSecret && (
          <span className="feed-lock">
            <Icon name="lock" size={18} />
          </span>
        )}
      </CoverImg>
      <span className="feed-copy">
        <span className="feed-copy-head">
          <p className="unlock-title">
            <span className={blur}>{name}</span>
          </p>
          <HeroMarks
            compact
            score={score}
            rarity={rarity}
            tier={row.trophy_type}
          />
        </span>
        {compare ? (
          <span className="compare-marks">
            {[compare.me, compare.them].map((who) => (
              <span
                key={who.id}
                className={who.has ? "compare-mark is-has" : "compare-mark"}
              >
                <Avatar name={who.name} personId={who.id} size={24} />
              </span>
            ))}
          </span>
        ) : (
          desc && (
            <p className="unlock-game">
              <span className="unlock-game-lead">
                <span
                  className={
                    blur ? `unlock-game-name ${blur}` : "unlock-game-name"
                  }
                >
                  {desc}
                </span>
              </span>
            </p>
          )
        )}
        {hasTip && (
          <span className="feed-tip-mark" aria-hidden>
            <Icon name="guide" size={16} />
          </span>
        )}
      </span>
    </div>
  );
}
