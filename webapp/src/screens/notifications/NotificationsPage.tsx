import { useMemo } from "react";
import { notificationsApi, type NotificationItem } from "../../api/notifications/notificationsApi";
import { useApp } from "../../app/context";
import { useLoad } from "../../app/useLoad";
import { clockOf } from "../../core/post-text";
import { tick } from "../../core/haptic";
import { dayKey, dayLabel } from "../../i18n";
import { Button, Empty } from "../../ui/Controls";
import { Face } from "../../ui/Face";
import { Icon } from "../../ui/Icon";
import { Page } from "../../ui/Page";
import { Cover } from "../../ui/Pic";
import { GoMark } from "../../ui/GoMark";
import "./Notifications.css";

export function NotificationsPage({ onClose, layer }: { onClose: () => void; layer: string }) {
  const { data, tr, locale, me, setMe, open } = useApp();
  const list = useLoad("notifications", () => notificationsApi.list(data));
  const items = list.data?.items ?? [];
  const days = useMemo(() => {
    const out: Array<{ key: string; label: string; items: NotificationItem[] }> = [];
    for (const item of items) {
      const key = dayKey(item.created_at);
      let day = out[out.length - 1];
      if (!day || day.key !== key) {
        day = { key, label: dayLabel(item.created_at, locale), items: [] };
        out.push(day);
      }
      day.items.push(item);
    }
    return out;
  }, [items, locale]);
  const unread = items.filter((i) => !i.read).length;

  const markRead = async (ids?: number[]) => {
    try {
      const res = await notificationsApi.markRead(data, ids);
      if (list.data) {
        list.set({
          ...list.data,
          unread: res.unread,
          items: list.data.items.map((i) => (!ids || ids.includes(i.id) ? { ...i, read: true } : i)),
        });
      }
      setMe({ ...me, notifications_unread: res.unread });
    } catch {
      // Still opens what it is about; it stays unread.
    }
  };

  const go = (item: NotificationItem) => {
    tick();
    if (!item.read) void markRead([item.id]);
    if (item.kind === "pass_reward" || item.kind === "pass_level" || item.kind === "season_start") {
      open({ kind: "pass" });
    } else if (item.news) {
      open({
        kind: "news",
        appid: item.news.appid,
        gid: item.news.gid,
        item: null,
        game: item.game ? { ...item.game, icon_url: item.cover ?? null } : null,
      });
    } else if (item.game && item.achievement_id) {
      open({
        kind: "achievementRef",
        platform: item.game.platform,
        titleId: item.game.title_id,
        achievementId: item.achievement_id,
        person: item.person_id ? { id: item.person_id, name: item.name ?? "" } : null,
      });
    } else if (item.game) {
      open({
        kind: "game",
        ref: {
          game_id: item.game.game_id ?? undefined,
          platform: item.game.platform,
          title_id: item.game.title_id,
          name: item.game.name,
          person: item.person_id ? { person_id: item.person_id, name: item.name ?? "" } : null,
        },
      });
    } else if (item.person_id) {
      open({ kind: "person", personId: item.person_id });
    } else if (item.kind === "xbox_login_dead" || item.kind === "psn_token_dead") {
      open({ kind: "settings", pane: "accounts" });
    }
  };

  return (
    <Page
      title={tr("notificationsTitle")}
      onBack={onClose}
      layer={layer}
      actions={
        unread > 0 ? (
          <button type="button" className="link-btn" onClick={() => void markRead()}>
            {tr("notificationsReadAll")}
          </button>
        ) : null
      }
    >
      {!list.data && list.loading && (
        <div className="group">
          <div className="group-items">
            {[0, 1, 2].map((i) => (
              <span key={i} className="row skel" style={{ height: 72 }} />
            ))}
          </div>
        </div>
      )}
      {list.error && !list.data ? <Empty icon="refresh" title={tr("loadFailed")} action={<Button variant="tonal" onClick={list.reload}>{tr("retry")}</Button>} /> : null}
      {list.data && items.length === 0 && <Empty icon="bell" title={tr("notificationsEmpty")} />}
      {days.map((d) => (
        <section key={d.key} className="nt-day">
          <h2 className="feed-day-head">{d.label}</h2>
          <div className="group">
            <div className="group-items">
              {d.items.map((item) => (
                <Moment key={item.id} item={item} onOpen={() => go(item)} />
              ))}
            </div>
          </div>
        </section>
      ))}
    </Page>
  );
}

/** One notice, one compact row, as a messenger's: who (a face, a game's
 * cover), what happened in one sentence, the game under it, the time in the
 * corner and the achievement's or the post's picture at the end. */
function Moment({ item, onOpen }: { item: NotificationItem; onOpen: () => void }) {
  const { locale } = useApp();
  const alert = item.kind === "xbox_login_dead" || item.kind === "psn_token_dead";
  const lead = item.person_id ? (
    <Face personId={item.person_id} name={item.name ?? "?"} size={44} />
  ) : item.cover ? (
    <Cover src={item.cover} className="nt-cover" />
  ) : (
    <span className="nt-icon shape-cookie9">
      <Icon name={alert ? "key" : "bell"} size={20} />
    </span>
  );
  const what = item.lead.replace(/^—\s*/, "");
  const pic = item.image && item.image !== item.cover ? item.image : null;
  return (
    <button type="button" className={`row row-tap nt-row${item.read ? "" : " nt-unread"}${alert ? " nt-alert" : ""}`} onClick={onOpen}>
      {lead}
      <span className="row-text">
        <span className="nt-text clamp-2">
          {item.bold && <b>{item.bold} </b>}
          {what}
        </span>
        {item.detail && <span className="row-sub clamp-1">{item.detail}</span>}
      </span>
      <span className="nt-end">
        <span className="nt-time">{clockOf(item.created_at, locale)}</span>
        {pic ? <Cover src={pic} className="nt-pic" /> : alert ? <GoMark /> : null}
      </span>
    </button>
  );
}
