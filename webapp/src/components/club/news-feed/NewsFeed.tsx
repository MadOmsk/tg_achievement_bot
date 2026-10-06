import { useEffect, useState } from "react";
import { fetchNews, type NewsItem } from "../../../api";
import { dayLabel, t, type Locale } from "../../../i18n";
import { NewsPage } from "../../game/news-page/NewsPage";
import { CoverImg, EmptyState, FeedSkel, FitImg, FEED_RATIO_MAX, isWide, useImageRatio, useOpenGame } from "../../shared/lib";
import "../../person/feed-post/FeedPost.css";
import "./NewsFeed.css";

/** «Новости» (owner, 2026-10-05): what the developers of the games the viewer
 * and the people they follow play posted on Steam in the month, newest first,
 * as they wrote it — untranslated. Laid out as the achievements' feed is: days,
 * and in each a post — the game over the picture's top where a post has its
 * author, the picture edge to edge, the text on frosted glass at its foot. A
 * post opens whole on a page of its own; the game opens the game's page. */
export function NewsFeed({ data, locale, month }: { data: string; locale: Locale; month: string }) {
  const [items, setItems] = useState<NewsItem[] | null>(null);
  const [open, setOpen] = useState<NewsItem | null>(null);
  const openGame = useOpenGame();

  useEffect(() => {
    let cancelled = false;
    setItems(null);
    fetchNews(data, month ? { month } : undefined)
      .then((res) => {
        if (!cancelled) setItems(res.items);
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      });
    return () => {
      cancelled = true;
    };
  }, [data, month]);

  if (items === null) return <FeedSkel head={false} />;
  if (items.length === 0) {
    return <EmptyState title={t(locale, "newsEmptyTitle")} hint={t(locale, "newsEmptyHint")} slide />;
  }

  const days: Array<{ date: string; posts: NewsItem[] }> = [];
  for (const item of items) {
    const last = days[days.length - 1];
    if (last && last.date === item.date) last.posts.push(item);
    else days.push({ date: item.date, posts: [item] });
  }

  const openGameOf = (item: NewsItem) =>
    openGame?.({
      platform: item.game.platform,
      title_id: item.game.title_id,
      name: item.game.name,
      icon_url: item.game.icon_url,
    });

  return (
    <div className="feed-days">
      {days.map((day) => (
        <section key={day.date} className="feed-day">
          <span className="feed-day-label">{dayLabel(`${day.date}T12:00:00`, locale)}</span>
          <div className="feed-posts">
            {day.posts.map((item) => (
              <NewsPostCard
                key={`${item.appid}:${item.gid}`}
                item={item}
                locale={locale}
                canOpenGame={Boolean(openGame)}
                onOpen={() => setOpen(item)}
                onOpenGame={() => openGameOf(item)}
              />
            ))}
          </div>
        </section>
      ))}
      {open && (
        <NewsPage
          post={open}
          locale={locale}
          game={{
            name: open.game.name,
            icon_url: open.game.icon_url,
            onOpen: openGame
              ? () => {
                  setOpen(null);
                  openGameOf(open);
                }
              : undefined,
          }}
          onClose={() => setOpen(null)}
        />
      )}
    </div>
  );
}

/** How long ago a post was, as an achievement's head says it — in days: Steam's
 * post keeps its day here, not its hour. */
function daysAgo(iso: string, locale: Locale): string {
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return iso;
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const days = Math.max(0, Math.round((today - new Date(y, m - 1, d).getTime()) / 86_400_000));
  if (days === 0) return t(locale, "dayToday").toLowerCase();
  if (days === 1) return t(locale, "dayYesterday").toLowerCase();
  return `${days} ${t(locale, "daysAgo")}`;
}

/** One post, laid out as an achievement post; its frame takes its picture's
 * proportions, within reason. */
function NewsPostCard({
  item,
  locale,
  canOpenGame,
  onOpen,
  onOpenGame,
}: {
  item: NewsItem;
  locale: Locale;
  canOpenGame: boolean;
  onOpen: () => void;
  onOpenGame: () => void;
}) {
  const picture = item.image ?? item.game.icon_url;
  const ratio = useImageRatio(picture, { max: FEED_RATIO_MAX });
  const wide = isWide(ratio);
  return (
    <article
      className={wide ? "post is-link is-wide" : "post is-link"}
      onClick={(e) => {
        if ((e.target as HTMLElement).closest("button")) return;
        onOpen();
      }}
    >
      <div className="post-stage">
        <header className="post-head">
          <button type="button" className="post-avatar" onClick={onOpenGame}>
            <CoverImg src={item.game.icon_url} kind="game" className="news-game-face" />
          </button>
          <span className="post-head-copy">
            <button type="button" className="post-name" onClick={onOpenGame}>
              {item.game.name}
            </button>
            <span className="post-time">{daysAgo(item.date, locale)}</span>
          </span>
        </header>
        <div className="post-track news-track">
          <div className="post-slide">
            <div className="post-media" style={{ aspectRatio: ratio }}>
              <CoverImg src={picture} kind="game" className="post-media-back" />
              <FitImg src={picture} kind="game" mode={wide ? "height" : "contain"} top />
            </div>
            <div className="post-copy">
              <div className="post-title">
                <h2 lang="en">{item.title}</h2>
                {/* Where an achievement has its rarity and points. */}
                <span className="post-marks">{t(locale, item.kind === "patch" ? "newsPatch" : "newsPost")}</span>
              </div>
              {item.excerpt && <p lang="en">{item.excerpt}</p>}
              <button type="button" className="post-game" onClick={onOpenGame} disabled={!canOpenGame}>
                <span className="post-game-name">{item.game.name}</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </article>
  );
}
