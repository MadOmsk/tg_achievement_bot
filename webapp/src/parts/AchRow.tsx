import { useState, type ReactNode } from "react";
import { useApp } from "../app/context";
import type { AchView } from "../app/layers";
import { isVeiled, pointsOf, rareLevel, revealed, TIER_NAME } from "../app/views";
import { num, pct } from "../i18n";
import { tick } from "../core/haptic";
import { AchPic } from "../ui/Pic";
import "./parts.css";

/** Xbox One/Series pictures are 16:9 art; every other platform's are square. */
export function isWideArt(platform: string): boolean {
  return platform === "xbox_modern";
}

/** The app's own points as a coin of its own: the logo's sparkle and the
 * number beside it — what an achievement is worth, at a glance. */
export function PointsCoin({ points, total, className = "" }: { points: number; total?: number; className?: string }) {
  const { tr, locale } = useApp();
  return (
    <span className={`pts-coin ${className}`} aria-label={`${points} ${tr("ptsMany")}`}>
      <Spark className="pts-coin-spark" />
      <b className="t-num">
        {num(points, locale)}
        {total != null && <small> / {num(total, locale)}</small>}
      </b>
    </span>
  );
}

/** The logo's four-point sparkle: the mark of the app's points. */
export function Spark({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path d="M12 2c.6 5.2 4.8 9.4 10 10-5.2.6-9.4 4.8-10 10-.6-5.2-4.8-9.4-10-10 5.2-.6 9.4-4.8 10-10z" />
    </svg>
  );
}

/** What an achievement is worth and how rare, on one scale for every
 * platform: the app's own points, then its tier — rare, legendary, mythic — or
 * its share. A PSN trophy's metal is not shown: its tier says it. */
export function AchMarks({
  ach,
  size = "s",
  plain = false,
  date,
  extra,
  noWorth = false,
}: {
  ach: Pick<AchView, "trophy" | "gamerscore" | "rarity" | "mythic">;
  /** The coin is shown elsewhere in the row (its right column). */
  noWorth?: boolean;
  size?: "s" | "m";
  /** A line of text instead of chips, where many rows sit together. */
  plain?: boolean;
  /** When it was earned, at the end of that line. */
  date?: string | null;
  /** Marks of the row's own (who has it, its guides), last on that line. */
  extra?: ReactNode;
}) {
  const { locale } = useApp();
  const tier = rareLevel(ach.rarity, ach);
  if (plain) {
    const pts = pointsOf(ach.rarity, ach);
    const worth = noWorth ? null : <PointsCoin points={pts} />;
    // A row with its own column (`noWorth`) names its rarity above its title.
    const rarity =
      !noWorth && (ach.rarity != null || tier === "mythic") ? (
        <span className={`mark-rarity${tier ? ` mark-${tier}` : ""}`}>
          {tier && <span className="rare-mark shape-flower6" />}
          {ach.rarity != null ? pct(ach.rarity, locale) : null}
        </span>
      ) : null;
    const parts = [worth, rarity, date ? <span className="mark-date">{date}</span> : null, extra ?? null].filter(Boolean);
    if (!parts.length) return null;
    return (
      <span className="marks-plain">
        {parts.map((part, i) => (
          <span key={i} className="mark-part">
            {i > 0 && !(i === 1 && !noWorth) && <span className="mark-dot">·</span>}
            {part}
          </span>
        ))}
      </span>
    );
  }
  return (
    <span className={`marks marks-${size}`}>
      <PointsCoin points={pointsOf(ach.rarity, ach)} />
      {(ach.rarity != null || tier === "mythic") && (
        <span className={`chip ${tier ? `chip-tier chip-tier-${tier}` : "chip-outline"}`}>
          {tier && <span className="rare-mark shape-flower6" />}
          {ach.rarity != null ? pct(ach.rarity, locale) : null}
        </span>
      )}
    </span>
  );
}

/** One achievement in a list: picture, name, description, marks. A tap opens
 * its page; a secret one is veiled until the first tap reveals it. */
export function AchRow({
  ach,
  showDescription = true,
  compact = false,
  plain = false,
  date,
  when,
  extra,
  trail,
}: {
  ach: AchView;
  showDescription?: boolean;
  compact?: boolean;
  plain?: boolean;
  date?: string | null;
  /** When it was earned, in a column of its own on the right, as a news row's day is. */
  when?: string | null;
  extra?: ReactNode;
  trail?: ReactNode;
}) {
  const { tr, open, me, locale } = useApp();
  const [, setTick] = useState(0);
  const veiled = isVeiled(ach.secret, ach.key, me.settings.show_secrets);
  const wide = isWideArt(ach.platform);
  return (
    <button
      type="button"
      className={`ach-row${compact ? " ach-row-compact" : ""}${plain ? " ach-row-plain" : ""}`}
      onClick={() => {
        tick();
        if (veiled) {
          revealed.add(ach.key);
          setTick((n) => n + 1);
          return;
        }
        open({ kind: "achievement", ach });
      }}
    >
      {when !== undefined ? (
        // What it is worth on a flower at the picture's corner, as a post's is.
        <span className="ach-pic-wrap">
          <AchPic src={ach.icon} className={wide ? "ach-pic-wide" : "ach-pic-square"} veiled={veiled} />
          <span className={`ach-flower shape-flower6 tile-badge-${rareLevel(ach.rarity, ach) ?? "plain"}`}>
            <b className="t-num flower-pts">
              <Spark className="flower-spark" />
              {pointsOf(ach.rarity, ach)}
            </b>
          </span>
        </span>
      ) : (
        <AchPic src={ach.icon} className={wide ? "ach-pic-wide" : "ach-pic-square"} veiled={veiled} />
      )}
      <span className="ach-text">
        {when !== undefined && (
          // Its rarity above the title, as a post's is.
          <span className={`ach-kicker${rareLevel(ach.rarity, ach) ? ` mark-${rareLevel(ach.rarity, ach)}` : ""}`}>
            {tierWord(tr(TIER_NAME[rareLevel(ach.rarity, ach) ?? "common"]))}
            {ach.rarity != null && ` · ${pct(ach.rarity, locale)}`}
          </span>
        )}
        <span className="ach-name clamp-2">{veiled ? tr("secretAchievement") : ach.name}</span>
        {showDescription && (veiled || ach.description) && (
          <span className={`ach-desc clamp-2${ach.translating && !veiled ? " translating" : ""}`}>{veiled ? tr("secretTapToReveal") : ach.description}</span>
        )}
        <AchMarks ach={ach} plain={plain} date={date} extra={extra} noWorth={when !== undefined} />
      </span>
      {/* When it came, at the top of a column of its own. */}
      {when && (
        <span className="ach-side">
          <span className="t-meta">{when}</span>
        </span>
      )}
      {trail}
    </button>
  );
}

const tierWord = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export const PLATFORM_SHORT: Record<string, string> = {
  xbox_modern: "XBOX",
  xbox_360: "XBOX 360",
  xbox: "XBOX",
  psn: "PS",
  steam: "STEAM",
};

export function PlatformTag({ platform }: { platform: string }) {
  return <span className="ptag">{PLATFORM_SHORT[platform] ?? platform.toUpperCase()}</span>;
}
