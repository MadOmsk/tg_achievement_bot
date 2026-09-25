import { useEffect, useRef, useState } from "react";
import type { FeedItem } from "../../../api";
import { dayKey, dayLabel, type Locale } from "../../../i18n";
import { feedKey, veiled } from "../utils";
import { useDayJump } from "../day-jump/useDayJump";
import { UnlockCard } from "../unlock-card/UnlockCard";
import { UnlockSlider } from "../unlock-slider/UnlockSlider";

// The feed mounts a card (some of them carousels, all with pictures) per post;
// building hundreds at once froze the tab switch. Only the first ones are
// rendered, the rest as the bottom nears.
const FIRST_POSTS = 5;
const MORE_POSTS = 6;

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
  onOpenPerson: (tgId: number) => void;
}) {
  const [limit, setLimit] = useState(FIRST_POSTS);
  const jump = useDayJump(items, locale, () => setLimit(Infinity));
  const sentinel = useRef<HTMLDivElement | null>(null);
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
      head.tg_id === row.tg_id &&
      head.platform === row.platform &&
      head.title_id === row.title_id
    ) {
      last.push(row);
    } else {
      day.groups.push([row]);
    }
  }
  let budget = limit;
  const shown: typeof days = [];
  for (const day of days) {
    if (budget <= 0) break;
    shown.push({ ...day, groups: day.groups.slice(0, budget) });
    budget -= day.groups.length;
  }
  const total = days.reduce((sum, day) => sum + day.groups.length, 0);
  const more = limit < total;

  useEffect(() => {
    const node = sentinel.current;
    if (!node || !more) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setLimit((n) => n + MORE_POSTS);
        }
      },
      { rootMargin: "900px 0px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [more, limit]);

  return (
    <div className="feed-days">
      {shown.map((day, i) => (
        <section
          key={`${day.key}-${i}`}
          className="feed-day"
          ref={jump.register(day.key)}
        >
          {day.label && (
            <button
              type="button"
              className="feed-day-label"
              onClick={() => jump.open(day.iso)}
            >
              {day.label}
            </button>
          )}
          <div className="feed-posts">
            {day.groups.map((group) => {
              const head = group[0];
              const key = `${feedKey(head)}:n${group.length}`;
              if (group.length === 1) {
                const secret = veiled(head, feedKey(head), revealed, showSecrets);
                return (
                  <UnlockCard
                    key={key}
                    item={head}
                    locale={locale}
                    secret={secret}
                    author
                    gameInCopy
                    onOpenPerson={onOpenPerson}
                    onReveal={onReveal}
                  />
                );
              }
              return (
                <UnlockSlider
                  key={key}
                  items={group}
                  locale={locale}
                  revealed={revealed}
                  showSecrets={showSecrets}
                  onReveal={onReveal}
                  onOpenPerson={onOpenPerson}
                  variant="feed"
                />
              );
            })}
          </div>
        </section>
      ))}
      {more && <div ref={sentinel} aria-hidden style={{ height: 1 }} />}
      {jump.picker}
    </div>
  );
}
