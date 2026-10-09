import { useCallback, useEffect, useState } from "react";
import { ApiError, userApi } from "../../api";
import { t, type Locale } from "../../i18n";
import {
  Icon,
  TelegramLogin,
  Wordmark,
  getPasskey,
  passkeyCancelled,
  passkeysSupported,
  type TelegramUser,
} from "../../components/shared/lib";
import { EmailCodeForm, SendCancelled } from "../../components/me/logins/EmailCodeForm";
import { InviteCodeForm } from "../../components/me/logins/InviteCodeForm";
import "./Login.css";

type AuthConfig = { bot: string | null; botId: number | null; email: boolean; passkey: boolean };

/** A code from a shared link (`?invite=`): it rides along with the sign-in. */
function linkInvite(): string | null {
  return new URLSearchParams(window.location.search).get("invite");
}

/** A code went out: how long until another may (a key's answer never gets here). */
function sentOf(
  res: Awaited<ReturnType<typeof userApi.emailSignInStart>>,
): { resendAfter: number; skipCode?: boolean } {
  if (res.passkey) throw new Error("passkey");
  return { resendAfter: res.resend_after, skipCode: res.skip_code };
}

const TG_RESULT = "tgAuthResult=";

/** What Telegram's sign-in page sent back in the address (`#tgAuthResult=…`,
 * base64 of the signed user), once: the address is cleaned at once. */
function takeTelegramReturn(): TelegramUser | null {
  const hash = window.location.hash;
  const at = hash.indexOf(TG_RESULT);
  if (at < 0) return null;
  window.history.replaceState(null, "", window.location.pathname + window.location.search);
  try {
    const raw = hash.slice(at + TG_RESULT.length).replace(/-/g, "+").replace(/_/g, "/");
    const user = JSON.parse(atob(raw.padEnd(Math.ceil(raw.length / 4) * 4, "="))) as TelegramUser;
    return typeof user === "object" && user && "hash" in user ? user : null;
  } catch {
    return null;
  }
}

/** Telegram's own sign-in page in this tab, coming back here (owner,
 * 2026-10-07): the Login Widget's popup lost its answer on phones, where it
 * opens as another tab, and the sign-in screen came back. */
function telegramSignInUrl(botId: number): string {
  const back = window.location.origin + window.location.pathname + window.location.search;
  const query = new URLSearchParams({
    bot_id: String(botId),
    origin: window.location.origin,
    request_access: "write",
    return_to: back,
  });
  return `https://oauth.telegram.org/auth?${query.toString()}`;
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
  // The invite to sign up with: a shared link's, or the one typed when asked.
  const [invite, setInvite] = useState(linkInvite);
  // A new address waiting for its invite before its code is sent (owner,
  // 2026-10-07): the send goes on once a good one is typed.
  const [askInvite, setAskInvite] = useState<{
    address: string;
    done: (sent: { resendAfter: number; skipCode?: boolean }) => void;
    cancel: () => void;
  } | null>(null);
  // The address a code went to: while it is typed, only that is on the screen.
  const [codeFor, setCodeFor] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    userApi
      .authConfig()
      .then((res) => {
        if (!cancelled) {
          setConfig({
            bot: res.bot_username,
            botId: res.bot_id ?? null,
            email: Boolean(res.email),
            passkey: Boolean(res.passkey),
          });
        }
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

  // Back from Telegram's sign-in page: finish the sign-in it proved.
  useEffect(() => {
    const user = takeTelegramReturn();
    if (user) onTelegram(user);
    // Once, on arriving.
  }, []);

  // A key on this phone or computer signs in in place of a code (owner,
  // 2026-10-08): asked for when the address has one, or straight away.
  const canKey = Boolean(config?.passkey) && passkeysSupported();
  const signInWithKey = async (token: string, options: Record<string, unknown>) => {
    const credential = await getPasskey(options);
    await userApi.passkeySignIn(token, credential);
    onSignedIn();
  };
  const keyFailed = (err: unknown) => {
    if (passkeyCancelled(err)) return;
    setError(
      err instanceof ApiError && err.code === "unknown_key"
        ? t(locale, "passkeyUnknown")
        : t(locale, "passkeyFailed"),
    );
  };

  const email = config?.email ?? false;
  const bot = config?.bot ?? null;
  const botId = config?.botId ?? null;

  if (signup) {
    return (
      <div className="login">
        <Wordmark className="login-brand" />
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
      {/* The name on every step; on the first it is the title itself. */}
      {(askInvite || codeFor) && <Wordmark className="login-brand" />}
      {askInvite ? (
        <>
          <h1>{t(locale, "inviteTitle")}</h1>
          <InviteCodeForm
            locale={locale}
            initial={invite ?? ""}
            onSubmit={async (code) => {
              const res = await userApi.emailSignInStart(askInvite.address, locale, code);
              setInvite(code);
              setAskInvite(null);
              askInvite.done(sentOf(res));
            }}
            onRestart={() => {
              askInvite.cancel();
              setAskInvite(null);
            }}
          />
        </>
      ) : codeFor ? (
        <h1>{t(locale, "emailCheckTitle")}</h1>
      ) : (
        <>
          <h1 className="login-title">
            <Wordmark />
          </h1>
          <p className="login-tagline">{t(locale, "loginTagline")}</p>
          {config === null && <p className="login-text">{t(locale, "loginUnavailable")}</p>}
        </>
      )}
      {email && (
        // Kept while the invite is asked, so the send it waits on goes on.
        <div className="login-email" hidden={askInvite != null}>
        <EmailCodeForm
          locale={locale}
          submitLabel={t(locale, "loginButton")}
          sendLabel={t(locale, "loginButton")}
          onSend={async (address) => {
            setError(null);
            try {
              const res = await userApi.emailSignInStart(address, locale, invite, canKey || undefined);
              if (res.passkey) {
                try {
                  await signInWithKey(res.token, res.options);
                  throw new SendCancelled();
                } catch (err) {
                  if (err instanceof SendCancelled) throw err;
                  // The key not at hand, or refused: the code by email instead.
                  if (!passkeyCancelled(err)) keyFailed(err);
                  return sentOf(await userApi.emailSignInStart(address, locale, invite, false));
                }
              }
              return sentOf(res);
            } catch (err) {
              if (err instanceof SendCancelled) throw err;
              if (!(err instanceof ApiError && (err.code === "invite_required" || err.code === "invite_invalid"))) {
                throw err;
              }
              // Somebody new: the invite first, then the code goes out.
              return await new Promise((done, fail) =>
                setAskInvite({ address, done, cancel: () => fail(new SendCancelled()) }),
              );
            }
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
        </div>
      )}
      {email && bot && !codeFor && !askInvite && <p className="login-or">{t(locale, "loginOr")}</p>}
      {askInvite ? null : botId != null && !codeFor ? (
        <button
          type="button"
          className="btn is-wide login-telegram"
          onClick={() => window.location.assign(telegramSignInUrl(botId))}
        >
          <Icon name="telegram" size={20} />
          <span>{t(locale, "loginWithTelegram")}</span>
        </button>
      ) : (
        bot &&
        !codeFor && (
          <div className="login-widget">
            <TelegramLogin bot={bot} onAuth={onTelegram} />
          </div>
        )
      )}
      {error && <p className="login-error">{error}</p>}
    </div>
  );
}
