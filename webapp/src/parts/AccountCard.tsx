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
      <PlatformMark platform={p.platform} size={22} />
      <span className="acc-chip-score t-num">{score ?? p.name}</span>
    </span>
  );
}
