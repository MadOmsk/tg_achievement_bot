import type { OnlineMember } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { Avatar, Sheet, isOnline } from "../../shared/lib";
import { rankPeople } from "../utils";
import { HandleName } from "../../shared/lib/handle-name/HandleName";

export function RosterSheet({
  members,
  locale,
  onClose,
  onOpen,
}: {
  members: OnlineMember[];
  locale: Locale;
  onClose: () => void;
  onOpen: (personId: number) => void;
}) {
  const rows = rankPeople(members);
  return (
    <Sheet onClose={onClose} mid title={t(locale, "friends")}>
      <div className="sheet-content score-sheet picker-sheet">
        {rows.length === 0 ? (
          <p className="empty">{t(locale, "nobodyOnline")}</p>
        ) : (
          <div className="picker-list">
            {rows.map((m) => (
              <button
                key={m.person_id}
                type="button"
                className="picker-row is-person"
                onClick={() => onOpen(m.person_id)}
              >
                <Avatar
                  name={m.name}
                  personId={m.person_id}
                  online={isOnline(m)}
                  platform={m.platform}
                  size={40}
                />
                <span className="picker-row-copy">
                  <strong>
                    <HandleName text={m.name} />
                  </strong>
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
