import type { PersonProfile } from "../api/people/peopleApi";
import { useApp } from "../app/context";
import { num, plural } from "../i18n";

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
 * nickname with its platform and counts under it, and the one number that
 * platform is known by (gamerscore, level) on the right. */
export function AccountCard({ p }: { p: Platform }) {
  const { tr, locale } = useApp();
  const name = MARK[p.platform]?.name ?? p.platform;
  const score = p.gamerscore
    ? { value: num(p.gamerscore, locale), unit: "G" }
    : p.trophy_level
      ? { value: String(p.trophy_level), unit: tr("level") }
      : null;
  const count = p.achievement_count ?? p.trophy_count ?? null;
  const facts = [
    name,
    count != null
      ? `${num(count, locale)} ${p.trophy_count != null && p.achievement_count == null ? tr("trophies") : plural(locale, count, ["achOne", "achFew", "achMany"])}`
      : null,
    p.completed_games
      ? `${p.completed_games} ${plural(locale, p.completed_games, ["gameOne", "gameFew", "gameMany"])} ${tr("accOn100")}`
      : null,
    p.platinum_count ? `${tr("tierPlatinum")} · ${p.platinum_count}` : null,
  ].filter(Boolean) as string[];
  return (
    <div className="row acc-card">
      <PlatformMark platform={p.platform} size={36} />
      <span className="row-text">
        <span className="row-title clamp-1">{p.name}</span>
        <span className="row-sub acc-facts">
          {facts.map((f) => (
            <span key={f}>{f}</span>
          ))}
        </span>
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
