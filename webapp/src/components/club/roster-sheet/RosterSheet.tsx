import type { OnlineMember } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { Avatar, Sheet, isOnline } from "../../shared/lib";
import { rankPeople } from "../utils";

export function RosterSheet({
  members,
  locale,
  onClose,
  onOpen,
}: {
  members: OnlineMember[];
  locale: Locale;
  onClose: () => void;
  onOpen: (tgId: number) => void;
}) {
  const rows = rankPeople(members);
  return (
    <Sheet onClose={onClose} closeLabel={t(locale, "close")} noClose mid>
      <div className="sheet-content score-sheet picker-sheet">
        <h2>{t(locale, "friends")}</h2>
        {rows.length === 0 ? (
          <p className="empty">{t(locale, "nobodyOnline")}</p>
        ) : (
          <div className="picker-list">
            {rows.map((m) => (
              <button
                key={m.tg_id}
                type="button"
                className="picker-row is-person"
                onClick={() => onOpen(m.tg_id)}
              >
                <Avatar
                  name={m.name}
                  tgId={m.tg_id}
                  online={isOnline(m)}
                  platform={m.platform}
                  size={40}
                />
                <span className="picker-row-copy">
                  <strong>{m.name}</strong>
                  <p>{m.playing ? m.title_name : m.status}</p>
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </Sheet>
  );
}
