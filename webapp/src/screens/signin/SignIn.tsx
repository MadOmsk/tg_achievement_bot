import { useCallback, useEffect, useState } from "react";
import { ApiError, userApi } from "../../api";
import { getPasskey, passkeysSupported } from "../../core/passkey";
import { TelegramLogin, type TelegramUser } from "../../core/telegram-login";
import { t, type Locale } from "../../i18n";
import { CodeEntry, errorText } from "../../parts/CodeEntry";
import { Button, Field, Spinner } from "../../ui/Controls";
import { Wordmark } from "./Wordmark";
import "./SignIn.css";

type Config = { bot: string | null; botId: number | null; email: boolean; passkey: boolean };

type Step =
  | { name: "start" }
  | { name: "code"; email: string; resendAfter: number }
  /** A proved sign-in of somebody new, or a new address, waiting for a code. */
  | { name: "invite"; then: (invite: string) => Promise<void> };

const TG_RESULT = "tgAuthResult=";

/** What Telegram's sign-in page sent back in the address, once: the address
 * is cleaned at once. */
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

/** Telegram's own sign-in page in this same tab, coming back here: the Login
 * Widget's popup lost its answer on phones. */
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

function linkInvite(): string | null {
  return new URLSearchParams(window.location.search).get("invite");
}

function signupToken(err: unknown): string | null {
  return err instanceof ApiError &&
    (err.code === "invite_required" || err.code === "invite_invalid") &&
    typeof err.body.signup === "string"
    ? err.body.signup
    : null;
}

const needsInvite = (err: unknown) =>
  err instanceof ApiError && (err.code === "invite_required" || err.code === "invite_invalid");

/** The sign-in a browser or the installed app shows; inside Telegram the
 * person is already known and this never appears. */
