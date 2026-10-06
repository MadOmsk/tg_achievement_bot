import { useEffect, useState, type ComponentProps } from "react";
import { notificationsApi, type NotificationItem } from "../../../api/notifications/notificationsApi";
import { dayKey, dayLabel, t, timeAgo, type Locale } from "../../../i18n";
import { Avatar, Icon, Sheet, useOpenGame } from "../../shared/lib";
import "./Notifications.css";

/** The bell on Home (#164): how many notices are unread, and the list behind
 * it. A notice is read once tapped, or all at once; a tap opens what it is
 * about — the game of a new post, else the person. */
export function NotificationsBell({
  data,
  locale,
  unread,
  onOpenPerson,
}: {
  data: string;
  locale: Locale;
  /** From /me; the bell's own count takes over once the list was opened. */
  unread: number;
  onOpenPerson: (personId: number) => void;
}) {
  const [count, setCount] = useState(unread);
  const [items, setItems] = useState<NotificationItem[] | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => setCount(unread), [unread]);

  const openGame = useOpenGame();

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    notificationsApi
      .list(data)
      .then((res) => {
        if (cancelled) return;
        setItems(res.items);
        setCount(res.unread);
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      });
    return () => {
      cancelled = true;
    };
  }, [open, data]);

  const markRead = (ids?: number[]) => {
    setItems((list) =>
      list?.map((item) => (!ids || ids.includes(item.id) ? { ...item, read: true } : item)) ?? list,
    );
    setCount((n) => (ids ? Math.max(0, n - ids.length) : 0));
    void notificationsApi.markRead(data, ids).catch(() => undefined);
  };

  const openItem = (item: NotificationItem) => {
    if (!item.read) markRead([item.id]);
    // A notice about nothing to open is only read.
    if (item.person_id == null && !item.game) return;
    setOpen(false);
    if (item.game && openGame) {
      openGame({
        platform: item.game.platform,
        title_id: item.game.title_id,
        name: item.game.name,
        person: item.person_id != null ? { person_id: item.person_id, name: item.name ?? "" } : null,
      });
    } else if (item.person_id != null) {
      onOpenPerson(item.person_id);
    }
  };

  return (
    <>
      <button
        type="button"
        className="bell-button"
        aria-label={t(locale, "notificationsTitle")}
        onClick={() => setOpen(true)}
      >
        <Icon name="bell" size={22} />
        {count > 0 && <span className="bell-count">{count > 9 ? "9+" : count}</span>}
      </button>
      {open && (
        <Sheet mid onClose={() => setOpen(false)}>
          <div className="sheet-content notices-sheet">
            <div className="notices-head">
              <h2>{t(locale, "notificationsTitle")}</h2>
              {count > 0 && (
                <button type="button" className="see-all" onClick={() => markRead()}>
                  {t(locale, "notificationsReadAll")}
                </button>
              )}
            </div>
            {items === null ? (
              <div className="notices-list" aria-busy>
                {[0, 1, 2].map((n) => (
                  <span key={n} className="skel notice-skel" />
                ))}
              </div>
            ) : items.length === 0 ? (
              <p className="empty">{t(locale, "notificationsEmpty")}</p>
            ) : (
              <div className="notices-days">
                {daysOf(items).map((day) => (
                  <section key={day.key} className="notices-day">
                    <span className="feed-day-label">{dayLabel(day.items[0].created_at, locale)}</span>
                    <div className="notices-list">
                      {day.items.map((item) => (
                        <NoticeRow key={item.id} item={item} locale={locale} onOpen={() => openItem(item)} />
                      ))}
                    </div>
                  </section>
                ))}
              </div>
            )}
          </div>
        </Sheet>
      )}
    </>
  );
}

/** Notices in runs of one day, newest first. */
function daysOf(items: NotificationItem[]): { key: string; items: NotificationItem[] }[] {
  const days: { key: string; items: NotificationItem[] }[] = [];
  const sorted = [...items].sort((a, b) => b.created_at.localeCompare(a.created_at));
  for (const item of sorted) {
    const key = dayKey(item.created_at);
    const last = days[days.length - 1];
    if (last && last.key === key) last.items.push(item);
    else days.push({ key, items: [item] });
  }
  return days;
}

/** What a notice is about, as a small mark on its face. */
const BADGE: Partial<Record<string, ComponentProps<typeof Icon>["name"]>> = {
  new_post: "cup",
  new_follower: "people",
  new_friend: "handshake",
  game_news: "feed",
};

/** One notice (owner, 2026-10-06), as an activity feed draws it: a face — the
 * person's, or the game's for its news — marked with what it is about; one
 * line, the name or the game in bold and what happened; under it the game or
 * the post; how long ago at the right. Unread ones are in full light with a
 * dot left of the face; read ones step back. */
function NoticeRow({
  item,
  locale,
  onOpen,
}: {
  item: NotificationItem;
  locale: Locale;
  onOpen: () => void;
}) {
  // A list item from before the short form came has no lead: its whole line.
  const lead = item.lead ?? item.text;
  const badge = BADGE[item.kind];
  return (
    <button type="button" className={item.read ? "notice-row" : "notice-row is-unread"} onClick={onOpen}>
      <span className="notice-face">
        {item.person_id != null ? (
          <Avatar name={item.name ?? "?"} personId={item.person_id} size={44} />
        ) : item.cover ? (
          <img className="notice-cover" src={item.cover} alt="" loading="lazy" />
        ) : (
          <span className="notice-mark">
            <Icon name="bell" size={18} />
          </span>
        )}
        {badge && (
          <span className={`notice-badge is-${item.kind}`} aria-hidden>
            <Icon name={badge} size={9} filled />
          </span>
        )}
      </span>
      <span className="notice-copy">
        <span className="notice-line">
          {item.bold && (
            <>
              <b>{item.bold}</b>{" "}
            </>
          )}
          {lead}
        </span>
        {item.detail && <small className="notice-detail">{item.detail}</small>}
      </span>
      {/* At the right, the same place on every row. */}
      <span className="notice-time">{timeAgo(item.created_at, locale)}</span>
    </button>
  );
}
