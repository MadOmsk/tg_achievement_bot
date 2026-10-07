import { t, type Locale } from "../../../i18n";
import { Avatar, isOnline } from "../../shared/lib";
import { HandleName } from "../../shared/lib/handle-name/HandleName";

export function PeopleHits({
  members,
  locale,
  onOpen,
}: {
  members: Array<{
    person_id: number;
    name: string;
    playing?: boolean;
    state?: string | null;
    title_name?: string | null;
    status?: string;
    platform?: string | null;
  }>;
  locale: Locale;
  onOpen: (personId: number) => void;
}) {
  if (members.length === 0) return null;
  return (
    <>
      <p className="kicker">{t(locale, "people")}</p>
      <div className="friends wrap">
        {members.map((m) => (
          <button
            key={m.person_id}
            type="button"
            className="friend"
            onClick={() => onOpen(m.person_id)}
          >
            <Avatar
              name={m.name}
              personId={m.person_id}
              online={isOnline(m)}
              platform={m.platform}
              size={72}
            />
            <strong>
              <HandleName text={m.name} />
            </strong>
            <p>{m.playing ? m.title_name : m.status}</p>
          </button>
        ))}
      </div>
    </>
  );
}
