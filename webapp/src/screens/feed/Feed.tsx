import { useEffect, useMemo, useRef, useState } from "react";
import { clubApi, type FeedItem, type NewsItem } from "../../api";
import { useApp } from "../../app/context";
import { useLoad } from "../../app/useLoad";
import { currentMonth } from "../../core/people-utils";
import { dayKey, dayLabel } from "../../i18n";
import { MonthButton } from "../../parts/Months";
import { toPosts, type Post as PostData } from "../../parts/posts";
import { Pull } from "../../parts/Pull";
import { Button, Empty } from "../../ui/Controls";
import { tick } from "../../core/haptic";
import { MagazineNews, MagazinePost, MagazineSkel } from "../../parts/MagazinePost";
import "./Feed.css";

const STEP = 16;

type Entry = { key: string; at: string; post?: PostData; news?: NewsItem };
type Day = { key: string; label: string; date: number; count: number; entries: Entry[] };

/** The month's posts and the favorite games' news, one day after another,
 * each day newest first. */
function toDays(items: FeedItem[], news: NewsItem[], locale: string): Day[] {
  const entries: Entry[] = [
    ...toPosts(items).map((post) => ({ key: post.key, at: post.events[0].items[0].unlocked_at ?? "", post })),
    ...news.map((item) => ({ key: `n:${item.appid}:${item.gid}`, at: item.date, news: item })),
  ].sort((x, y) => y.at.localeCompare(x.at));
  const days: Day[] = [];
  for (const entry of entries) {
    const key = entry.post ? entry.post.day : dayKey(entry.at);
    let day = days.find((d) => d.key === key);
    if (!day) {
      day = { key, label: dayLabel(entry.at, locale), date: entry.at ? new Date(entry.at).getDate() : 0, count: 0, entries: [] };
      days.push(day);
    }
    day.entries.push(entry);
    if (entry.post) day.count += entry.post.events.reduce((n, e) => n + e.items.length, 0);
  }
  return days;
}

export function Feed({ refreshKey }: { refreshKey: number }) {
  const { data, tr, locale } = useApp();
  const [month, setMonth] = useState(currentMonth());
  const [round, setRound] = useState(0);
  const feed = useLoad(`feed:${month}:${refreshKey}:${round}`, () =>
    clubApi.fetchFeed(data, "following", { month }),
  );
  const news = useLoad(`feed-news:${month}:${refreshKey}:${round}`, () =>
    clubApi.fetchNews(data, { month, favorites: true }),
  );
  const days = useMemo(
    () => toDays(feed.data?.items ?? [], news.data?.items ?? [], locale),
    [feed.data, news.data, locale],
  );
  const [limit, setLimit] = useState(STEP);
  const [jump, setJump] = useState<string | null>(null);
  const sentinel = useRef<HTMLDivElement>(null);

  useEffect(() => setLimit(STEP), [month]);

  useEffect(() => {
    const node = sentinel.current;
    if (!node) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) setLimit((n) => n + STEP);
      },
      { rootMargin: "1200px 0px" },
    );
    io.observe(node);
    return () => io.disconnect();
  }, [days.length]);

  // A day further down than drawn: draw up to it, then go there.
  useEffect(() => {
    if (!jump) return;
    const node = document.getElementById(`day-${jump}`);
    if (node) {
      node.scrollIntoView({ behavior: "smooth", block: "start" });
      setJump(null);
    }
  }, [jump, limit]);

  const goTo = (day: Day) => {
    tick();
    let before = 0;
    for (const d of days) {
      before += d.entries.length;
      if (d.key === day.key) break;
    }
    setLimit((n) => Math.max(n, before + 2));
    setJump(day.key);
  };

  let left = limit;
  const isCurrent = month === (feed.data?.current_month ?? currentMonth());

  return (
    <div className="feed">
      <Pull onRefresh={() => setRound((n) => n + 1)} />
      <header className="screen-head">
        <h1 className="t-headline">{tr("feed")}</h1>
        <MonthButton months={feed.data?.months ?? []} value={month} onChange={setMonth} />
      </header>

      {days.length > 0 && (
        <div className="days rail" role="list">
          {days.map((d) => (
            <button key={d.key} type="button" className="day" onClick={() => goTo(d)}>
              <b>{d.date}</b>
              <span>{d.count || "·"}</span>
            </button>
          ))}
        </div>
      )}

      {!feed.data && feed.loading && (
        <div className="feed-skel">
          <div className="days rail" aria-hidden="true">
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <span key={i} className="day skel" />
            ))}
          </div>
          <span className="skel skel-line feed-skel-day" />
          <MagazineSkel />
          <MagazineSkel />
        </div>
      )}

      {feed.error && !feed.data ? (
        <Empty
          icon="refresh"
          title={tr("loadFailed")}
          action={
            <Button variant="tonal" onClick={feed.reload}>
              {tr("retry")}
            </Button>
          }
        />
      ) : null}

      {feed.data && days.length === 0 && (
        <Empty
          icon="feed"
          title={isCurrent ? tr("emptyTitleNow") : tr("emptyTitlePast")}
          text={tr("emptyFeedHint")}
          action={
            feed.data.months.length > 1 && isCurrent ? (
              <Button variant="tonal" onClick={() => setMonth(feed.data!.months[1])}>
                {tr("emptyPrevMonth")}
              </Button>
            ) : null
          }
        />
      )}

      {days.map((d) => {
        if (left <= 0) return null;
        const shown = d.entries.slice(0, left);
        left -= shown.length;
        return (
          <section key={d.key} id={`day-${d.key}`} className="feed-day">
            <h2 className="feed-day-head">
              <span>{d.label}</span>
              {d.count > 0 && <span className="feed-day-count">{d.count}</span>}
            </h2>
            {shown.map((e) => (e.post ? <MagazinePost key={e.key} post={e.post} /> : <MagazineNews key={e.key} item={e.news!} />))}
          </section>
        );
      })}
      <div ref={sentinel} style={{ height: 1 }} />
    </div>
  );
}
