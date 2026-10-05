import type { OnlineMember } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { Avatar, Icon, isOnline } from "../../shared/lib";
import { rankPeople } from "../utils";
import { FriendMark } from "../../people/friend-mark/FriendMark";
import { HandleName } from "../../shared/lib/handle-name/HandleName";

export function FriendsStrip({
  members,
  locale,
  limit,
  onOpen,
  onSeeAll,
  onFind,
  emptyText,
  friendIds,
}: {
  members: OnlineMember[];
  locale: Locale;
  limit: number;
  onOpen: (tgId: number) => void;
  onSeeAll: () => void;
  /** Your own strip offers a search when empty; somebody else's only says so. */
  onFind?: () => void;
  emptyText?: string;
  /** The viewer's friends among them, marked on their faces. */
  friendIds?: Set<number>;
}) {
  // Friends first, then as everywhere: playing, online, the rest.
  const pool = rankPeople(members).sort(
    (a, b) => Number(Boolean(friendIds?.has(b.tg_id))) - Number(Boolean(friendIds?.has(a.tg_id))),
  );
  if (pool.length === 0) {
    return (
      <>
        <div className="section-head">
          <h1 className="kicker" style={{ margin: 0 }}>
            {t(locale, "peopleFollowing")}
          </h1>
          {onFind && (
            <button type="button" className="see-all" onClick={onFind}>
              <span>{t(locale, "find")}</span>
              <Icon name="forward" size={16} />
            </button>
          )}
        </div>
        <p className="friends-empty">{emptyText ?? t(locale, "friendsEmpty")}</p>
      </>
    );
  }
  const shown = pool.slice(0, limit);
  return (
    <>
      <div className="section-head">
        <span className="section-title-group">
          <h1 className="kicker" style={{ margin: 0 }}>
            {t(locale, "peopleFollowing")}
          </h1>
          <span className="section-count">{pool.length}</span>
        </span>
        <button type="button" className="see-all" onClick={onSeeAll}>
          <span>{t(locale, "seeAll")}</span>
          <Icon name="forward" size={16} />
        </button>
      </div>
      <div className="friends">
        {shown.map((m) => (
          <button
            key={m.tg_id}
            type="button"
            className="friend"
            onClick={() => onOpen(m.tg_id)}
          >
            <FriendMark friend={Boolean(friendIds?.has(m.tg_id))} label={t(locale, "friends")} big>
              <Avatar
                name={m.name}
                tgId={m.tg_id}
                online={isOnline(m)}
                platform={m.platform}
                size={80}
              />
            </FriendMark>
            <strong>
              <HandleName text={m.name} />
            </strong>
            {(m.playing ? m.title_name : m.status) && <p>{m.playing ? m.title_name : m.status}</p>}
          </button>
        ))}
      </div>
    </>
  );
}
