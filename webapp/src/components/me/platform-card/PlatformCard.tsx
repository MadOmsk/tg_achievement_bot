import { Icon, PlatformLogo } from "../../shared/lib";
import { t, type Locale } from "../../../i18n";

export type PlatNote = { kind: "error" | "warn" | "info"; text: string };
export type PlatNotes = Partial<Record<"xbox" | "steam" | "psn", PlatNote>>;

export type AccountRow = {
  key: string;
  name: string;
  profileUrl: string | null;
  publishes?: boolean;
  onTogglePublish?: () => void;
  onDisconnect: () => void;
};

export function PlatformCard({
  mark,
  title,
  accounts,
  locale,
  onConnect,
  onAdd,
  onSync,
  notes,
}: {
  mark: string;
  title: string;
  accounts: AccountRow[];
  locale: Locale;
  onConnect: () => void;
  onAdd?: () => void;
  onSync?: () => void;
  notes?: Array<PlatNote | null | undefined>;
}) {
  const linked = accounts.length > 0;
  return (
    <div className={linked ? "plat-card is-linked" : "plat-card"}>
      <div className="plat-card-main">
        <PlatformLogo platform={mark} size={22} />
        <strong className="plat-card-nick">
          {linked ? title : t(locale, "notLinked")}
        </strong>
        {linked ? (
          <div className="plat-card-icons" role="group">
            {onSync ? (
              <button
                type="button"
                onClick={onSync}
                aria-label={t(locale, "sync")}
                title={t(locale, "sync")}
              >
                <Icon name="sync" size={16} />
              </button>
            ) : null}
            {onAdd ? (
              <button
                type="button"
                className="btn sm"
                onClick={onAdd}
              >
                {t(locale, "addPsnAccount")}
              </button>
            ) : null}
          </div>
        ) : (
          <button type="button" className="btn sm" onClick={onConnect}>
            {t(locale, "connect")}
          </button>
        )}
      </div>
      {accounts.map((account) => (
        <div key={account.key} className="plat-account">
          <p className="plat-account-name">{account.name}</p>
          <div className="plat-buttons">
            {account.profileUrl ? (
              <a
                href={account.profileUrl}
                target="_blank"
                rel="noreferrer"
                className="btn sm ghost"
              >
                {t(locale, "profile")}
              </a>
            ) : null}
            {account.onTogglePublish ? (
              <button
                type="button"
                className="btn sm ghost"
                onClick={account.onTogglePublish}
              >
                {t(locale, account.publishes ? "publishingOn" : "publishingOff")}
              </button>
            ) : null}
            <button
              type="button"
              className="btn sm ghost is-danger"
              onClick={account.onDisconnect}
            >
              {t(locale, "disconnect")}
            </button>
          </div>
        </div>
      ))}
      {(notes ?? [])
        .filter((n): n is PlatNote => Boolean(n))
        .map((note) => (
          <p
            key={`${note.kind}:${note.text}`}
            className={`plat-note is-${note.kind}`}
          >
            {note.text}
          </p>
        ))}
    </div>
  );
}
