import { useState } from "react";
import { ApiError } from "../../../api";
import { t, type Locale } from "../../../i18n";
import "./Logins.css";

// The code's own alphabet (bot/services/invites.py): no 0/O, 1/I/L look-alikes.
const ALPHABET = /[ABCDEFGHJKMNPQRSTUVWXYZ2-9]/g;
const LENGTH = 16;

/** What was typed or pasted, as the code reads: upper case, dashes by fours. */
export function formatInvite(raw: string): string {
  const chars = (raw.toUpperCase().match(ALPHABET) ?? []).join("").slice(0, LENGTH);
  return chars.replace(/(.{4})(?=.)/g, "$1-");
}

/** The step after a proved sign-in of somebody new: the code a member gave
 * (owner, 2026-10-05). */
export function InviteCodeForm({
  locale,
  initial = "",
  onSubmit,
  onRestart,
}: {
  locale: Locale;
  initial?: string;
  onSubmit: (code: string) => Promise<void>;
  /** Back to the start, when the proved sign-in has expired. */
  onRestart: () => void;
}) {
  const [code, setCode] = useState(() => formatInvite(initial));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expired, setExpired] = useState(false);
  const full = code.replace(/-/g, "").length === LENGTH;

  const submit = async () => {
    if (!full) return;
    setBusy(true);
    setError(null);
    try {
      await onSubmit(code);
    } catch (err) {
      if (err instanceof ApiError && err.code === "signup_expired") {
        setExpired(true);
        setError(t(locale, "inviteExpired"));
      } else if (err instanceof ApiError && err.code === "invite_invalid") {
        setError(t(locale, "inviteInvalid"));
      } else {
        setError(`${t(locale, "error")}: ${String(err)}`);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      className="email-form form-stack"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <p className="field-note invite-intro">{t(locale, "inviteIntro")}</p>
      <label className={error ? "field is-invite is-error" : "field is-invite"}>
        <input
          autoFocus
          autoCapitalize="characters"
          autoCorrect="off"
          autoComplete="off"
          spellCheck={false}
          placeholder="XXXX-XXXX-XXXX-XXXX"
          value={code}
          onChange={(event) => setCode(formatInvite(event.target.value))}
          aria-label={t(locale, "inviteCode")}
        />
      </label>
      {error && <p className="field-note is-error">{error}</p>}
      {expired ? (
        <button type="button" className="btn is-wide" onClick={onRestart}>
          {t(locale, "inviteRestart")}
        </button>
      ) : (
        <button type="submit" className="btn is-wide" disabled={busy || !full}>
          {t(locale, "inviteContinue")}
        </button>
      )}
      {!expired && (
        <div className="email-links is-center">
          <button type="button" className="see-all" onClick={onRestart}>
            {t(locale, "back")}
          </button>
        </div>
      )}
    </form>
  );
}
