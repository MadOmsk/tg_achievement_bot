import type { GameAchievement } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { Avatar, CoverImg, Icon } from "../../shared/lib";
import { HeroMarks } from "../../person";
import { pickLocale, trophyBadge } from "../utils";

export function GameAchievementRow({
  row,
  isRevealed,
  locale,
  onToggleReveal,
  onSelect,
  compare,
}: {
  row: GameAchievement;
  isRevealed: boolean;
  locale: Locale;
  onToggleReveal: (id: string) => void;
  onSelect: (row: GameAchievement) => void;
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

  const score = isSecret
    ? null
    : trophyBadge(row.trophy_type) || (row.gamerscore ? `${row.gamerscore} G` : null);
  const blur = isSecret ? "secret-blur" : undefined;

  const rarity = row.rarity_percent != null ? `${row.rarity_percent}%` : null;

  return (
    <button
      type="button"
      className={[
        "feed-row",
        isSecret ? "is-secret" : "",
        // The frame is for a platinum only; other earned ones look ordinary.
        row.trophy_type === "platinum" && row.is_unlocked ? "is-done" : "",
        row.is_unlocked ? "" : "is-locked-row",
      ]
        .filter(Boolean)
        .join(" ")}
      onClick={() => {
        if (isSecret) {
          onToggleReveal(row.achievement_id);
        } else {
          onSelect(row);
        }
      }}
    >
      <CoverImg
        src={row.icon_url}
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
          <HeroMarks compact score={score} rarity={rarity} />
        </span>
        {compare ? (
          <span className="compare-marks">
            {[compare.me, compare.them].map((who) => (
              <span
                key={who.id}
                className={who.has ? "compare-mark is-has" : "compare-mark"}
              >
                <Avatar name={who.name} tgId={who.id} size={24} />
              </span>
            ))}
          </span>
        ) : (
          desc && (
            <p className="unlock-game">
              <span className="unlock-game-lead">
                <span className="unlock-game-name">{desc || "\u00a0"}</span>
              </span>
            </p>
          )
        )}
      </span>
    </button>
  );
}
