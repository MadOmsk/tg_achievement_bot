import { useRef } from "react";
import type { FeedItem } from "../../../api";
import { dayKey, type Locale } from "../../../i18n";
import { DropdownArrow } from "../../shared/lib";
import { DayCalendar } from "./DayCalendar";

/**
 * Day labels that open the month's calendar under them (owner, 2026-10-07: no
 * drawer, no long list) and scroll to the chosen day. A list registers each
 * day's section with `register` and draws its label with `label`.
 */
export function useDayJump(
  items: FeedItem[],
  locale: Locale,
  /** Called before a jump: a list that builds lazily builds up to that day. */
  ensure?: (key: string) => void,
) {
  const nodes = useRef(new Map<string, HTMLElement>());

  const byKey = new Map<string, { key: string; iso: string; count: number }>();
  for (const row of items) {
    const key = dayKey(row.unlocked_at);
    if (!key || !row.unlocked_at) continue;
    const day = byKey.get(key);
    if (day) day.count += 1;
    else byKey.set(key, { key, iso: row.unlocked_at, count: 1 });
  }
  const counts = new Map([...byKey.values()].map((day) => [day.key, day.count]));

  const register = (key: string) => (node: HTMLElement | null) => {
    if (node) nodes.current.set(key, node);
    else nodes.current.delete(key);
  };

  const jumpTo = (key: string) => {
    ensure?.(key);
    // Retry briefly in case the day has not mounted yet.
    let tries = 0;
    const go = () => {
      const node = nodes.current.get(key);
      if (node) {
        node.scrollIntoView({ behavior: "smooth", block: "start" });
        // Posts far away are only estimated in height until they are rendered
        // (content-visibility): once the scroll has passed them, settle exactly.
        window.setTimeout(() => node.scrollIntoView({ block: "start" }), 900);
        window.setTimeout(() => node.scrollIntoView({ block: "start" }), 1500);
      } else if (tries++ < 30) {
        window.setTimeout(go, 100);
      }
    };
    window.setTimeout(go, 60);
  };

  const label = (key: string, text: string) => (
    <DayCalendar
      className="dd-trigger feed-day-label"
      locale={locale}
      days={counts}
      current={key}
      onPick={jumpTo}
      trigger={
        <>
          {text}
          <DropdownArrow />
        </>
      }
    />
  );

  return { register, label };
}
