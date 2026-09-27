import { useRef, useState, type ReactNode } from "react";
import type { FeedItem } from "../../../api";
import { dayKey, type Locale } from "../../../i18n";
import { DayPicker } from "../../shared/lib";

/**
 * Day labels that open a calendar and scroll to the chosen day. A list
 * registers each day's section with `register`, puts a `DayLabel` on it and
 * renders `picker` once.
 */
export function useDayJump(items: FeedItem[], locale: Locale) {
  const [from, setFrom] = useState<Date | null>(null);
  const nodes = useRef(new Map<string, HTMLElement>());

  const counts = new Map<string, number>();
  for (const row of items) {
    const key = dayKey(row.unlocked_at);
    if (key) counts.set(key, (counts.get(key) ?? 0) + 1);
  }

  const register = (key: string) => (node: HTMLElement | null) => {
    if (node) nodes.current.set(key, node);
    else nodes.current.delete(key);
  };

  const jumpTo = (key: string) => {
    setFrom(null);
    // Let the sheet start closing first, so the scroll is not fighting it;
    // retry briefly in case the day has not mounted yet.
    let tries = 0;
    const go = () => {
      const node = nodes.current.get(key);
      if (node) {
        node.scrollIntoView({ behavior: "smooth", block: "start" });
        // Posts far away are only estimated in height until they are rendered
        // (content-visibility): once the scroll has passed them, settle exactly.
        window.setTimeout(() => node.scrollIntoView({ block: "start" }), 900);
        window.setTimeout(() => node.scrollIntoView({ block: "start" }), 1500);
      } else if (tries++ < 12) {
        window.setTimeout(go, 100);
      }
    };
    window.setTimeout(go, 120);
  };

  const picker: ReactNode =
    from && counts.size > 0 ? (
      <DayPicker
        locale={locale}
        days={counts}
        start={from}
        onPick={jumpTo}
        onClose={() => setFrom(null)}
      />
    ) : null;

  return {
    register,
    open: (iso: string | null) => setFrom(new Date(iso ?? Date.now())),
    picker,
  };
}
