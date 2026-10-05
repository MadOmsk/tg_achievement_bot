import { useEffect, useRef, useState } from "react";
import { ApiError } from "../../../api";
import { t, type Locale, type TranslationKey } from "../../../i18n";
import "./Logins.css";

const CODE_LENGTH = 6;

/** What a refusal says, by the `error` the server answered with (#162). */
const ERRORS: Record<string, TranslationKey> = {
  invalid: "emailInvalid",
  too_soon: "emailTooSoon",
  unavailable: "emailUnavailable",
  send_failed: "emailSendFailed",
  wrong_code: "emailWrongCode",
  expired: "emailExpired",
  taken: "emailTaken",
};

function describe(err: unknown, locale: Locale): string {
  if (err instanceof ApiError) {
    const key = ERRORS[err.code];
    if (key === "emailWrongCode" && typeof err.body.attempts_left === "number") {
      return `${t(locale, key)} ${t(locale, "emailAttemptsLeft")} ${err.body.attempts_left}`;
    }
    if (key) return t(locale, key);
  }
  return `${t(locale, "error")}: ${String(err)}`;
}

function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

/** An address, then the six-digit code sent to it (#162). The same two steps
 * sign a person in and add an address in Settings; only what the two calls do
 * differs. */
export function EmailCodeForm({
  locale,
  initialEmail = "",
  submitLabel,
  onSend,
  onVerify,
}: {
  locale: Locale;
  initialEmail?: string;
  submitLabel: string;
  /** Sends a code; resolves with how many seconds until another may be sent,
   * and whether no code is needed at all (the dev server's no-code mode). */
  onSend: (email: string) => Promise<{ resendAfter: number; skipCode?: boolean }>;
  onVerify: (email: string, code: string) => Promise<void>;
}) {
  const [email, setEmail] = useState(initialEmail);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [wait, setWait] = useState(0);
  const codeRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (wait <= 0) return;
    const timer = window.setTimeout(() => setWait((w) => w - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [wait]);

  useEffect(() => {
    if (sentTo) codeRef.current?.focus();
  }, [sentTo]);

  const send = async (address: string) => {
    setBusy(true);
    setError(null);
    try {
      const sent = await onSend(address);
      if (sent.skipCode) {
        await onVerify(address, "");
        return;
      }
      setWait(sent.resendAfter);
      setSentTo(address);
      setCode("");
    } catch (err) {
      if (err instanceof ApiError && err.code === "too_soon") {
        const after = Number(err.body.retry_after) || 60;
        setWait(after);
        // A code already went to this address: let it be typed.
        if (sentTo === address) setError(null);
        else setError(t(locale, "emailTooSoon"));
      } else {
        setError(describe(err, locale));
      }
    } finally {
      setBusy(false);
    }
  };

  const verify = async (value: string) => {
    if (!sentTo || value.length !== CODE_LENGTH) return;
    setBusy(true);
    setError(null);
    try {
      await onVerify(sentTo, value);
    } catch (err) {
      setError(describe(err, locale));
      setCode("");
      if (err instanceof ApiError && err.code === "expired") setWait(0);
    } finally {
      setBusy(false);
    }
  };

  if (!sentTo) {
    return (
      <form
        className="email-form"
        onSubmit={(event) => {
          event.preventDefault();
          void send(email.trim());
        }}
      >
        <label className="email-field glass">
          <input
            type="email"
            inputMode="email"
            autoComplete="email"
            placeholder={t(locale, "emailPlaceholder")}
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        {error && <p className="email-note is-error">{error}</p>}
        <button type="submit" className="btn email-submit" disabled={busy || !email.trim()}>
          {t(locale, "emailGetCode")}
        </button>
      </form>
    );
  }

  return (
    <form
      className="email-form"
      onSubmit={(event) => {
        event.preventDefault();
        void verify(code);
      }}
    >
      <p className="email-note">
        {t(locale, "emailCodeSent")} <b>{sentTo}</b>
      </p>
      <label className="email-field glass is-code">
        <input
          ref={codeRef}
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={CODE_LENGTH}
          placeholder="••••••"
          value={code}
          onChange={(event) => {
            const value = event.target.value.replace(/\D/g, "").slice(0, CODE_LENGTH);
            setCode(value);
            // The last digit is the press of the button.
            if (value.length === CODE_LENGTH) void verify(value);
          }}
        />
      </label>
      {error && <p className="email-note is-error">{error}</p>}
      <button type="submit" className="btn email-submit" disabled={busy || code.length !== CODE_LENGTH}>
        {submitLabel}
      </button>
      <div className="email-links">
        <button
          type="button"
          className="see-all"
          onClick={() => {
            setSentTo(null);
            setError(null);
          }}
        >
          {t(locale, "emailChange")}
        </button>
        <button type="button" className="see-all" disabled={busy || wait > 0} onClick={() => void send(sentTo)}>
          {wait > 0 ? `${t(locale, "emailResendIn")} ${clock(wait)}` : t(locale, "emailResend")}
        </button>
      </div>
    </form>
  );
}
