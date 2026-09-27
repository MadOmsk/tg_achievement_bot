import { useState } from "react";
import type { FeedItem } from "../../../api";
import { dayKey, dayLabel, t, type Locale } from "../../../i18n";
import { Sheet } from "../../shared/lib";
import { feedKey, veiled } from "../utils";
import { useDayJump } from "../day-jump/useDayJump";
import { FeedRow } from "../feed-row/FeedRow";
import { UnlockCard } from "../unlock-card/UnlockCard";

export function FeedList({
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
  onOpenPerson?: (tgId: number) => void;
}) {
  const [item, setItem] = useState<FeedItem | null>(null);
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
          {group.label && (
            <button
              type="button"
              className="feed-day-label"
              onClick={() => jump.open(group.items[0].unlocked_at)}
            >
              {group.label}
            </button>
          )}
          {group.items.map((row) => {
            const key = feedKey(row);
            const secret = veiled(row, key, revealed, showSecrets);
            return (
              <FeedRow
                key={key}
                row={row}
                secret={secret}
                onOpen={setItem}
              />
            );
          })}
        </section>
      ))}
      {jump.picker}
      {item && (
        <Sheet
          mid
          onClose={() => setItem(null)}
          closeLabel={t(locale, "close")}
          noClose
        >
          <div className="sheet-unlock">
            <UnlockCard
              item={item}
              locale={locale}
              secret={veiled(item, feedKey(item), revealed, showSecrets)}
              author
              gameInCopy
              onOpenPerson={onOpenPerson}
              onReveal={onReveal}
            />
          </div>
        </Sheet>
      )}
    </div>
  );
}
