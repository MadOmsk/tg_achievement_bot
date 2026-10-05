import { useState } from "react";
import { userApi } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { EmailCodeForm } from "./EmailCodeForm";
import "../../../screens/login/Login.css";

/** Asked once, on opening the app, of somebody with no email (owner,
 * 2026-10-05): it is the main way in — without Telegram, on any device. Added
 * here or put off; Settings → Профиль → Вход adds one any time later. */
export function AddEmailScreen({
  locale,
  data,
  onDone,
}: {
  locale: Locale;
  data: string;
  /** Added or put off: the app goes on. */
  onDone: () => Promise<void> | void;
}) {
  const [codeFor, setCodeFor] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const later = async () => {
    setBusy(true);
    try {
      await userApi.emailLater(data);
    } finally {
      await onDone();
    }
  };

  return (
    <div className="login">
      <img className="login-mark" src={`${import.meta.env.BASE_URL}logo.svg`} alt="" width={96} height={96} />
      <h1>{t(locale, codeFor ? "emailCheckTitle" : "addEmailTitle")}</h1>
      {!codeFor && <p className="login-text">{t(locale, "addEmailText")}</p>}
      <EmailCodeForm
        locale={locale}
        submitLabel={t(locale, "emailConfirm")}
        onStep={setCodeFor}
        onSend={async (email) => {
          const res = await userApi.emailLinkStart(data, email);
          return { resendAfter: res.resend_after, skipCode: res.skip_code };
        }}
        onVerify={async (email, code) => {
          await userApi.emailLinkVerify(data, email, code);
          await onDone();
        }}
      />
      {!codeFor && (
        <button type="button" className="see-all add-email-later" disabled={busy} onClick={() => void later()}>
          {t(locale, "addEmailLater")}
        </button>
      )}
    </div>
  );
}
