import type { ReactNode } from "react";
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
export function TierDisc({
  tier,
  size = 16,
  children,
}: {
  tier: Tier;
  size?: number;
  children?: ReactNode;
}) {
  return (
    <span
      className={`tier-disc is-${tier}`}
      style={{ width: size, height: size }}
      aria-label={tier}
    >
      {children}
    </span>
  );
}

/**
 * Earned trophies per tier as medals with their counts, best first. Only tiers
 * with something in them are drawn.
 */
export function TierMedals({
  counts,
  discSize = 16,
  numbersInside = false,
}: {
  counts: TierCounts;
  discSize?: number;
  /** The count sits inside the disc instead of next to it — tighter, for
   * where there isn't room to spare (e.g. the game page's header). */
  numbersInside?: boolean;
}) {
  const shown = ORDER.filter((tier) => counts[tier] > 0);
  if (shown.length === 0) return null;
  return (
    <span className="tier-medals">
      {shown.map((tier) =>
        numbersInside ? (
          <TierDisc key={tier} tier={tier} size={discSize}>
            {counts[tier]}
          </TierDisc>
        ) : (
          <span key={tier} className="tier-medal">
            <TierDisc tier={tier} size={discSize} />
            <b>{counts[tier]}</b>
          </span>
        ),
      )}
    </span>
  );
}
