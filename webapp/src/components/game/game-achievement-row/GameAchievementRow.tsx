import { useEffect, useRef } from "react";
import type { AchievementTip, GameAchievement } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { Avatar, CoverImg, Icon } from "../../shared/lib";
import { HeroMarks } from "../../person";
import { pickLocale } from "../utils";
import { RichLines } from "../rich-text/RichText";

const SETTLE_MS = 340;
const BREATHING_ROOM = 10;

/** A card that opens or closes changes the page's height: a big one closed leaves
 * its top above the screen, under the bar. Once it has settled, its top is brought
 * back into view. */
function useKeepInView(open: boolean) {
  const ref = useRef<HTMLDivElement>(null);
  const mounted = useRef(false);
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    const id = window.setTimeout(() => {
      const row = ref.current;
      const page = row?.closest<HTMLElement>(".game-page");
      if (!row || !page) return;
      const bar = page.querySelector<HTMLElement>(".person-bar");
      const floor = (bar?.getBoundingClientRect().bottom ?? 0) + BREATHING_ROOM;
      const top = row.getBoundingClientRect().top;
      if (top < floor) page.scrollBy({ top: top - floor, behavior: "smooth" });
    }, SETTLE_MS);
    return () => window.clearTimeout(id);
  }, [open]);
  return ref;
}

export function GameAchievementRow({
  row,
  isRevealed,
  locale,
  onToggleReveal,
  compare,
  fallbackIcon,
  tip,
  open,
  onToggleTip,
}: {
  row: GameAchievement;
  isRevealed: boolean;
  locale: Locale;
  onToggleReveal: (id: string) => void;
  /** Shown when the achievement has no picture of its own (most catalog rows do not). */
  fallbackIcon?: string | null;
  /** What the Steam guides say about getting this achievement; a row without one does not open. */
  tip?: AchievementTip;
  /** Whether its tip is showing — the page keeps one open at a time in a group. */
  open: boolean;
  onToggleTip: (id: string) => void;
  /** Both people's state on this achievement (the compare view). */
  compare?: {
    me: { id: number; name: string; has: boolean };
    them: { id: number; name: string; has: boolean };
  };
}) {
  const isSecret = row.is_secret && !isRevealed;
  const rowRef = useKeepInView(open);

  const name =
    pickLocale(locale, row.name_ru, row.name_en, row.achievement_id) ||
    t(locale, "secret");

  const desc = pickLocale(locale, row.description_ru, row.description_en);

  const score = row.gamerscore ? `${row.gamerscore} G` : null;
  const blur = isSecret ? "secret-blur" : undefined;

  const rarity = row.rarity_percent != null ? `${row.rarity_percent}%` : null;

  // A secret still needs a tap to reveal it; after that (or straight away for
  // an ordinary row) a row with a tip opens to it, in its own card.
  const canOpen = !isSecret && !compare && tip !== undefined;
  const onTap = isSecret
    ? () => onToggleReveal(row.achievement_id)
    : canOpen
      ? () => onToggleTip(row.achievement_id)
      : undefined;

  return (
    <div
      ref={rowRef}
      role={onTap ? "button" : undefined}
      tabIndex={onTap ? 0 : undefined}
      onKeyDown={
        onTap
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") onTap();
            }
          : undefined
      }
      className={[
        "feed-row",
        "has-wrap",
        isSecret ? "is-secret" : "",
        canOpen ? "has-tip" : "",
        open && canOpen ? "is-open swiper-no-swiping" : "",
        row.is_unlocked ? "" : "is-locked-row",
      ]
        .filter(Boolean)
        .join(" ")}
      aria-expanded={canOpen ? open : undefined}
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
                <Avatar name={who.name} tgId={who.id} size={24} />
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
        {canOpen && (
          <span className="feed-tip-mark" aria-hidden>
            <Icon name="guide" size={16} />
          </span>
        )}
      </span>
      {canOpen && tip && (
        <span className="ach-tip">
          <span className="ach-tip-inner">
            <span className="ach-tip-body">
              <RichLines text={tip.text} className="ach-tip-line" />
            </span>
          </span>
        </span>
      )}
    </div>
  );
}
