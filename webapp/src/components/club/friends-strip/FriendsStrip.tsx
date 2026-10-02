import type { OnlineMember } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { Avatar, Icon, isOnline } from "../../shared/lib";
import { rankPeople } from "../utils";

export function FriendsStrip({
  members,
  locale,
  limit,
  onOpen,
  onSeeAll,
  onFind,
}: {
  members: OnlineMember[];
  locale: Locale;
  limit: number;
  onOpen: (tgId: number) => void;
  onSeeAll: () => void;
  onFind: () => void;
}) {
  const pool = rankPeople(members);
  if (pool.length === 0) {
    return (
      <>
        <div className="section-head">
          <h1 className="kicker" style={{ margin: 0 }}>
            {t(locale, "friends")}
          </h1>
        </div>
        <p className="friends-empty">{t(locale, "friendsEmpty")}</p>
        <button type="button" className="find-btn is-wide" onClick={onFind}>
          <Icon name="search" size={18} />
          <span>{t(locale, "find")}</span>
        </button>
      </>
    );
  }
  const shown = pool.slice(0, limit);
  return (
    <>
      <div className="section-head">
        <span className="section-title-group">
          <h1 className="kicker" style={{ margin: 0 }}>
            {t(locale, "friends")}
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
            <Avatar
              name={m.name}
              tgId={m.tg_id}
              online={isOnline(m)}
              platform={m.platform}
              size={80}
            />
            <strong>{m.name}</strong>
            <p>{m.playing ? m.title_name : m.status}</p>
          </button>
        ))}
      </div>
    </>
  );
}
