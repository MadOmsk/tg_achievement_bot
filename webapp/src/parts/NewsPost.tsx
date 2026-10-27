import type { NewsItem } from "../api";
import { useApp } from "../app/context";
import { clockOf } from "../core/post-text";
import { tick } from "../core/haptic";
import { dayKey, timeAgo } from "../i18n";
import { KindChip } from "./KindChip";
import { Cover } from "../ui/Pic";

/** A developer's post in the feed, laid out as a people's post is: who (the
 * game), when, then the post itself as one row. */
export function NewsPost({ item }: { item: NewsItem }) {
  const { locale, open } = useApp();
  const openGame = () => {
    tick();
    open({
      kind: "game",
      ref: { platform: item.game.platform, title_id: item.game.title_id, name: item.game.name, icon_url: item.game.icon_url },
    });
  };
  return (
    <article className="post">
      <div className="post-by">
        <button type="button" aria-label={item.game.name} onClick={openGame}>
          <Cover src={item.game.icon_url} className="post-news-cover" />
        </button>
        <span className="post-who">
          <span className="post-top">
            <button type="button" className="post-name clamp-1" onClick={openGame}>
              {item.game.name}
            </button>
            <span className="post-time">
              {dayKey(item.date) === dayKey(new Date().toISOString()) ? timeAgo(item.date, locale) : clockOf(item.date, locale)}
            </span>
          </span>
          <span className="post-game">
            <KindChip kind={item.kind} />
          </span>
        </span>
      </div>
      <div className="post-items">
        <button
          type="button"
          className="ach-row ach-row-plain"
          onClick={() => {
            tick();
            open({ kind: "news", appid: item.appid, gid: item.gid, item, game: item.game });
          }}
        >
          {item.image && <Cover src={item.image} className="ach-pic-wide" />}
          <span className="ach-text">
            <span className="ach-name clamp-2">{item.title}</span>
            {item.excerpt && <span className="ach-desc clamp-2">{item.excerpt}</span>}
          </span>
        </button>
      </div>
    </article>
  );
}
