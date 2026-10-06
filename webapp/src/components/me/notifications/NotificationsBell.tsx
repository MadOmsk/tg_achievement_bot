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
              <div className="notices-list">
                {items.map((item) => (
                  <NoticeRow key={item.id} item={item} locale={locale} onOpen={() => openItem(item)} />
                ))}
              </div>
            )}
          </div>
        </Sheet>
      )}
    </>
  );
}

/** One notice, short (owner, 2026-10-06): a small face, the name in bold and
 * what happened in one line, the game under it, how long ago at the right. Unread ones
 * stand on a tint, with no dot. */
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
  const named = item.person_id != null && item.name && lead !== item.text;
  return (
    <button type="button" className={item.read ? "notice-row" : "notice-row is-unread"} onClick={onOpen}>
      {item.person_id != null ? (
        <Avatar name={item.name ?? "?"} personId={item.person_id} size={34} />
      ) : item.image ? (
        <img className="notice-pic" src={item.image} alt="" loading="lazy" />
      ) : (
        <span className="notice-mark">
          <Icon name="bell" size={16} />
        </span>
      )}
      <span className="notice-copy">
        <span className="notice-line">
          {named ? (
            <>
              <b>{item.name}</b> {lead}
            </>
          ) : (
            lead
          )}
        </span>
        {item.detail && <small>{item.detail}</small>}
      </span>
      <span className="notice-time">{timeAgo(item.created_at, locale)}</span>
    </button>
  );
}
