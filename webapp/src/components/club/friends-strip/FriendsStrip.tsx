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
}: {
  members: OnlineMember[];
  locale: Locale;
  limit: number;
  onOpen: (tgId: number) => void;
  onSeeAll: () => void;
}) {
  const pool = rankPeople(members);
  if (pool.length === 0) return null;
  const shown = pool.slice(0, limit);
  return (
    <>
      <div className="section-head">
        <h1 className="kicker" style={{ margin: 0 }}>
          {t(locale, "friends")}
        </h1>
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
