import { TierDisc, asTier } from "../../shared/lib";

export function HeroMarks({
  score,
  rarity,
  tier,
  compact = false,
}: {
  score: string | null;
  rarity: string | null;
  /** A PSN trophy's tier (bronze…platinum): drawn as its medal, after the rarity. */
  tier?: string | null;
  compact?: boolean;
}) {
  const kind = asTier(tier);
  const text = [rarity, kind ? null : score].filter(Boolean).join(" · ");
  if (!text && !kind) return null;
  const body = (
    <>
      {text}
      {kind && (
        <>
          {text && " · "}
          <TierDisc tier={kind} size={compact ? 13 : 18} />
        </>
      )}
    </>
  );
  if (compact) {
    return <span className="feed-plat">{body}</span>;
  }
  return (
    <span className="hero-corner">
      <span className="hero-mark">{body}</span>
    </span>
  );
}
