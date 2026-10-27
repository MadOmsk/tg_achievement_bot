import type { AchView } from "../app/layers";
import { useApp } from "../app/context";
import { isVeiled, rareLevel } from "../app/views";
import { tick } from "../core/haptic";
import { pct } from "../i18n";
import { Face } from "../ui/Face";
import { AchPic } from "../ui/Pic";
import { AchMarks, isWideArt } from "./AchRow";

/** One achievement as a card of a rail — Home's latest, the hunts, the rare
 * finds: its picture (a rare one framed in its tier's colour), name, game,
 * then who got it or what it is worth. One shape for every rail. */
export function AchTile({
  ach,
  people,
  badge = false,
}: {
  ach: AchView;
  /** Who got it, when the card is about people. */
  people?: Array<{ id: number; name: string }>;
  /** The rarity as a flower on the picture's corner. */
  badge?: boolean;
}) {
  const { tr, locale, open, me } = useApp();
  const veiled = isVeiled(ach.secret, ach.key, me.settings.show_secrets);
  const level = rareLevel(ach.rarity);
  return (
    <button
      type="button"
      className="tile"
      onClick={() => {
        tick();
        open({ kind: "achievement", ach: people ? { ...ach, person: null } : ach });
      }}
    >
      <span className="tile-art">
        <AchPic
          src={ach.icon}
          veiled={veiled}
          tier={level}
          className={isWideArt(ach.platform) ? "tile-pic" : "tile-pic tile-pic-sq"}
        />
        {badge && ach.rarity != null && (
          <span className={`tile-badge shape-flower6 tile-badge-${level ?? "plain"}`}>
            <b className="t-num">{pct(ach.rarity, locale)}</b>
          </span>
        )}
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
      ) : (
        <AchMarks ach={ach} plain />
      )}
    </button>
  );
}
