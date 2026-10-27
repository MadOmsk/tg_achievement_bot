import { useState } from "react";
import { useApp } from "../app/context";
import { achOfFeed } from "../app/views";
import { clockOf } from "../core/post-text";
import { tick } from "../core/haptic";
import { dayKey, plural, timeAgo } from "../i18n";
import { Face } from "../ui/Face";
import { Cover } from "../ui/Pic";
import { AchRow } from "./AchRow";
import { progressOf, type Post as PostData } from "./posts";

const SHOWN = 3;

/** One post of the feed: who, when, what they earned, and the game it is in
 * with their progress. Several people means they earned it together. */
export function Post({ post }: { post: PostData }) {
  const { tr, locale, open } = useApp();
  const [all, setAll] = useState(false);
  const together = post.people.length > 1;
  const events = all ? post.events : post.events.slice(0, SHOWN);
  const hidden = post.events.length - events.length;
  const newest = post.events[0].items[0].unlocked_at;
  const oldest = post.events[post.events.length - 1].items[0].unlocked_at;
  const time =
    newest && dayKey(newest) === dayKey(new Date().toISOString())
      ? timeAgo(newest, locale)
      : newest && oldest && clockOf(newest, locale) !== clockOf(oldest, locale)
      ? `${clockOf(oldest, locale)}–${clockOf(newest, locale)}`
      : newest
        ? clockOf(newest, locale)
        : "";
  const progress = progressOf(post);
  const mine = progress[0];

  const openGame = () => {
    tick();
    open({
      kind: "game",
      ref: {
        platform: post.platform,
        title_id: post.titleId,
        name: post.game,
        icon_url: post.gameIcon,
        person: { person_id: post.people[0].id, name: post.people[0].name },
      },
    });
  };
  const count = together ? tr("together") : mine.total ? `${mine.unlocked}/${mine.total}` : "";

  return (
    <article className="post">
      <div className="post-by">
        {together ? (
          <span className="post-duo">
            {post.people.slice(0, 2).map((p, i) => (
              <button
                key={p.id}
                type="button"
                style={i === 0 ? { left: 0, top: 0, zIndex: 1 } : { right: -4, bottom: -10, zIndex: 2 }}
                aria-label={p.name}
                onClick={() => open({ kind: "person", personId: p.id })}
              >
                <Face personId={p.id} name={p.name} size={i === 0 ? 36 : 24} />
              </button>
            ))}
          </span>
        ) : (
          <button type="button" aria-label={post.people[0].name} onClick={() => open({ kind: "person", personId: post.people[0].id })}>
            <Face personId={post.people[0].id} name={post.people[0].name} size={40} />
          </button>
        )}
        <span className="post-who">
          <span className="post-top">
            <button
              type="button"
              className="post-name clamp-1"
              onClick={() => open({ kind: "person", personId: post.people[0].id })}
            >
              {together ? post.people.map((p) => p.name).join(` ${tr("and")} `) : post.people[0].name}
            </button>
            <span className="post-time">{time}</span>
          </span>
          <button type="button" className="post-game" onClick={openGame}>
            <Cover src={post.gameIcon} className="post-game-cover" />
            <span className="post-game-name clamp-1">{post.game}</span>
            {count && <b className={`post-game-num${together ? " post-game-together" : ""}`}>{count}</b>}
          </button>
        </span>
      </div>

      <div className="post-items">
        {events.map((event) => {
          const item = event.items[0];
          const ach = achOfFeed(item);
          if (event.items.length > 1) {
            ach.together = event.items.map((i) => ({ id: i.person_id, name: i.person, at: i.unlocked_at }));
          }
          return <AchRow key={`${item.achievement_id}:${event.at}`} ach={ach} plain />;
        })}
      </div>
      {hidden > 0 && (
        <button
          type="button"
          className="post-more"
          onClick={() => {
            tick();
            setAll(true);
          }}
        >
          {tr("more")} {hidden} {plural(locale, hidden, ["achOne", "achFew", "achMany"])}
        </button>
      )}
    </article>
  );
}

/** A post while the feed is on its way: its very shape, in skeleton. */
export function PostSkel({ rows = 2 }: { rows?: number }) {
  return (
    <div className="post post-skel" aria-hidden="true">
      <div className="post-by">
        <span className="skel skel-face" />
        <span className="post-who">
          <span className="skel skel-line" style={{ width: "45%" }} />
          <span className="skel skel-line" style={{ width: "70%" }} />
        </span>
      </div>
      <div className="post-items">
        {Array.from({ length: rows }, (_, i) => (
          <div key={i} className="ach-row ach-row-plain">
            <span className="skel ach-pic-wide" />
            <span className="ach-text">
              <span className="skel skel-line" style={{ width: "60%" }} />
              <span className="skel skel-line" style={{ width: "90%" }} />
              <span className="skel skel-line" style={{ width: "35%" }} />
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
