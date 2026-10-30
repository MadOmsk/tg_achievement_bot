import { useState } from "react";
import { clubApi, type PersonPayload } from "../api";
import { useLoad } from "../app/useLoad";
import { PassStrip } from "../screens/season-pass/SeasonPassCard";
import { usePass } from "../core/season-pass";
import { passApi } from "../api/season-pass/seasonPassApi";
import { useArtTheme } from "../app/artTheme";
import { useApp } from "../app/context";
import { tick } from "../core/haptic";
import { formatMonth, currentMonth } from "../core/people-utils";
import { num } from "../i18n";
import { Face } from "../ui/Face";
import { Icon } from "../ui/Icon";
import { MonthSheet } from "./Months";
import { Spark } from "./AchRow";

/** A person's month as one card, by what matters: the month's points (the
 * achievements and the games small beside; owner, 2026-10-28), the place among the people
 * followed by the app's own points, and those people in a row — each with
 * their place and how many points the person lacks to pass them (+) or leads
 * them by (−). Home
 * shows the viewer's, a person's page that person's. */
export function MonthHero({
  payload,
  month,
  months,
  onMonth,
  personId,
  season = false,
}: {
  payload: PersonPayload | null | undefined;
  month: string;
  /** The months there are to see, newest first; with `onMonth` the card
   * turns from one to the next. */
  months?: string[];
  onMonth?: (month: string) => void;
  /** Whose month it is: their place among the people the viewer follows. */
  personId?: number;
  /** Home's own card: this month's season pass under the race. */
  season?: boolean;
}) {
  const { data, tr, locale, open, me } = useApp();
  const summary = useLoad(personId ? `summary:${month}:hero` : null, () => clubApi.fetchSummary(data, "following", { month }));
  const leaders = [...(summary.data?.month ?? [])]
    .filter((r) => r.count > 0)
    .sort((a, b) => (b.points ?? 0) - (a.points ?? 0) || b.count - a.count);
  const place = personId ? leaders.findIndex((r) => r.person_id === personId) + 1 : 0;
  // Until both the month and the race are in, the card keeps their shapes.
  const ready = Boolean(payload) && (!personId || Boolean(summary.data) || Boolean(summary.error));
  const mine = place > 0 ? (leaders[place - 1].points ?? 0) : 0;
  const [pick, setPick] = useState(false);
  const list = months?.length ? months : [month];
  const label = formatMonth(month, locale, "sheet");
  // The pass is this month's: another month shows its race.
  const thisMonth = month === currentMonth();
  const pass = season && thisMonth;
  const passState = usePass(data);
  // An earlier month's season, as the arrows switch to it.
  const pastSeason = useLoad(!thisMonth ? `hero-season:${month}` : null, () => passApi.fetchPass(data, { month }));
  const shownSeason = thisMonth ? passState : (pastSeason.data ?? null);
  // This month's season is remembered on the device, so a visit draws it at
  // once rather than a moment later.
  const remembered = thisMonth && !passState ? recallSeason(month) : null;
  if (thisMonth && passState) rememberSeason(month, passState.title, passState.image ?? null);
  // The season's name is Home's; its colours, from its cover, every card's
  // (owner, 2026-10-30), so each month's card looks its own.
  const seasonTitle = season ? (shownSeason?.title ?? remembered?.title ?? null) : null;
  const tint = useArtTheme(shownSeason?.image ?? remembered?.image ?? null, true);
  return (
    <section className="home-hero" style={tint.style}>
      <span className="home-hero-deco shape-clover4" aria-hidden="true" />
      {onMonth ? (
        <div className="home-hero-nav">
          <button type="button" className="home-hero-month home-hero-pick" onClick={() => setPick(true)}>
            {label.toUpperCase()}
            <Icon name="down" size={18} />
          </button>
        </div>
      ) : (
        <p className="home-hero-month">{label.split(" ")[0].toUpperCase()}</p>
      )}
      {seasonTitle && <p className="home-hero-season clamp-1">{seasonTitle}</p>}
      {pick && onMonth && <MonthSheet months={list} value={month} onChange={onMonth} onClose={() => setPick(false)} />}
      <div className="home-hero-main">
        <div className="home-hero-text">
          {payload ? (
            // Points run to five digits and more: the more digits, the smaller.
            <p className={`t-display home-hero-num home-hero-num-${Math.min(7, num(payload.month.points ?? 0, locale).length)}`}>
              <Spark className="home-hero-spark" />
              {num(payload.month.points ?? 0, locale)}
            </p>
          ) : (
            <span className="home-hero-ghost home-hero-ghost-num" />
          )}
        </div>
        {!ready && <span className="home-hero-ghost home-hero-ghost-medal shape-flower6" />}
        {ready && place > 0 && (
          <span key={`${month}:${place}`} className={`home-hero-medal shape-flower6${place <= 3 ? ` home-hero-medal-${place}` : ""}`}>
            <b className="t-num">{place}</b>
            <span>{tr("heroPlaceWord")}</span>
          </span>
        )}
      </div>
      {!ready && (
        <div className="home-hero-people rail" aria-hidden="true">
          {[0, 1, 2, 3, 4].map((i) => (
            <span key={i} className="home-hero-person home-hero-person-ghost">
              <span className="home-hero-ghost home-hero-ghost-face shape-cookie12" />
              <span className="home-hero-ghost home-hero-ghost-chip" />
            </span>
          ))}
        </div>
      )}
      {ready && place > 0 && leaders.length > 1 && (
        <div className="home-hero-people rail">
          {leaders.map((r, i) => {
            const isMe = r.person_id === personId;
            // Above the person: how many to pass them (one more than the
            // difference). Below: how far ahead the person is; level is "+0".
            const above = i < place - 1;
            const gap = above ? (r.points ?? 0) - mine + 1 : mine - (r.points ?? 0);
            return (
              <button
                key={r.person_id}
                type="button"
                className={`home-hero-person${i < 3 ? ` home-hero-person-${i + 1}` : ""}${isMe ? " home-hero-person-me" : ""}`}
                onClick={() => {
                  tick();
                  open({ kind: "person", personId: r.person_id });
                }}
              >
                <span className="home-hero-person-face">
                  <span className="home-hero-person-ring shape-cookie12">
                    <Face personId={r.person_id} name={r.name} size={54} />
                  </span>
                  <span className="home-hero-person-at t-num">{i + 1}</span>
                </span>
                <span className={`home-hero-person-gap t-num${isMe ? "" : above ? " home-hero-person-ahead" : " home-hero-person-behind"}`}>
                  {isMe
                    ? personId === me.person_id
                      ? tr("you")
                      : num(r.points ?? 0, locale)
                    : above
                      ? `+${num(gap, locale)}`
                      : gap > 0
                        ? `−${num(gap, locale)}`
                        : "+0"}
                </span>
              </button>
            );
          })}
        </div>
      )}
      {pass && <PassStrip />}
    </section>
  );
}

const SEASON_KEY = "home-season";

function recallSeason(month: string): { title: string | null; image?: string | null } | null {
  try {
    const saved = JSON.parse(localStorage.getItem(SEASON_KEY) ?? "null");
    return saved && saved.month === month ? saved : null;
  } catch {
    return null;
  }
}

function rememberSeason(month: string, title: string | null, image: string | null): void {
  try {
    localStorage.setItem(SEASON_KEY, JSON.stringify({ month, title, image }));
  } catch {
    // A private window keeps nothing: the card waits for the server then.
  }
}
