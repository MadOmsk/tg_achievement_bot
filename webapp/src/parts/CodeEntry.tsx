import { useEffect, useRef, useState } from "react";
import { ApiError } from "../api";
import { t, type Locale, type TranslationKey } from "../i18n";
import { Button } from "../ui/Controls";

const ERRORS: Record<string, TranslationKey> = {
  invalid: "emailInvalid",
  too_soon: "emailTooSoon",
  unavailable: "emailUnavailable",
  send_failed: "emailSendFailed",
  wrong_code: "emailWrongCode",
  expired: "emailExpired",
  taken: "emailTaken",
  invite_invalid: "inviteInvalid",
  invite_required: "inviteInvalid",
  signup_expired: "inviteExpired",
  already: "emailSaved",
  last_login: "telegramKeepLast",
  admin: "telegramKeepAdmin",
  in_telegram: "telegramKeepInside",
  not_linked: "telegramNotLinked",
};

/** A refusal in the app's words; anything unknown says so plainly. */
export function errorText(err: unknown, locale: Locale): string {
  if (err instanceof ApiError) {
    const key = ERRORS[err.code];
    if (key) {
      const left = err.body.attempts_left;
      return typeof left === "number" && err.code === "wrong_code"
        ? `${t(locale, key)} ${t(locale, "emailAttemptsLeft")} ${left}`
        : t(locale, key);
    }
  }
  return t(locale, "somethingWrong");
}

/** The six digits from the letter: sent as soon as the sixth is typed, a new
 * code a minute later (counted down). */
export function CodeEntry({
  locale,
  email,
  resendAfter,
  onVerify,
  onResend,
  onChangeAddress,
}: {
  locale: Locale;
  email: string;
  resendAfter: number;
  onVerify: (code: string) => Promise<void>;
  onResend: () => Promise<number>;
  onChangeAddress: () => void;
}) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [wait, setWait] = useState(resendAfter);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    input.current?.focus();
  }, []);

  useEffect(() => {
    if (wait <= 0) return;
    const id = window.setTimeout(() => setWait((n) => n - 1), 1000);
    return () => window.clearTimeout(id);
  }, [wait]);

  const verify = async (value: string) => {
    setBusy(true);
    setError(null);
    try {
      await onVerify(value);
    } catch (err) {
      setError(errorText(err, locale));
      setCode("");
      input.current?.focus();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="code-entry">
      <p className="t-body">
        {t(locale, "emailCodeSent")} <b>{email}</b>
      </p>
      <label className="code-boxes">
        <span className="sr-only">{t(locale, "emailCheckTitle")}</span>
        <input
          ref={input}
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          value={code}
          disabled={busy}
          onChange={(e) => {
            const digits = e.target.value.replace(/\D/g, "").slice(0, 6);
            setCode(digits);
            if (digits.length === 6) void verify(digits);
          }}
        />
        {Array.from({ length: 6 }, (_, i) => (
          <span key={i} className={`code-box${i === code.length ? " code-box-at" : ""}`} aria-hidden="true">
            {code[i] ?? ""}
          </span>
        ))}
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="code-actions">
        <Button variant="text" onClick={onChangeAddress}>
          {t(locale, "emailChange")}
        </Button>
        <Button
          variant="tonal"
          disabled={wait > 0}
          onClick={async () => {
            setError(null);
            try {
              setWait(await onResend());
            } catch (err) {
              setError(errorText(err, locale));
            }
          }}
        >
          {wait > 0 ? `${t(locale, "emailResendIn")} ${wait} ${t(locale, "seconds")}` : t(locale, "emailResend")}
        </Button>
      </div>
    </div>
  );
}
