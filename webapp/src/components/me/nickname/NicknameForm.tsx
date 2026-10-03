import { useState } from "react";
import type { Handle } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { BackHead } from "../../shared/lib";

const VALID = /^[A-Za-z0-9]{3,20}$/;

/** Choose or change the nickname (#157). `first` is the screen a person sees
 * once, on their first visit: it asks them to keep the nickname they were given
 * or to pick another, and has no way back. Otherwise it is a Settings pane. */
export function NicknameForm({
  locale,
  handle,
  first,
  onBack,
  onSubmit,
  onKeep,
}: {
  locale: Locale;
  handle: Handle;
  first?: boolean;
  onBack?: () => void;
  onSubmit: (value: string) => Promise<void>;
  onKeep?: () => Promise<void>;
}) {
  const [value, setValue] = useState(handle.name);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  // A change is locked for a day after the last real one; the first choice
  // is free (the server decides, this only explains it).
  const waitUntil = !first && handle.next_change_at ? new Date(handle.next_change_at) : null;
  const locked = waitUntil !== null && waitUntil.getTime() > Date.now();
  const unchanged = value === handle.name;
  const valid = VALID.test(value);

  const send = () => {
    if (busy || locked || !valid) return;
    setBusy(true);
    setNote(null);
    const action = unchanged && onKeep ? onKeep() : onSubmit(value);
    void action
      .catch((err: unknown) => {
        const text = String(err);
        setNote(
          text.includes("too_soon")
            ? t(locale, "nicknameTooSoon")
            : text.includes("invalid")
              ? t(locale, "nicknameInvalid")
              : text,
        );
      })
      .finally(() => setBusy(false));
  };

  return (
    <>
      {first ? (
        <header className="page-head">
          <h1>{t(locale, "nicknameTitle")}</h1>
        </header>
      ) : (
        <BackHead
          title={t(locale, "nickname")}
          backLabel={t(locale, "back")}
          onBack={onBack ?? (() => undefined)}
        />
      )}
      <form
        className="nick-form"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        {first && <p className="nick-intro">{t(locale, "nicknameIntro")}</p>}
        <input
          className="input wide"
          value={value}
          onChange={(e) => setValue(e.target.value.replace(/[^A-Za-z0-9]/g, "").slice(0, 20))}
          autoCapitalize="off"
          autoCorrect="off"
          spellCheck={false}
          enterKeyHint="done"
          maxLength={20}
          disabled={locked}
          aria-label={t(locale, "nickname")}
        />
        <p className="nick-hint">
          {locked && waitUntil
            ? `${t(locale, "nicknameNext")} ${waitUntil.toLocaleDateString(locale)}`
            : t(locale, "nicknameHint")}
        </p>
        {note && <p className="plat-note is-error">{note}</p>}
        <button type="submit" className="btn" disabled={!valid || busy || locked}>
          {unchanged && first ? t(locale, "nicknameKeep") : t(locale, "nicknameSave")}
        </button>
      </form>
    </>
  );
}
