import { useCallback, useEffect, useState } from "react";
import { ApiError, userApi } from "../../api";
import { t, type Locale } from "../../i18n";
import { TelegramLogin, type TelegramUser } from "../../components/shared/lib";
import { EmailCodeForm } from "../../components/me/logins/EmailCodeForm";
import { InviteCodeForm } from "../../components/me/logins/InviteCodeForm";
import "./Login.css";

type AuthConfig = { bot: string | null; email: boolean };

/** A code from a shared link (`?invite=`): it rides along with the sign-in. */
function linkInvite(): string | null {
  return new URLSearchParams(window.location.search).get("invite");
}

/** The sign-in proved somebody new who has no usable code: the token that waits
 * for one, or rethrow anything else. */
function signupOf(err: unknown): string {
  if (
    err instanceof ApiError &&
    (err.code === "invite_required" || err.code === "invite_invalid") &&
    typeof err.body.signup === "string"
  ) {
    return err.body.signup;
  }
  throw err;
}

/** Sign-in for the Mini App opened in a plain browser: Telegram's Login Widget
 * (#157) and, when a mail server is set up, a code sent by email (#162). Inside
 * Telegram this screen never shows. Somebody new needs an invite (owner,
 * 2026-10-05): asked for once the address or the Telegram account is proved,
 * unless a shared link already carried it. */
export function Login({ locale, onSignedIn }: { locale: Locale; onSignedIn: () => void }) {
  const [config, setConfig] = useState<AuthConfig | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  // A proved sign-in of somebody new, waiting for an invite.
  const [signup, setSignup] = useState<string | null>(null);
  const [invite] = useState(linkInvite);
  // The address a code went to: while it is typed, only that is on the screen.
  const [codeFor, setCodeFor] = useState<string | null>(null);

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
        .loginTelegram(user, invite)
        .then(onSignedIn)
        .catch((err: unknown) => {
          try {
            setSignup(signupOf(err));
          } catch {
            setError(String(err));
          }
        });
    },
    [onSignedIn, invite],
  );

  const email = config?.email ?? false;
  const bot = config?.bot ?? null;

  if (signup) {
    return (
      <div className="login">
        <img className="login-mark" src="/logo.svg" alt="" width={96} height={96} />
        <h1>{t(locale, "inviteTitle")}</h1>
        <InviteCodeForm
          locale={locale}
          initial={invite ?? ""}
          onSubmit={async (code) => {
            await userApi.signUp(signup, code);
            onSignedIn();
          }}
          onRestart={() => setSignup(null)}
        />
      </div>
    );
  }

  return (
    <div className="login">
      <img className="login-mark" src="/logo.svg" alt="" width={96} height={96} />
      {codeFor ? (
        <h1>{t(locale, "emailCheckTitle")}</h1>
      ) : (
        <>
          <h1>{t(locale, "appName")}</h1>
          <p className="login-tagline">{t(locale, "loginTagline")}</p>
          <p className="login-text">{t(locale, email ? "loginTextBoth" : "loginText")}</p>
          {config === null && <p className="login-text">{t(locale, "loginUnavailable")}</p>}
        </>
      )}
      {email && (
        <EmailCodeForm
          locale={locale}
          submitLabel={t(locale, "loginButton")}
          onSend={async (address) => {
            const res = await userApi.emailSignInStart(address, locale);
            return { resendAfter: res.resend_after, skipCode: res.skip_code };
          }}
          onStep={setCodeFor}
          onVerify={async (address, code) => {
            try {
              await userApi.emailSignInVerify(address, code, locale, invite);
            } catch (err) {
              setSignup(signupOf(err));
              return;
            }
            onSignedIn();
          }}
        />
      )}
      {email && bot && !codeFor && <p className="login-or">{t(locale, "loginOr")}</p>}
      {bot && !codeFor && (
        <div className="login-widget">
          <TelegramLogin bot={bot} onAuth={onTelegram} />
        </div>
      )}
      {error && <p className="login-error">{error}</p>}
    </div>
  );
}
