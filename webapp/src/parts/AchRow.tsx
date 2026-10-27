import { useState, type ReactNode } from "react";
import { useApp } from "../app/context";
import type { AchView } from "../app/layers";
import { isVeiled, rareLevel, revealed } from "../app/views";
import { num, pct, type TranslationKey } from "../i18n";
import { tick } from "../core/haptic";
import { AchPic } from "../ui/Pic";
import "./parts.css";

/** Xbox One/Series pictures are 16:9 art; every other platform's are square. */
export function isWideArt(platform: string): boolean {
  return platform === "xbox_modern";
}

const TIERS: Record<string, TranslationKey> = {
  bronze: "tierBronze",
  silver: "tierSilver",
  gold: "tierGold",
  platinum: "tierPlatinum",
};

/** What an achievement is worth: its tier or points, and how rare. */
export function AchMarks({
  ach,
  size = "s",
  plain = false,
  date,
  extra,
}: {
  ach: Pick<AchView, "trophy" | "gamerscore" | "rarity">;
  size?: "s" | "m";
  /** A line of text instead of chips, where many rows sit together. */
  plain?: boolean;
  /** When it was earned, at the end of that line. */
  date?: string | null;
  /** Marks of the row's own (who has it, its guides), last on that line. */
  extra?: ReactNode;
}) {
  const { tr, locale } = useApp();
  const tier = ach.trophy ? TIERS[ach.trophy.toLowerCase()] : undefined;
  const rare = rareLevel(ach.rarity);
  if (plain) {
    const worth = tier ? (
      <span className="mark-worth">
        <span className={`tier tier-${ach.trophy?.toLowerCase()}`} />
        {tr(tier)}
      </span>
    ) : ach.gamerscore ? (
      <span className="mark-worth">{num(ach.gamerscore, locale)} G</span>
    ) : null;
    const rarity =
      ach.rarity != null ? (
        <span className={`mark-rarity${rare ? ` mark-${rare}` : ""}`}>
          {rare && <span className="rare-mark shape-flower6" />}
          {pct(ach.rarity, locale)}
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
      {tier && (
        <span className="chip chip-outline">
          <span className={`tier tier-${ach.trophy?.toLowerCase()}`} />
          {tr(tier)}
        </span>
      )}
      {!tier && ach.gamerscore ? <span className="chip chip-outline">{num(ach.gamerscore, locale)} G</span> : null}
      {ach.rarity != null && (
        <span className={`chip ${rare ? `chip-tier chip-tier-${rare}` : "chip-outline"}`}>
          {rare && <span className="rare-mark shape-flower6" />}
          {pct(ach.rarity, locale)}
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
      <AchPic src={ach.icon} className={wide ? "ach-pic-wide" : "ach-pic-square"} veiled={veiled} tier={rareLevel(ach.rarity)} />
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

const PLATFORM_SHORT: Record<string, string> = {
  xbox_modern: "XBOX",
  xbox_360: "XBOX 360",
  xbox: "XBOX",
  psn: "PS",
  steam: "STEAM",
};

export function PlatformTag({ platform }: { platform: string }) {
  return <span className="ptag">{PLATFORM_SHORT[platform] ?? platform.toUpperCase()}</span>;
}
