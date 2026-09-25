import { Icon, PlatformLogo } from "../../shared/lib";
import { t, type Locale } from "../../../i18n";

export type PlatNote = { kind: "error" | "warn" | "info"; text: string };
export type PlatNotes = Partial<Record<"xbox" | "steam" | "psn", PlatNote>>;

export function PlatformCard({
  mark,
  linked,
  name,
  profileUrl,
  locale,
  onConnect,
  onDisconnect,
  onSync,
  notes,
}: {
  mark: string;
  linked: boolean;
  name: string;
  profileUrl: string | null;
  locale: Locale;
  onConnect: () => void;
  onDisconnect: () => void;
  onSync?: () => void;
  notes?: Array<PlatNote | null | undefined>;
}) {
  return (
    <div className={linked ? "plat-card is-linked" : "plat-card"}>
      <div className="plat-card-main">
        <PlatformLogo platform={mark} size={22} />
        <strong className="plat-card-nick">
          {linked ? name : t(locale, "notLinked")}
        </strong>
        {linked ? (
          <div className="plat-card-icons" role="group">
            {profileUrl ? (
              <a
                href={profileUrl}
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
            {onSync ? (
              <button
                type="button"
                onClick={onSync}
                aria-label={t(locale, "sync")}
                title={t(locale, "sync")}
              >
                <Icon name="sync" size={16} />
              </button>
            ) : (
              <span className="is-disabled" aria-hidden>
                <Icon name="sync" size={16} />
              </span>
            )}
            <button
              type="button"
              className="is-danger"
              onClick={onDisconnect}
              aria-label={t(locale, "disconnect")}
              title={t(locale, "disconnect")}
            >
              <Icon name="off" size={16} />
            </button>
          </div>
        ) : (
          <button type="button" className="btn sm" onClick={onConnect}>
            {t(locale, "connect")}
          </button>
        )}
      </div>
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
