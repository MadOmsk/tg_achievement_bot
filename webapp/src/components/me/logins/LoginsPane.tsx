import { useCallback, useEffect, useState } from "react";
import { userApi, type LoginsResponse } from "../../../api";
import { t, type Locale, type TranslationKey } from "../../../i18n";
import { BackHead, Group, InfoRow, NavRow, SettingsSkel, TelegramLogin, type TelegramUser } from "../../shared/lib";
import { EmailCodeForm } from "./EmailCodeForm";
import "./Logins.css";

/** Settings → «Вход» (#162): the ways this person signs in. An address is added
 * or changed by a code sent to it, and removed only while Telegram is left;
 * Telegram is added through its Login Widget, which works only in a browser —
 * inside Telegram a person always has it already. */
export function LoginsPane({
  locale,
  data,
  onBack,
  onFlash,
  onChanged,
}: {
  locale: Locale;
  data: string;
  onBack: () => void;
  onFlash: (message: string) => void;
  /** The logins changed in a way the rest of the app shows (Telegram added). */
  onChanged: () => void;
}) {
  // Why Telegram cannot be taken away right now, worded (#162).
  const BLOCKED: Record<string, TranslationKey> = {
    last_login: "telegramKeepLast",
    in_telegram: "telegramKeepInside",
    admin: "telegramKeepAdmin",
  };
  const [logins, setLogins] = useState<LoginsResponse | null>(null);
  const [editing, setEditing] = useState(false);
  const [bot, setBot] = useState<string | null>(null);
  const inTelegram = Boolean(window.Telegram?.WebApp?.initData);
  const fail = useCallback((err: unknown) => onFlash(`${t(locale, "error")}: ${String(err)}`), [locale, onFlash]);

  useEffect(() => {
    userApi.logins(data).then(setLogins).catch(fail);
    if (!inTelegram) {
      userApi
        .authConfig()
        .then((res) => setBot(res.bot_username))
        .catch(() => setBot(null));
    }
  }, [data, fail, inTelegram]);

  const linkTelegram = useCallback(
    (user: TelegramUser) => {
      userApi
        .linkTelegram(data, user)
        .then((res) => {
          setLogins(res);
          onChanged();
        })
        .catch((err: unknown) =>
          onFlash(String(err).includes("taken") ? t(locale, "telegramTaken") : `${t(locale, "error")}: ${String(err)}`),
        );
    },
    [data, locale, onChanged, onFlash],
  );

  if (logins === null) {
    return (
      <>
        <BackHead title={t(locale, "logins")} backLabel={t(locale, "back")} onBack={onBack} />
        <SettingsSkel groups={[1, 1]} />
      </>
    );
  }

  const emailForm = (
    <div className="logins-form">
      <EmailCodeForm
        locale={locale}
        initialEmail={logins.email ?? ""}
        submitLabel={t(locale, "emailConfirm")}
        onSend={async (email) => (await userApi.emailLinkStart(data, email)).resend_after}
        onVerify={async (email, code) => {
          setLogins(await userApi.emailLinkVerify(data, email, code));
          setEditing(false);
          onFlash(t(locale, "emailSaved"));
        }}
      />
    </div>
  );

  return (
    <>
      <BackHead title={t(locale, "logins")} backLabel={t(locale, "back")} onBack={onBack} />

      <Group title={t(locale, "emailTitle")} hint={t(locale, "emailHint")}>
        {logins.email && !editing ? (
          <InfoRow label={logins.email}>
            {logins.email_available && (
              <button type="button" className="btn sm is-quiet" onClick={() => setEditing(true)}>
                {t(locale, "emailChangeShort")}
              </button>
            )}
          </InfoRow>
        ) : logins.email_available ? (
          emailForm
        ) : (
          <InfoRow label={t(locale, "emailUnavailable")} />
        )}
      </Group>

      <Group
        title="Telegram"
        hint={
          !logins.telegram.linked
            ? t(locale, "telegramWhy")
            : logins.telegram.blocked
              ? t(locale, BLOCKED[logins.telegram.blocked])
              : undefined
        }
      >
        {logins.telegram.linked ? (
          <InfoRow label={t(locale, "telegramLinked")} value={logins.telegram.username ?? undefined} />
        ) : bot ? (
          <div className="logins-widget">
            <TelegramLogin bot={bot} onAuth={linkTelegram} />
          </div>
        ) : (
          <InfoRow label={t(locale, "loginUnavailable")} />
        )}
      </Group>

      {/* Email is the main way in (owner, 2026-10-05): changed, never removed.
          Telegram may go while an address is left. */}
      {logins.telegram.removable && (
        <Group>
          <NavRow
            danger
            label={t(locale, "telegramRemove")}
            onClick={() => {
              if (!window.confirm(t(locale, "telegramRemoveConfirm"))) return;
              userApi
                .removeTelegram(data)
                .then((res) => {
                  setLogins(res);
                  onChanged();
                })
                .catch(fail);
            }}
          />
        </Group>
      )}
    </>
  );
}