export function SignIn({ locale, onSignedIn }: { locale: Locale; onSignedIn: () => void }) {
  const tr = (key: Parameters<typeof t>[1]) => t(locale, key);
  const [config, setConfig] = useState<Config | null | undefined>(undefined);
  const [step, setStep] = useState<Step>({ name: "start" });
  const [email, setEmail] = useState("");
  const [invite, setInvite] = useState(linkInvite);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    userApi
      .authConfig()
      .then((c) => setConfig({ bot: c.bot_username, botId: c.bot_id ?? null, email: Boolean(c.email), passkey: Boolean(c.passkey) }))
      .catch(() => setConfig(null));
  }, []);

  const afterInvite = useCallback(
    (err: unknown, retry: (code: string) => Promise<void>) => {
      const signup = signupToken(err);
      if (signup) {
        const then = (code: string) => userApi.signUp(signup, code).then(onSignedIn);
        if (invite) {
          void then(invite).catch(() => setStep({ name: "invite", then }));
          return true;
        }
        setStep({ name: "invite", then });
        return true;
      }
      if (needsInvite(err)) {
        setStep({ name: "invite", then: retry });
        return true;
      }
      return false;
    },
    [invite, onSignedIn],
  );

  const onTelegram = useCallback(
    (user: TelegramUser) => {
      setError(null);
      userApi
        .loginTelegram(user, invite)
        .then(onSignedIn)
        .catch((err: unknown) => {
          if (!afterInvite(err, async (code) => {
            setInvite(code);
            await userApi.loginTelegram(user, code);
            onSignedIn();
          })) setError(errorText(err, locale));
        });
    },
    [invite, onSignedIn, afterInvite, locale],
  );

  useEffect(() => {
    const user = takeTelegramReturn();
    if (user) onTelegram(user);
    // Once, for the address the page came back with.
  }, []);

  /** Send the code — or, for an address with a passkey, ask the phone for it. */
  const start = async (address: string, withInvite: string | null, passkey: boolean): Promise<void> => {
    const res = await userApi.emailSignInStart(address, locale, withInvite, passkey ? true : undefined);
    if (res.passkey) {
      try {
        const credential = await getPasskey(res.options);
        await userApi.passkeySignIn(res.token, credential);
        onSignedIn();
        return;
      } catch {
        // Refused, not at hand or failed: the code goes out instead, no word.
        return start(address, withInvite, false);
      }
    }
    if (res.skip_code) {
      await userApi.emailSignInVerify(address, "000000", locale, withInvite);
      onSignedIn();
      return;
    }
    setStep({ name: "code", email: address, resendAfter: res.resend_after });
  };

  const submitEmail = async () => {
    const address = email.trim();
    if (!address) return;
    setBusy(true);
    setError(null);
    try {
      await start(address, invite, Boolean(config?.passkey && passkeysSupported()));
    } catch (err) {
      if (
        !afterInvite(err, async (code) => {
          setInvite(code);
          await start(address, code, false);
        })
      )
        setError(errorText(err, locale));
    } finally {
      setBusy(false);
    }
  };

  if (config === undefined) {
    return (
      <div className="signin signin-center">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="signin">
      <Wordmark className="signin-word" />
      <p className="signin-tag">{tr("loginTagline")}</p>

      {step.name === "start" && (
        <div className="signin-card">
          {config?.email && (
            <form
              className="signin-form"
              onSubmit={(e) => {
                e.preventDefault();
                void submitEmail();
              }}
            >
              <Field
                type="email"
                inputMode="email"
                autoComplete="email webauthn"
                icon="mail"
                placeholder={tr("emailPlaceholder")}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <Button wide variant="filled" type="submit" busy={busy}>
                {tr("loginButton")}
              </Button>
            </form>
          )}
          {config?.email && (config.botId || config.bot) && <p className="signin-or">{tr("loginOr")}</p>}
          {config?.botId ? (
            <Button wide variant={config.email ? "tonal" : "filled"} onClick={() => (window.location.href = telegramSignInUrl(config.botId!))}>
              {tr("loginWithTelegram")}
            </Button>
          ) : config?.bot ? (
            <TelegramLogin bot={config.bot} onAuth={onTelegram} />
          ) : null}
          {!config?.email && !config?.bot && <p className="t-body">{tr("loginUnavailable")}</p>}
        </div>
      )}

      {step.name === "code" && (
        <div className="signin-card">
          <p className="t-title">{tr("emailCheckTitle")}</p>
          <CodeEntry
            locale={locale}
            email={step.email}
            resendAfter={step.resendAfter}
            onVerify={async (code) => {
              try {
                await userApi.emailSignInVerify(step.email, code, locale, invite);
                onSignedIn();
              } catch (err) {
                if (afterInvite(err, async (c) => {
                  setInvite(c);
                  await userApi.emailSignInVerify(step.email, code, locale, c);
                  onSignedIn();
                })) return;
                throw err;
              }
            }}
            onResend={async () => {
              const res = await userApi.emailSignInStart(step.email, locale, invite, false);
              return "resend_after" in res && res.resend_after ? res.resend_after : 60;
            }}
            onChangeAddress={() => setStep({ name: "start" })}
          />
        </div>
      )}

      {step.name === "invite" && <InviteStep locale={locale} initial={invite} then={step.then} onBack={() => setStep({ name: "start" })} />}

      {error && <p className="form-error signin-error">{error}</p>}
    </div>
  );
}

function InviteStep({
  locale,
  initial,
  then,
  onBack,
}: {
  locale: Locale;
  initial: string | null;
  then: (invite: string) => Promise<void>;
  onBack: () => void;
}) {
  const [code, setCode] = useState(initial ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      className="signin-card"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        try {
          await then(code.trim().toUpperCase());
        } catch (err) {
          setError(errorText(err, locale));
        } finally {
          setBusy(false);
        }
      }}
    >
      <p className="t-title">{t(locale, "inviteTitle")}</p>
      <p className="t-body">{t(locale, "inviteIntro")}</p>
      <Field
        icon="gift"
        placeholder="XXXX-XXXX-XXXX-XXXX"
        autoCapitalize="characters"
        value={code}
        error={error}
        onChange={(e) => setCode(e.target.value)}
      />
      <Button wide type="submit" busy={busy} disabled={code.trim().length < 8}>
        {t(locale, "inviteContinue")}
      </Button>
      <Button variant="text" onClick={onBack}>
        {t(locale, "back")}
      </Button>
    </form>
  );
}
