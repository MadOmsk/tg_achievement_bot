import type { AchView } from "../app/layers";
import { useApp } from "../app/context";
import { isVeiled, pointsOf, rareLevel, TIER_NAME } from "../app/views";
import { tick } from "../core/haptic";
import { pct } from "../i18n";
import { Face } from "../ui/Face";
import { AchPic } from "../ui/Pic";
import { isWideArt } from "./AchRow";
import { capital } from "./Months";
import { Spark } from "./AchRow";

/** One achievement as a card of a rail — Home's latest, the hunts, the rare
 * finds: its picture with its rarity on the corner, name, game, then who got
 * it or its tier and worth. One shape for every rail. */
export function AchTile({
  ach,
  people,
  badge = true,
}: {
  ach: AchView;
  /** Who got it, when the card is about people. */
  people?: Array<{ id: number; name: string; at?: string | null }>;
  /** The rarity as a flower on the picture's corner (on by default). */
  badge?: boolean;
}) {
  const { tr, locale, open, me } = useApp();
  const veiled = isVeiled(ach.secret, ach.key, me.settings.show_secrets);
  const level = rareLevel(ach.rarity, ach);
  return (
    <button
      type="button"
      className="tile"
      onClick={() => {
        tick();
        open({
          kind: "achievement",
          ach: people
            ? { ...ach, person: null, together: people.map((p) => ({ id: p.id, name: p.name, at: p.at ?? null })) }
            : ach,
        });
      }}
    >
      <span className="tile-art">
        <AchPic
          src={ach.icon}
          veiled={veiled}
          className={isWideArt(ach.platform) ? "tile-pic" : "tile-pic tile-pic-sq"}
        />
        {/* What it is worth on the flower, in its tier's colour; how rare beside the tier's word. */}
        {badge && (
          <span className={`tile-badge shape-flower6 tile-badge-${level ?? "plain"}`}>
            <b className="t-num flower-pts">
              <Spark className="flower-spark" />
              {pointsOf(ach.rarity, ach)}</b>
          </span>
        )}
      </span>
      <span className="tile-kicker">
        <span className={level ? `mark-${level}` : ""}>
          {capital(tr(TIER_NAME[level ?? "common"]))}
          {ach.rarity != null && ` · ${pct(ach.rarity, locale)}`}
        </span>
      </span>
      <span className="tile-name clamp-2">{veiled ? tr("secretAchievement") : ach.name}</span>
      <span className="tile-game clamp-1">{ach.game}</span>
      {people ? (
        <span className="tile-who">
          <span className="tile-faces">
            {people.slice(0, 3).map((p, i) => (
              <span key={p.id} style={{ zIndex: 3 - i }}>
                <Face personId={p.id} name={p.name} size={24} />
              </span>
            ))}
          </span>
          <span className="clamp-1">
            {(people[0].id === me.person_id ? tr("you") : people[0].name) +
              (people.length > 1 ? ` +${people.length - 1}` : "")}
          </span>
        </span>
      ) : null}
    </button>
  );
}
