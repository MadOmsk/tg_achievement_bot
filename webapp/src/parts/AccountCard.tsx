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

/** One game account on a person's card, one line: the platform's mark, the
 * nickname with its platform under it, and the one number that platform is
 * known by (gamerscore, level) on the right. */
export function AccountCard({ p }: { p: Platform }) {
  const { tr, locale } = useApp();
  const name = MARK[p.platform]?.name ?? p.platform;
  const score = p.gamerscore
    ? { value: num(p.gamerscore, locale), unit: "G" }
    : p.trophy_level
      ? { value: String(p.trophy_level), unit: tr("level") }
      : null;
  return (
    <div className="row acc-card">
      <PlatformMark platform={p.platform} size={36} />
      <span className="row-text">
        <span className="row-title clamp-1">{p.name}</span>
        <span className="row-sub">{name}</span>
      </span>
      {score && (
        <span className="acc-score">
          <b className="t-num">{score.value}</b>
          <span>{score.unit}</span>
        </span>
      )}
    </div>
  );
}
