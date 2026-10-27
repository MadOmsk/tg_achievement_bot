import { useState } from "react";
import { clubApi, type FeedItem, type PersonPayload } from "../api";
import { useLoad } from "../app/useLoad";
import { useApp } from "../app/context";
import { tick } from "../core/haptic";
import { formatMonth } from "../core/people-utils";
import { num, plural } from "../i18n";
import { Icon } from "../ui/Icon";
import { MonthSheet } from "./Months";

/** The month as one bar a day: how much was earned, today marked, the days
 * still to come left faint. */
function MonthBars({ feed, month }: { feed: FeedItem[]; month: string }) {
  const [year, m] = month.split("-").map(Number);
  const days = new Date(year, m, 0).getDate();
  const today = new Date();
  const isNow = today.getFullYear() === year && today.getMonth() + 1 === m;
  const counts = new Array(days).fill(0);
  for (const item of feed) {
    if (!item.unlocked_at) continue;
    const d = new Date(item.unlocked_at);
    if (d.getFullYear() === year && d.getMonth() + 1 === m) counts[d.getDate() - 1] += 1;
  }
  const top = Math.max(1, ...counts);
  return (
    <div className="home-bars" aria-hidden="true">
      {counts.map((n, i) => (
        <span
          key={i}
          className={`home-bar${n ? " home-bar-on" : ""}${isNow && i + 1 === today.getDate() ? " home-bar-today" : ""}${isNow && i + 1 > today.getDate() ? " home-bar-later" : ""}`}
          style={{ height: n ? `${Math.max(18, (n / top) * 100)}%` : undefined }}
        />
      ))}
    </div>
  );
}

/** A person's month as one card, by what matters: how many achievements
 * (the points and the games small beside), the place among the people
 * followed and the race with the one just above or below, the month by day. Home
 * shows the viewer's, a person's page that person's. */
export function MonthHero({
  payload,
  month,
  months,
  onMonth,
  personId,
}: {
  payload: PersonPayload | null | undefined;
  month: string;
  /** The months there are to see, newest first; with `onMonth` the card
   * turns from one to the next. */
  months?: string[];
  onMonth?: (month: string) => void;
  /** Whose month it is: their place among the people the viewer follows. */
  personId?: number;
}) {
  const { data, tr, locale } = useApp();
  const summary = useLoad(personId ? `summary:${month}:hero` : null, () => clubApi.fetchSummary(data, "following", { month }));
  const leaders = [...(summary.data?.month ?? [])].filter((r) => r.count > 0).sort((a, b) => b.count - a.count || b.score - a.score);
  const place = personId ? leaders.findIndex((r) => r.person_id === personId) + 1 : 0;
  // The race: who is just above (and how many it takes to pass them), or —
  // for the first — who is just below and how far behind.
  const rival = place > 1 ? leaders[place - 2] : place === 1 ? leaders[1] : undefined;
  const mine = place > 0 ? leaders[place - 1].count : 0;
  const gap = rival ? (place > 1 ? rival.count - mine + 1 : mine - rival.count) : 0;
  const [pick, setPick] = useState(false);
  const list = months?.length ? months : [month];
  const at = list.indexOf(month);
  const older = at >= 0 ? list[at + 1] : undefined;
  const newer = at > 0 ? list[at - 1] : undefined;
  const label = formatMonth(month, locale, "sheet");
  const go = (m: string | undefined) => {
    if (!m || !onMonth) return;
    tick();
    onMonth(m);
  };
  return (
    <section className="home-hero">
      <span className="home-hero-deco shape-clover4" aria-hidden="true" />
      {onMonth ? (
        <div className="home-hero-nav">
          <button type="button" className="home-hero-month home-hero-pick" onClick={() => setPick(true)}>
            {label.toUpperCase()}
            <Icon name="down" size={18} />
          </button>
          <span className="home-hero-arrows">
            <button type="button" className="home-hero-arrow" aria-label={tr("pickMonth")} disabled={!older} onClick={() => go(older)}>
              <Icon name="back" size={20} />
            </button>
            <button type="button" className="home-hero-arrow" aria-label={tr("pickMonth")} disabled={!newer} onClick={() => go(newer)}>
              <Icon name="forward" size={20} />
            </button>
          </span>
        </div>
      ) : (
        <p className="home-hero-month">{label.split(" ")[0].toUpperCase()}</p>
      )}
      {pick && onMonth && <MonthSheet months={list} value={month} onChange={onMonth} onClose={() => setPick(false)} />}
      <div className="home-hero-main">
        <div className="home-hero-text">
          {payload ? (
            <>
              <p className="t-display home-hero-num">{num(payload.month.count, locale)}</p>
              <p className="home-hero-line">
                {plural(locale, payload.month.count, ["achOne", "achFew", "achMany"])}
                {payload.month.score > 0 && ` · +${num(payload.month.score, locale)} G`}
                {` · ${payload.games.length} ${plural(locale, payload.games.length, ["gameOne", "gameFew", "gameMany"])}`}
              </p>
            </>
          ) : (
            <>
              <span className="home-hero-ghost home-hero-ghost-num" />
              <span className="home-hero-ghost home-hero-ghost-line" />
            </>
          )}
        </div>
        {place > 0 && (
          <span key={`${month}:${place}`} className={`home-hero-medal shape-flower6${place <= 3 ? ` home-hero-medal-${place}` : ""}`}>
            <b className="t-num">{place}</b>
            <span>{tr("heroPlaceWord")}</span>
          </span>
        )}
      </div>
      {place > 0 && (
        <div className="home-hero-race">
          <Icon name={place === 1 ? "trophy" : "rank"} size={16} />
          <span className="home-hero-race-line clamp-1">
            {!rival
              ? tr("heroAlone")
              : place > 1
                ? tr("heroToNext").replace("{n}", num(gap, locale)).replace("{name}", rival.name)
                : gap > 0
                  ? tr("heroAhead").replace("{n}", num(gap, locale)).replace("{name}", rival.name)
                  : tr("heroTied").replace("{name}", rival.name)}
          </span>
        </div>
      )}
      <MonthBars feed={payload?.feed ?? []} month={month} />
    </section>
  );
}
