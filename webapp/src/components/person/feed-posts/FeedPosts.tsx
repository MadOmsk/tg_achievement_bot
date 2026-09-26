import { useEffect, useState } from "react";
import type { FeedItem } from "../../../api";
import { dayKey, dayLabel, type Locale } from "../../../i18n";
import { feedKey, veiled } from "../utils";
import { useDayJump } from "../day-jump/useDayJump";
import { UnlockCard } from "../unlock-card/UnlockCard";
import { UnlockSlider } from "../unlock-slider/UnlockSlider";

// The tab opens on its first posts at once and builds the rest in the
// background, a few per turn — not on scroll, so nothing pops in under the
// finger, and not all at the start, which held the tap for a second.
const FIRST_POSTS = 4;
const POSTS_PER_TURN = 4;

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
  const jump = useDayJump(items, locale);
  const [built, setBuilt] = useState(FIRST_POSTS);
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
  const total = days.reduce((sum, day) => sum + day.groups.length, 0);
  useEffect(() => {
    if (built >= total) return;
    const id = window.setTimeout(() => setBuilt((n) => n + POSTS_PER_TURN), 60);
    return () => window.clearTimeout(id);
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
      {jump.picker}
    </div>
  );
}
