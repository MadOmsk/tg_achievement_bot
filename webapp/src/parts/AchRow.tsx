import { useState, type ReactNode } from "react";
import { useApp } from "../app/context";
import type { AchView } from "../app/layers";
import { isVeiled, pointsOf, rareLevel, revealed } from "../app/views";
import { num, pct, plural } from "../i18n";
import { tick } from "../core/haptic";
import { AchPic } from "../ui/Pic";
import "./parts.css";

/** Xbox One/Series pictures are 16:9 art; every other platform's are square. */
export function isWideArt(platform: string): boolean {
  return platform === "xbox_modern";
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
}: {
  ach: Pick<AchView, "trophy" | "gamerscore" | "rarity" | "mythic">;
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
    const worth = <span className="mark-worth">{num(pts, locale)} {plural(locale, pts, ["ptsOne", "ptsFew", "ptsMany"])}</span>;
    const rarity =
      ach.rarity != null || tier === "mythic" ? (
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
            {i > 0 && <span className="mark-dot">·</span>}
            {part}
          </span>
        ))}
      </span>
    );
  }
  return (
    <span className={`marks marks-${size}`}>
      <span className="chip chip-outline">
        {num(pointsOf(ach.rarity, ach), locale)} {plural(locale, pointsOf(ach.rarity, ach), ["ptsOne", "ptsFew", "ptsMany"])}
      </span>
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
  extra,
  trail,
}: {
  ach: AchView;
  showDescription?: boolean;
  compact?: boolean;
  plain?: boolean;
  date?: string | null;
  extra?: ReactNode;
  trail?: ReactNode;
}) {
  const { tr, open, me } = useApp();
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
      <AchPic src={ach.icon} className={wide ? "ach-pic-wide" : "ach-pic-square"} veiled={veiled} />
      <span className="ach-text">
        <span className="ach-name clamp-2">{veiled ? tr("secretAchievement") : ach.name}</span>
        {showDescription && (veiled || ach.description) && (
          <span className="ach-desc clamp-2">{veiled ? tr("secretTapToReveal") : ach.description}</span>
        )}
        <AchMarks ach={ach} plain={plain} date={date} extra={extra} />
      </span>
      {trail}
    </button>
  );
}

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
