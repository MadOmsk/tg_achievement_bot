import type { PersonProfile } from "../api/people/peopleApi";
import { useApp } from "../app/context";
import { num } from "../i18n";

type Platform = NonNullable<PersonProfile["activity"]>["platforms"][number];

const MARK: Record<string, { glyph: string; cls: string; name: string }> = {
  xbox: { glyph: "X", cls: "acc-xbox", name: "Xbox" },
  xbox_modern: { glyph: "X", cls: "acc-xbox", name: "Xbox" },
  psn: { glyph: "PS", cls: "acc-psn", name: "PlayStation" },
  steam: { glyph: "S", cls: "acc-steam", name: "Steam" },
};

export function PlatformMark({ platform, size = 44 }: { platform: string; size?: number }) {
  const m = MARK[platform] ?? { glyph: "?", cls: "", name: platform };
  return (
    <span className={`acc-mark ${m.cls} shape-cookie9`} style={{ width: size, height: size }} aria-label={m.name}>
      {m.glyph}
    </span>
  );
}

/** The same account as a short chip under a person's name: the platform's
 * mark and the one number it is known by (the nickname when it has none). */
export function AccountChip({ p }: { p: Platform }) {
  const { tr, locale } = useApp();
  const score = p.gamerscore ? `${num(p.gamerscore, locale)} G` : p.trophy_level ? `${tr("level")} ${p.trophy_level}` : null;
  return (
    <span className="acc-chip">
      <PlatformMark platform={p.platform} size={18} />
      <span className="acc-chip-score t-num">{score ?? p.name}</span>
    </span>
  );
}

/** A game account as a row of a person's page: the platform's mark, the
 * nickname on it, its own score (G or the trophy level), then how many
 * achievements or trophies it holds. */
export function AccountRow({ p }: { p: Platform }) {
  const { tr, locale } = useApp();
  const name = MARK[p.platform]?.name ?? p.platform;
  const score = p.gamerscore ? `${num(p.gamerscore, locale)} G` : p.trophy_level ? `${tr("level")} ${p.trophy_level}` : null;
  const count = p.achievement_count ?? p.trophy_count ?? null;
  return (
    <div className="row acc-row">
      <PlatformMark platform={p.platform} size={40} />
      <span className="row-text">
        <span className="row-title clamp-1">{p.name ?? name}</span>
        <span className="row-sub">{[name, count != null ? `${num(count, locale)} ${tr("achShort")}` : null].filter(Boolean).join(" · ")}</span>
      </span>
      {score && <b className="acc-row-score t-num">{score}</b>}
    </div>
  );
}
