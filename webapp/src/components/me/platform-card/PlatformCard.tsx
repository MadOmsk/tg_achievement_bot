import { Icon, InfoRow, NavRow, PlatformLogo, RowLink } from "../../shared/lib";
import { t, type Locale } from "../../../i18n";

export type PlatNote = { kind: "error" | "warn" | "info"; text: string };
export type PlatNotes = Partial<Record<"xbox" | "steam" | "psn", PlatNote>>;

export type AccountRow = {
  key: string;
  name: string;
  profileUrl: string | null;
  onDisconnect: () => void;
};

/** One platform as rows of the Accounts group: "connect" when nothing is linked,
 * otherwise each account with profile, sync and unlink as icons (owner, 2026-10-01). */
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
  const logo = <PlatformLogo platform={mark} size={20} />;
  const shownNotes = (notes ?? []).filter((n): n is PlatNote => Boolean(n));

  const icons = (account: AccountRow, withSync: boolean) => (
    <span className="fr-icons" role="group">
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
      {withSync && onSync && (
        <button type="button" onClick={onSync} aria-label={t(locale, "sync")} title={t(locale, "sync")}>
          <Icon name="sync" size={16} />
        </button>
      )}
      <button
        type="button"
        className="is-danger"
        onClick={account.onDisconnect}
        aria-label={t(locale, "disconnect")}
        title={t(locale, "disconnect")}
      >
        <Icon name="off" size={16} />
      </button>
    </span>
  );

  if (accounts.length === 0) {
    return (
      <>
        <InfoRow lead={logo} label={title}>
          <RowLink onClick={onConnect}>{t(locale, "connect")}</RowLink>
        </InfoRow>
        {shownNotes.map((note) => (
          <p key={note.text} className={`fr-note is-${note.kind}`}>
            {note.text}
          </p>
        ))}
      </>
    );
  }

  return (
    <>
      {accounts.map((account, i) => (
        <InfoRow
          key={account.key}
          lead={i === 0 ? logo : <span />}
          label={account.name}
        >
          {icons(account, i === 0)}
        </InfoRow>
      ))}
      {onAdd && <NavRow lead={<span />} label={t(locale, "addAccount")} onClick={onAdd} />}
      {shownNotes.map((note) => (
        <p key={note.text} className={`fr-note is-${note.kind}`}>
          {note.text}
        </p>
      ))}
    </>
  );
}
