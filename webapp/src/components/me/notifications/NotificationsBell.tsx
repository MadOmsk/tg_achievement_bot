import { useEffect, useState } from "react";
import { notificationsApi, type NotificationItem } from "../../../api/notifications/notificationsApi";
import { t, timeAgo, type Locale } from "../../../i18n";
import { Avatar, Icon, Sheet } from "../../shared/lib";
import "./Notifications.css";

/** The bell on Home (#164): how many notices are unread, and the list behind
 * it. Opening the list marks them read; a notice about somebody opens them. */
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

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    notificationsApi
      .list(data)
      .then((res) => {
        if (cancelled) return;
        setItems(res.items);
        if (res.unread > 0) {
          setCount(0);
          void notificationsApi.markRead(data).catch(() => undefined);
        }
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      });
    return () => {
      cancelled = true;
    };
  }, [open, data]);

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
            <h2>{t(locale, "notificationsTitle")}</h2>
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
                        <Avatar name={item.name ?? "?"} personId={item.person_id} size={36} />
                      ) : (
                        <span className="notice-mark">
                          <Icon name="bell" size={18} />
                        </span>
                      )}
                      <span className="notice-copy">
                        <span>{item.text}</span>
                        <small>{timeAgo(item.created_at, locale)}</small>
                      </span>
                      {!item.read && <span className="notice-dot" aria-hidden />}
                    </>
                  );
                  return item.person_id != null ? (
                    <button
                      key={item.id}
                      type="button"
                      className="notice-row"
                      onClick={() => {
                        setOpen(false);
                        onOpenPerson(item.person_id as number);
                      }}
                    >
                      {body}
                    </button>
                  ) : (
                    <div key={item.id} className="notice-row">
                      {body}
                    </div>
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
