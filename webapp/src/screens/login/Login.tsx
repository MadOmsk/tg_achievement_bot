import { useCallback, useEffect, useState } from "react";
import { userApi } from "../../api";
import { t, type Locale } from "../../i18n";
import { TelegramLogin, type TelegramUser } from "../../components/shared/lib";
import { EmailCodeForm } from "../../components/me/logins/EmailCodeForm";
import "./Login.css";

type AuthConfig = { bot: string | null; email: boolean };

/** Sign-in for the Mini App opened in a plain browser: Telegram's Login Widget
 * (#157) and, when a mail server is set up, a code sent by email (#162). Inside
 * Telegram this screen never shows. */
export function Login({ locale, onSignedIn }: { locale: Locale; onSignedIn: () => void }) {
  const [config, setConfig] = useState<AuthConfig | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    userApi
      .authConfig()
      .then((res) => {
        if (!cancelled) setConfig({ bot: res.bot_username, email: Boolean(res.email) });
      })
      .catch(() => {
        if (!cancelled) setConfig(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const onTelegram = useCallback(
    (user: TelegramUser) => {
      setError(null);
      userApi
        .loginTelegram(user)
        .then(onSignedIn)
        .catch((err: unknown) => setError(String(err)));
    },
    [onSignedIn],
  );

  const email = config?.email ?? false;
  const bot = config?.bot ?? null;

  return (
    <div className="login">
      <img className="login-mark" src="/logo.svg" alt="" width={96} height={96} />
      <h1>{t(locale, "loginTitle")}</h1>
      <p className="login-text">{t(locale, email ? "loginTextBoth" : "loginText")}</p>
      {config === null && <p className="login-text">{t(locale, "loginUnavailable")}</p>}
      {email && (
        <EmailCodeForm
          locale={locale}
          submitLabel={t(locale, "loginButton")}
          onSend={async (address) => (await userApi.emailSignInStart(address, locale)).resend_after}
          onVerify={async (address, code) => {
            await userApi.emailSignInVerify(address, code, locale);
            onSignedIn();
          }}
        />
      )}
      {email && bot && <p className="login-or">{t(locale, "loginOr")}</p>}
      {bot && (
        <div className="login-widget">
          <TelegramLogin bot={bot} onAuth={onTelegram} />
        </div>
      )}
      {error && <p className="login-error">{error}</p>}
    </div>
  );
}
