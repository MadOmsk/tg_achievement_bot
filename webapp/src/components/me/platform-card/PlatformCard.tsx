import { Icon, PlatformLogo } from "../../shared/lib";
import { t, type Locale } from "../../../i18n";

export type PlatNote = { kind: "error" | "warn" | "info"; text: string };
export type PlatNotes = Partial<Record<"xbox" | "steam" | "psn", PlatNote>>;

export type AccountRow = {
  key: string;
  name: string;
  profileUrl: string | null;
  onDisconnect: () => void;
};

/** One platform: its name, then every account it holds — profile, sync and unlink
 * as icons in the account's own row (owner, 2026-10-01). */
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
  const single = accounts.length === 1;
  // Profile, sync and unlink as icons in the row of the account they belong to.
  const icons = (account: AccountRow, withSync: boolean) => (
    <div className="plat-card-icons" role="group">
      {account.profileUrl ? (
        <a
          href={account.profileUrl}
          target="_blank"
          rel="noreferrer"
          aria-label={t(locale, "profile")}
          title={t(locale, "profile")}
        >
          <Icon name="link" size={16} />
        </a>
      ) : (
        <span className="is-disabled" aria-hidden>
          <Icon name="link" size={16} />
        </span>
      )}
      {withSync && onSync ? (
        <button
          type="button"
          onClick={onSync}
          aria-label={t(locale, "sync")}
          title={t(locale, "sync")}
        >
          <Icon name="sync" size={16} />
        </button>
      ) : withSync ? (
        <span className="is-disabled" aria-hidden>
          <Icon name="sync" size={16} />
        </span>
      ) : null}
      <button
        type="button"
        className="is-danger"
        onClick={account.onDisconnect}
        aria-label={t(locale, "disconnect")}
        title={t(locale, "disconnect")}
      >
        <Icon name="off" size={16} />
      </button>
    </div>
  );
  return (
    <div className={linked ? "plat-card is-linked" : "plat-card"}>
      <div className="plat-card-main">
        <PlatformLogo platform={mark} size={22} />
        <strong className="plat-card-nick">
          {linked ? (single ? accounts[0].name : title) : title}
        </strong>
        {linked ? (
          single ? (
            icons(accounts[0], true)
          ) : null
        ) : (
          <button type="button" className="btn sm" onClick={onConnect}>
            {t(locale, "connect")}
          </button>
        )}
      </div>
      {linked && !single
        ? accounts.map((account) => (
            <div key={account.key} className="plat-card-main plat-card-sub">
              <strong className="plat-card-nick">{account.name}</strong>
              {icons(account, false)}
            </div>
          ))
        : null}
      {linked && onAdd ? (
        <div className="plat-buttons plat-buttons-foot">
          <button type="button" className="btn sm ghost" onClick={onAdd}>
            {t(locale, "addPsnAccount")}
          </button>
        </div>
      ) : null}
      {(notes ?? [])
        .filter((n): n is PlatNote => Boolean(n))
        .map((note) => (
          <p key={`${note.kind}:${note.text}`} className={`plat-note is-${note.kind}`}>
            {note.text}
          </p>
        ))}
    </div>
  );
}
