import { useMemo, useState } from "react";
import { clubApi, type FeedItem, type SummaryMember } from "../../api";
import { useApp } from "../../app/context";
import { useLoad } from "../../app/useLoad";
import { achOfFeed } from "../../app/views";
import { currentMonth, formatMonth } from "../../core/people-utils";
import { tick } from "../../core/haptic";
import { num, plural } from "../../i18n";
import { capital, MonthSheet } from "../../parts/Months";
import { Sheet } from "../../ui/Page";
import { Pull } from "../../parts/Pull";
import { Button, Empty, Section, Segmented } from "../../ui/Controls";
import { Face } from "../../ui/Face";
import { WaveRing } from "../../ui/WaveRing";
import { GameTile } from "../../parts/GameTile";
import { AchTile } from "../../parts/AchTile";
import "./Ranking.css";

type Board = "day" | "month" | "year";

type Hunt = { key: string; item: FeedItem; people: Array<{ id: number; name: string; at: string | null }> };

/** Achievements several people got this month, each once with everybody who
 * got it, the most shared first. */
function hunts(items: FeedItem[], min = 2): Hunt[] {
  const map = new Map<string, Hunt>();
  for (const item of items) {
    const key = `${item.platform}:${item.title_id}:${item.achievement_id}`;
    const hunt = map.get(key) ?? { key, item, people: [] };
    if (!hunt.people.some((p) => p.id === item.person_id)) hunt.people.push({ id: item.person_id, name: item.person, at: item.unlocked_at ?? null });
    map.set(key, hunt);
  }
  return [...map.values()].filter((h) => h.people.length >= min).sort((a, b) => b.people.length - a.people.length);
}

const sum = (rows: SummaryMember[] | undefined) => (rows ?? []).reduce((n, r) => n + r.count, 0);

/** The months of the last three years up to this one, newest first. */
function lastMonths(now: string): string[] {
  const out: string[] = [];
  const year = Number(now.slice(0, 4));
  for (let y = year; y > year - 3; y -= 1) {
    for (let m = y === year ? Number(now.slice(5, 7)) : 12; m >= 1; m -= 1) out.push(`${y}-${String(m).padStart(2, "0")}`);
  }
  return out;
}

