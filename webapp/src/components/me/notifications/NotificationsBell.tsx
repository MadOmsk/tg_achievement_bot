import { useEffect, useState } from "react";
import { notificationsApi, type NotificationItem } from "../../../api/notifications/notificationsApi";
import { t, timeAgo, type Locale } from "../../../i18n";
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
              <div className="notices-list">
                {items.map((item) => {
                  const body = (
                    <>
                      {item.person_id != null ? (
                        <Avatar name={item.name ?? "?"} personId={item.person_id} size={44} />
                      ) : (
                        <span className="notice-mark">
                          <Icon name="bell" size={20} />
                        </span>
                      )}
                      <span className="notice-copy">
                        <span>{item.text}</span>
                        <small>{timeAgo(item.created_at, locale)}</small>
                      </span>
                      {!item.read && <span className="notice-dot" aria-hidden />}
                    </>
                  );
                  const rowClass = item.read ? "notice-row" : "notice-row is-unread";
                  return item.person_id != null || item.game ? (
                    <button key={item.id} type="button" className={rowClass} onClick={() => openItem(item)}>
                      {body}
                    </button>
                  ) : (
                    <button
                      key={item.id}
                      type="button"
                      className={rowClass}
                      onClick={() => !item.read && markRead([item.id])}
                    >
                      {body}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </Sheet>
      )}
    </>
  );
}
