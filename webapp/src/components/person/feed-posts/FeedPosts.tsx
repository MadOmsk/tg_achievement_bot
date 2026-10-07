import { useEffect, useRef, useState } from "react";
import type { FeedItem } from "../../../api";
import { dayKey, dayLabel, type Locale } from "../../../i18n";
import { feedKey } from "../utils";
import { useDayJump } from "../day-jump/useDayJump";
import { FeedPost } from "../feed-post/FeedPost";

// The tab opens on its first posts and builds more as the reader nears the
// end, well ahead of the finger (owner, 2026-10-07): a month of posts built at
// once was more than a phone's browser would keep.
const FIRST_POSTS = 8;
const POSTS_PER_STEP = 8;
const AHEAD = "2000px";

export function FeedPosts({
  items,
  locale,
  revealed,
  showSecrets,
  onReveal,
  onOpenPerson,
}: {
  items: FeedItem[];
  locale: Locale;
  revealed: Set<string>;
  showSecrets?: boolean;
  onReveal: (key: string) => void;
  onOpenPerson: (personId: number) => void;
}) {
  const [built, setBuilt] = useState(FIRST_POSTS);
  const end = useRef<HTMLDivElement>(null);
  // Days first, then — inside a day — runs of one person's achievements in one
  // game, which become a carousel.
  const days: Array<{ key: string; label: string; iso: string | null; groups: FeedItem[][] }> = [];
  for (const row of items) {
    const key = dayKey(row.unlocked_at) || "unknown";
    let day = days[days.length - 1];
    if (!day || day.key !== key) {
      day = {
        key,
        label: dayLabel(row.unlocked_at, locale),
        iso: row.unlocked_at,
        groups: [],
      };
      days.push(day);
    }
    const last = day.groups[day.groups.length - 1];
    const head = last?.[0];
    if (
      head &&
      head.person_id === row.person_id &&
      head.platform === row.platform &&
      head.title_id === row.title_id
    ) {
      last.push(row);
    } else {
      day.groups.push([row]);
    }
  }
  const total = days.reduce((sum, day) => sum + day.groups.length, 0);
  // How many posts come before each day ends: what a jump to it needs built.
  const through = new Map<string, number>();
  let count = 0;
  for (const day of days) {
    count += day.groups.length;
    through.set(day.key, count);
  }
  const jump = useDayJump(items, locale, (key) => {
    const need = through.get(key);
    if (need != null) setBuilt((n) => Math.max(n, need));
  });

  useEffect(() => {
    const node = end.current;
    if (!node || built >= total) return;
    const watch = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) setBuilt((n) => n + POSTS_PER_STEP);
      },
      { rootMargin: `0px 0px ${AHEAD} 0px` },
    );
    watch.observe(node);
    return () => watch.disconnect();
  }, [built, total]);

  let budget = built;
  const shown: typeof days = [];
  for (const day of days) {
    if (budget <= 0) break;
    shown.push({ ...day, groups: day.groups.slice(0, budget) });
    budget -= day.groups.length;
  }

  return (
    <div className="feed-days">
      {shown.map((day, i) => (
        <section
          key={`${day.key}-${i}`}
          className="feed-day"
          ref={jump.register(day.key)}
        >
          {day.label && jump.label(day.key, day.label)}
          <div className="feed-posts">
            {day.groups.map((group) => (
              <FeedPost
                key={`${feedKey(group[0])}:n${group.length}`}
                items={group}
                locale={locale}
                revealed={revealed}
                showSecrets={showSecrets}
                onReveal={onReveal}
                onOpenPerson={onOpenPerson}
              />
            ))}
          </div>
        </section>
      ))}
      {built < total && <div ref={end} style={{ height: 1 }} aria-hidden />}
    </div>
  );
}
