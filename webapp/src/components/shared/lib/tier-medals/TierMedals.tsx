import "./TierMedals.css";

export interface TierCounts {
  bronze: number;
  silver: number;
  gold: number;
  platinum: number;
}

export type Tier = keyof TierCounts;

const ORDER: Tier[] = ["platinum", "gold", "silver", "bronze"];

/** The trophy tier a platform sends ("Gold", "platinum"…), or null. */
export function asTier(type: string | null | undefined): Tier | null {
  const key = (type ?? "").toLowerCase();
  return key === "bronze" || key === "silver" || key === "gold" || key === "platinum"
    ? key
    : null;
}

/** One tier's medal — the same disc wherever a trophy tier is shown. */
export function TierDisc({ tier, size = 16 }: { tier: Tier; size?: number }) {
  return (
    <i
      className={`tier-disc is-${tier}`}
      style={{ width: size, height: size }}
      aria-label={tier}
    />
  );
}

/**
 * Earned trophies per tier as medals with their counts, best first. Only tiers
 * with something in them are drawn.
 */
export function TierMedals({ counts }: { counts: TierCounts }) {
  const shown = ORDER.filter((tier) => counts[tier] > 0);
  if (shown.length === 0) return null;
  return (
    <span className="tier-medals">
      {shown.map((tier) => (
        <span key={tier} className="tier-medal">
          <TierDisc tier={tier} />
          <b>{counts[tier]}</b>
        </span>
      ))}
    </span>
  );
}
