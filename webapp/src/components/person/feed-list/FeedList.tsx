import type { FeedItem } from "../../../api";
import { dayKey, dayLabel, type Locale } from "../../../i18n";
import { useOpenAchievement } from "../../shared/lib";
import { feedKey, veiled } from "../utils";
import { useDayJump } from "../day-jump/useDayJump";
import { FeedRow } from "../feed-row/FeedRow";

export function FeedList({
  items,
  locale,
  revealed,
  showSecrets,
  onReveal,
}: {
  items: FeedItem[];
  locale: Locale;
  revealed: Set<string>;
  showSecrets?: boolean;
  onReveal: (key: string) => void;
  /** Kept for callers; an achievement's page names its game, not its author. */
  onOpenPerson?: (personId: number) => void;
}) {
  // A row opens the achievement on its own page, as a post does (owner, 2026-10-09).
  const openAchievement = useOpenAchievement();
  const setItem = (row: FeedItem) => openAchievement?.(row);
  const jump = useDayJump(items, locale);
  const groups: Array<{ key: string; label: string; items: FeedItem[] }> = [];
  for (const row of items) {
    const key = dayKey(row.unlocked_at) || "unknown";
    const last = groups[groups.length - 1];
    if (last && last.key === key) last.items.push(row);
    else
      groups.push({
        key,
        label: dayLabel(row.unlocked_at, locale),
        items: [row],
      });
  }
  return (
    <div className="feed">
      {groups.map((group, i) => (
        <section
          key={`${group.key}-${i}`}
          className="feed-day"
          ref={jump.register(group.key)}
        >
          {group.label && jump.label(group.key, group.label)}
          {group.items.map((row) => {
            const key = feedKey(row);
            const secret = veiled(row, key, revealed, showSecrets);
            return (
              <FeedRow
                key={key}
                row={row}
                secret={secret}
                onOpen={setItem}
                onToggleReveal={onReveal}
              />
            );
          })}
        </section>
      ))}
    </div>
  );
}
