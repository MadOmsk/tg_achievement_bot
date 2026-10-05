import { useCallback, useEffect, useState } from "react";
import { ApiError, userApi, type LoginsResponse, type MergePreview } from "../../../api";
import { t, type Locale, type TranslationKey } from "../../../i18n";
import { BackHead, Group, InfoRow, NavRow, SettingsSkel, TelegramLogin, type TelegramUser } from "../../shared/lib";
import { EmailCodeForm } from "./EmailCodeForm";
import { MergeSheet } from "./MergeSheet";
import "./Logins.css";

// Why Telegram cannot be taken away right now, worded (#162).
const BLOCKED: Record<string, TranslationKey> = {
  last_login: "telegramKeepLast",
  in_telegram: "telegramKeepInside",
  admin: "telegramKeepAdmin",
};

/** A refusal that came with a merge offer: the login proved is somebody else's. */
function mergeOffer(err: unknown): MergePreview | null {
  return err instanceof ApiError && err.code === "taken" && err.body.merge
    ? (err.body.merge as MergePreview)
    : null;
}

/** Settings → «Вход» (#162): the ways this person signs in. The address is the
 * main way in: added or changed by a code, never removed. Telegram is added
 * through its Login Widget or a link that opens the bot, and taken away while an
 * address is left. A login that turns out to be another account of the same
 * person opens the merge (`MergeSheet`). */
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
  /** The logins changed in a way the rest of the app shows (Telegram added, a merge). */
  onChanged: () => void;
}) {
  const [logins, setLogins] = useState<LoginsResponse | null>(null);
  const [editing, setEditing] = useState(false);
  const [bot, setBot] = useState<string | null>(null);
  const [merge, setMerge] = useState<MergePreview | null>(null);
  const inTelegram = Boolean(window.Telegram?.WebApp?.initData);
  const fail = useCallback((err: unknown) => onFlash(`${t(locale, "error")}: ${String(err)}`), [locale, onFlash]);

  const load = useCallback(() => {
    userApi
      .logins(data)
      .then((res) => {
        setLogins(res);
        if (res.merge_pending) {
          void userApi.pendingMerge(data).then((pending) => setMerge(pending.merge));
        }
      })
      .catch(fail);
  }, [data, fail]);

  useEffect(() => {
    load();
    if (!inTelegram) {
      userApi
        .authConfig()
        .then((res) => setBot(res.bot_username))
        .catch(() => setBot(null));
    }
    // Back from the bot (the t.me link): see what it did.
    const onVisible = () => {
      if (document.visibilityState === "visible") load();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [load, inTelegram]);

  const linkTelegram = useCallback(
    (user: TelegramUser) => {
      userApi
        .linkTelegram(data, user)
        .then((res) => {
          setLogins(res);
          onChanged();
        })
        .catch((err: unknown) => {
          const offer = mergeOffer(err);
          if (offer) setMerge(offer);
          else fail(err);
        });
    },
    [data, fail, onChanged],
  );

  const openBot = () => {
    userApi
      .telegramLinkUrl(data)
      .then((res) => window.open(res.url, "_blank", "noopener"))
      .catch(fail);
  };

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
        placeholder={logins.email ?? undefined}
        submitLabel={t(locale, "emailConfirm")}
        onSend={async (email) => {
          const res = await userApi.emailLinkStart(data, email);
          return { resendAfter: res.resend_after, skipCode: res.skip_code };
        }}
        onVerify={async (email, code) => {
          try {
            setLogins(await userApi.emailLinkVerify(data, email, code));
          } catch (err) {
            const offer = mergeOffer(err);
            if (!offer) throw err;
            setMerge(offer);
            return;
          }
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
        ) : (
          <>
            {bot && (
              <div className="logins-widget">
                <TelegramLogin bot={bot} onAuth={linkTelegram} />
              </div>
            )}
            {/* The widget renders only on a host BotFather knows, and on a phone
                the bot itself is nearer: the link opens it with a one-time token. */}
            <div className="logins-link">
              <button type="button" className="see-all" onClick={openBot}>
                {t(locale, "telegramViaBot")}
              </button>
            </div>
          </>
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

      {merge && (
        <MergeSheet
          preview={merge}
          data={data}
          locale={locale}
          onClose={() => setMerge(null)}
          onDone={() => {
            setMerge(null);
            setEditing(false);
            onFlash(t(locale, "mergeDone"));
            load();
            onChanged();
          }}
        />
      )}
    </>
  );
}
