import type { FeedItem, PersonPayload } from "../api";
import { useApp } from "../app/context";
import { achOfFeed, isVeiled } from "../app/views";
import { tick } from "../core/haptic";
import { formatMonth } from "../core/people-utils";
import { num, plural } from "../i18n";
import { AchPic } from "../ui/Pic";

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

/** A person's month as one card: how many achievements, the points and the
 * games, the latest three as a fan of pictures, and the month by day. Home
 * shows the viewer's, a person's page that person's. */
export function MonthHero({ payload, month }: { payload: PersonPayload | null | undefined; month: string }) {
  const { tr, locale, open, me } = useApp();
  const recent = (payload?.feed ?? []).slice(0, 3);
  return (
    <section className="home-hero">
      <div className="home-hero-top">
        <div className="home-hero-text">
          <p className="home-hero-month">{formatMonth(month, locale, "sheet").split(" ")[0].toUpperCase()}</p>
          {payload ? (
            <>
              <p className="t-display home-hero-num">{num(payload.month.count, locale)}</p>
              <p className="home-hero-line">
                {plural(locale, payload.month.count, ["achOne", "achFew", "achMany"])}
                <br />
                {payload.month.score > 0 && <b>+{num(payload.month.score, locale)} G · </b>}
                {payload.games.length} {plural(locale, payload.games.length, ["gameOne", "gameFew", "gameMany"])}
              </p>
            </>
          ) : (
            <>
              <span className="home-hero-ghost home-hero-ghost-num" />
              <span className="home-hero-ghost home-hero-ghost-line" />
              <span className="home-hero-ghost home-hero-ghost-line short" />
            </>
          )}
        </div>
        <div className="home-hero-stack">
          {!payload &&
            [0, 1, 2].map((i) => <span key={i} className={`home-hero-pic home-hero-pic-${i} home-hero-ghost`} />)}
          {recent.map((item, i) => (
            <button
              key={`${item.title_id}:${item.achievement_id}`}
              type="button"
              className={`home-hero-pic home-hero-pic-${i}`}
              aria-label={item.name ?? tr("pageAchievement")}
              onClick={() => {
                tick();
                open({ kind: "achievement", ach: achOfFeed(item) });
              }}
            >
              <AchPic
                src={item.icon_url}
                veiled={isVeiled(item.is_secret, `${item.platform}:${item.title_id}:${item.achievement_id}:${item.person_id}`, me.settings.show_secrets)}
              />
            </button>
          ))}
        </div>
      </div>
      <MonthBars feed={payload?.feed ?? []} month={month} />
    </section>
  );
}