export function Ranking({ refreshKey }: { refreshKey: number }) {
  const { data, tr, locale, me, open } = useApp();
  const [month, setMonth] = useState(currentMonth());
  const [round, setRound] = useState(0);
  const [board, setBoard] = useState<Board>("month");
  const [pick, setPick] = useState<"month" | "year" | null>(null);
  const thisMonth = currentMonth();
  const summary = useLoad(`summary:${month}:${refreshKey}:${round}`, () =>
    clubApi.fetchSummary(data, "following", { month }),
  );
  const s = summary.data;
  const together = useMemo(() => hunts(s?.recent ?? []), [s]);
  const rows = (board === "day" ? s?.day : board === "year" ? s?.year : s?.month) ?? [];
  const leaders = [...rows].sort((a, b) => b.count - a.count || b.score - a.score);
  const myPlace = leaders.findIndex((r) => r.person_id === me.person_id && r.count > 0) + 1;
  const total = sum(rows);
  const mine = rows.find((r) => r.person_id === me.person_id)?.count ?? 0;
  const podium = leaders.filter((r) => r.count > 0).slice(0, 3);
  const rest = leaders.slice(podium.length);

  return (
    <div className="ranking">
      <Pull onRefresh={() => setRound((n) => n + 1)} />
      <header className="screen-head">
        <h1 className="t-headline">{tr("ranking")}</h1>
      </header>

      {summary.error && !s ? (
        <Empty icon="refresh" title={tr("loadFailed")} action={<Button variant="tonal" onClick={summary.reload}>{tr("retry")}</Button>} />
      ) : null}

      <div className="board-switch">
        <Segmented
          options={[
            { value: "day", label: tr("boardDay") },
            { value: "month", label: capital(formatMonth(month, locale, "chip")), more: true },
            { value: "year", label: month.slice(0, 4), more: true },
          ]}
          value={board}
          onChange={setBoard}
          onRepeat={(b) => setPick(b === "year" ? "year" : "month")}
        />
      </div>
      {pick === "month" && (
        <MonthSheet months={lastMonths(thisMonth)} value={month} onChange={setMonth} onClose={() => setPick(null)} />
      )}
      {pick === "year" && (
        <Sheet title={tr("pickYear")} onClose={() => setPick(null)} layer="rank-year">
          <div className="months-grid">
            {[0, 1, 2].map((i) => {
              const y = String(Number(thisMonth.slice(0, 4)) - i);
              return (
                <button
                  key={y}
                  type="button"
                  className={month.startsWith(y) ? "months-on" : ""}
                  onClick={() => {
                    setPick(null);
                    setMonth(i === 0 ? thisMonth : `${y}-12`);
                  }}
                >
                  {y}
                </button>
              );
            })}
          </div>
        </Sheet>
      )}

      <section className="rank-hero">
        <WaveRing value={mine} total={total || 1} size={116}>
          <span className="rank-ring-pct t-num">{total ? Math.round((mine / total) * 100) : 0}%</span>
        </WaveRing>
        <div className="rank-hero-text">
          <p className="rank-hero-kick">{tr("rankYourShare")}</p>
          <p className="rank-hero-num t-num">
            {s ? num(mine, locale) : "–"}
            <small>/{s ? num(total, locale) : "–"}</small>
          </p>
          <p className="rank-hero-line">{tr("rankShareLine")}</p>
        </div>
      </section>

      <Section
        title={tr("leaders")}
        action={myPlace > 0 ? <span className="rank-place-chip">{tr("rankYouPlace").replace("{n}", String(myPlace))}</span> : null}
      >
        {podium.length > 0 && (
          <div className="podium">
            {[1, 0, 2].map((place) => {
              const r = podium[place];
              if (!r) return <span key={place} className="podium-step" />;
              const n = place + 1;
              return (
                <button
                  key={r.person_id}
                  type="button"
                  className={`podium-step podium-${n}`}
                  onClick={() => {
                    tick();
                    open({ kind: "person", personId: r.person_id });
                  }}
                >
                  <span className="podium-face">
                    <Face personId={r.person_id} name={r.name} size={n === 1 ? 76 : 60} />
                    <span className="podium-medal shape-flower6">{n}</span>
                  </span>
                  <span className="podium-name clamp-1">{r.person_id === me.person_id ? tr("you") : r.name}</span>
                  <span className="podium-block">
                    <b className="t-num">{num(r.count, locale)}</b>
                  </span>
                </button>
              );
            })}
          </div>
        )}
        <div className="group">
          <div className="group-items">
            {!s && Array.from({ length: 4 }, (_, i) => <span key={i} className="row skel" style={{ height: 68 }} />)}
            {s && podium.length === 0 && <div className="row t-meta">{tr("emptySummary")}</div>}
            {rest.map((r, j) => {
              const i = j + podium.length;
              return (
              <button
                key={r.person_id}
                type="button"
                className={`row row-tap leader${r.person_id === me.person_id ? " leader-me" : ""}`}
                onClick={() => {
                  tick();
                  open({ kind: "person", personId: r.person_id });
                }}
              >
                <span className={`leader-rank${i < 3 ? ` leader-top shape-flower6 leader-top-${i}` : ""}`}>{i + 1}</span>
                <Face personId={r.person_id} name={r.name} size={44} />
                <span className="row-text">
                  <span className="row-title clamp-1">{r.name}</span>
                  <span className="row-sub">
                    {r.score > 0 && `${num(r.score, locale)} G`}
                    {r.rare > 0 && ` · ${tr("factRare").toLowerCase()} ${r.rare}`}
                  </span>
                </span>
                <span className="leader-count">
                  <b className="t-num">{num(r.count, locale)}</b>
                  <span>{plural(locale, r.count, ["achOne", "achFew", "achMany"])}</span>
                </span>
              </button>
              );
            })}
          </div>
        </div>
      </Section>

      {(s?.games.length ?? 0) > 0 && (
        <Section title={tr("trending")}>
          <div className="rail month-games">
            {s!.games.map((g) => (
              <GameTile
                key={`${g.platform}:${g.title_id}`}
                cover={g.icon_url}
                name={g.name ?? ""}
                mark={
                  <span className="trend-count">
                    <b className="t-num">{num(g.count, locale)}</b>
                    <span>{plural(locale, g.count, ["achOne", "achFew", "achMany"])}</span>
                  </span>
                }
                onOpen={() => open({ kind: "game", ref: { platform: g.platform, title_id: g.title_id, name: g.name, icon_url: g.icon_url } })}
              />
            ))}
          </div>
        </Section>
      )}

      {together.length > 0 && (
        <Section title={tr("huntTogether")}>
          <div className="hunts rail">
            {together.map((h) => (
              <AchTile key={h.key} ach={achOfFeed(h.item)} people={h.people} />
            ))}
          </div>
        </Section>
      )}

      {(s?.rares?.length ?? 0) > 0 && (
        <Section title={tr("rareFinds")}>
          <div className="rail rares">
            {hunts(s!.rares!, 1)
              .sort((a, b) => (a.item.rarity_percent ?? 100) - (b.item.rarity_percent ?? 100))
              .map(({ key, item, people }) => (
                <AchTile key={key} ach={achOfFeed(item)} people={people} badge />
              ))}
          </div>
        </Section>
      )}

    </div>
  );
}

