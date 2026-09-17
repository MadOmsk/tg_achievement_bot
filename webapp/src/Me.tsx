import { useState } from "react";
import type { ChatRow, MeResponse } from "./api";
import { digestLabel, rarityLabel, t, type Locale } from "./i18n";
import { BackHead, Icon, PlatformLogo, Toggle } from "./ui";

export const TIMEZONES: Array<{ min: number; ru: string; en: string }> = [
  { min: -480, ru: "Лос-Анджелес · UTC−8", en: "Los Angeles · UTC−8" },
  { min: -300, ru: "Нью-Йорк · UTC−5", en: "New York · UTC−5" },
  { min: 0, ru: "Лондон · UTC+0", en: "London · UTC+0" },
  { min: 60, ru: "Берлин · UTC+1", en: "Berlin · UTC+1" },
  { min: 120, ru: "Калининград · UTC+2", en: "Kaliningrad · UTC+2" },
  { min: 180, ru: "Москва · UTC+3", en: "Moscow · UTC+3" },
  { min: 240, ru: "Самара · UTC+4", en: "Samara · UTC+4" },
  { min: 300, ru: "Екатеринбург · UTC+5", en: "Yekaterinburg · UTC+5" },
  { min: 360, ru: "Омск · UTC+6", en: "Omsk · UTC+6" },
  { min: 420, ru: "Новосибирск · UTC+7", en: "Novosibirsk · UTC+7" },
  { min: 480, ru: "Иркутск · UTC+8", en: "Irkutsk · UTC+8" },
  { min: 540, ru: "Якутск · UTC+9", en: "Yakutsk · UTC+9" },
  { min: 600, ru: "Владивосток · UTC+10", en: "Vladivostok · UTC+10" },
  { min: 660, ru: "Магадан · UTC+11", en: "Magadan · UTC+11" },
  { min: 720, ru: "Камчатка · UTC+12", en: "Kamchatka · UTC+12" },
];

export type PlatNote = { kind: "error" | "warn" | "info"; text: string };
export type PlatNotes = Partial<Record<"xbox" | "steam" | "psn", PlatNote>>;

export function Me({
  me,
  locale,
  notes,
  onConnectSteam,
  onConnectPsn,
  onConnectXbox,
  onDisconnectXbox,
  onDisconnectSteam,
  onDisconnectPsn,
  onSync,
}: {
  me: MeResponse;
  locale: Locale;
  notes?: PlatNotes;
  onConnectXbox: () => void;
  onConnectSteam: () => void;
  onConnectPsn: () => void;
  onDisconnectXbox: () => void;
  onDisconnectSteam: () => void;
  onDisconnectPsn: () => void;
  onSync: () => void;
}) {
  const xboxName =
    me.xbox.gamertag_modern || me.xbox.gamertag || t(locale, "notLinked");

  return (
    <>
      <PlatformCard
        linked={me.xbox.linked}
        name={xboxName}
        mark="xbox"
        profileUrl={me.xbox.profile_url}
        locale={locale}
        onConnect={onConnectXbox}
        onDisconnect={onDisconnectXbox}
        onSync={me.xbox.linked ? onSync : undefined}
        notes={[
          me.xbox.needs_reconnect
            ? { kind: "error", text: t(locale, "reconnectHint") }
            : null,
          notes?.xbox,
        ]}
      />

      <PlatformCard
        linked={me.psn.linked}
        name={me.psn.linked ? me.psn.online_id || me.psn.account_id : ""}
        mark="psn"
        profileUrl={me.psn.linked ? me.psn.profile_url : null}
        locale={locale}
        onConnect={onConnectPsn}
        onDisconnect={onDisconnectPsn}
        onSync={me.psn.linked ? onSync : undefined}
        notes={[
          me.psn.linked && me.psn.achievements_visible === false
            ? { kind: "warn", text: t(locale, "hiddenPsn") }
            : null,
          notes?.psn,
        ]}
      />

      <PlatformCard
        linked={me.steam.linked}
        name={me.steam.linked ? me.steam.display_name || me.steam.steam_id : ""}
        mark="steam"
        profileUrl={me.steam.linked ? me.steam.profile_url : null}
        locale={locale}
        onConnect={onConnectSteam}
        onDisconnect={onDisconnectSteam}
        onSync={me.steam.linked ? onSync : undefined}
        notes={[
          me.steam.linked && me.steam.achievements_visible === false
            ? { kind: "warn", text: t(locale, "hiddenSteam") }
            : null,
          notes?.steam,
        ]}
      />
    </>
  );
}

function PlatformCard({
  mark,
  linked,
  name,
  profileUrl,
  locale,
  onConnect,
  onDisconnect,
  onSync,
  notes,
}: {
  mark: string;
  linked: boolean;
  name: string;
  profileUrl: string | null;
  locale: Locale;
  onConnect: () => void;
  onDisconnect: () => void;
  onSync?: () => void;
  notes?: Array<PlatNote | null | undefined>;
}) {
  return (
    <div className={linked ? "plat-card is-linked" : "plat-card"}>
      <div className="plat-card-main">
        <PlatformLogo platform={mark} size={36} />
        <strong className="plat-card-nick">
          {linked ? name : t(locale, "notLinked")}
        </strong>
        {linked ? (
          <div className="plat-card-icons" role="group">
            {profileUrl ? (
              <a
                href={profileUrl}
                target="_blank"
                rel="noreferrer"
                aria-label={t(locale, "profile")}
                title={t(locale, "profile")}
              >
                <Icon name="link" size={18} />
              </a>
            ) : (
              <span className="is-disabled" aria-hidden>
                <Icon name="link" size={18} />
              </span>
            )}
            {onSync ? (
              <button
                type="button"
                onClick={onSync}
                aria-label={t(locale, "sync")}
                title={t(locale, "sync")}
              >
                <Icon name="sync" size={18} />
              </button>
            ) : (
              <span className="is-disabled" aria-hidden>
                <Icon name="sync" size={18} />
              </span>
            )}
            <button
              type="button"
              className="is-danger"
              onClick={onDisconnect}
              aria-label={t(locale, "disconnect")}
              title={t(locale, "disconnect")}
            >
              <Icon name="off" size={18} />
            </button>
          </div>
        ) : (
          <button type="button" className="btn sm" onClick={onConnect}>
            {t(locale, "connect")}
          </button>
        )}
      </div>
      {(notes ?? []).filter((n): n is PlatNote => Boolean(n)).map((note) => (
        <p key={`${note.kind}:${note.text}`} className={`plat-note is-${note.kind}`}>
          {note.text}
        </p>
      ))}
    </div>
  );
}

const DIGEST_CHOICES = [2, 3, 4, 5, 6, 8, 10, 99] as const;

export function Settings({
  me,
  locale,
  notes,
  onPatch,
  onChatPatch,
  onAdmin,
  onConnectSteam,
  onConnectPsn,
  onConnectXbox,
  onDisconnectXbox,
  onDisconnectSteam,
  onDisconnectPsn,
  onSync,
}: {
  me: MeResponse;
  locale: Locale;
  notes?: PlatNotes;
  onPatch: (body: {
    locale?: Locale;
    tz_offset_min?: number | null;
    show_profile_links?: boolean;
    show_secrets?: boolean;
  }) => void;
  onChatPatch: (chatId: number, body: Record<string, unknown>) => void;
  onAdmin?: () => void;
  onConnectXbox: () => void;
  onConnectSteam: () => void;
  onConnectPsn: () => void;
  onDisconnectXbox: () => void;
  onDisconnectSteam: () => void;
  onDisconnectPsn: () => void;
  onSync: () => void;
}) {
  const [pane, setPane] = useState<"root" | "achievements" | "notifications" | "chats">("root");
  const tz = me.settings.tz_offset_min;
  const tzOptions = TIMEZONES;

  if (pane === "achievements") {
    return (
      <>
        <BackHead
          title={t(locale, "homeAchievements")}
          backLabel={t(locale, "back")}
          onBack={() => setPane("root")}
        />
        <div className="glass-card">
          <div className="ios-row">
            <span>{t(locale, "showSecrets")}</span>
            <Toggle
              on={me.settings.show_secrets}
              label={t(locale, "showSecrets")}
              onClick={() => onPatch({ show_secrets: !me.settings.show_secrets })}
            />
          </div>
          <div className="ios-row">
            <span>{t(locale, "showLinks")}</span>
            <Toggle
              on={me.settings.show_profile_links}
              label={t(locale, "showLinks")}
              onClick={() => onPatch({ show_profile_links: !me.settings.show_profile_links })}
            />
          </div>
        </div>
      </>
    );
  }

  if (pane === "notifications") {
    return (
      <>
        <BackHead
          title={t(locale, "notifications")}
          backLabel={t(locale, "back")}
          onBack={() => setPane("root")}
        />
        {me.chats.length === 0 ? (
          <p className="empty">{t(locale, "noChats")}</p>
        ) : (
          me.chats.map((chat) => (
            <ChatSettingsCard key={chat.chat_id} chat={chat} locale={locale} onPatch={onChatPatch} />
          ))
        )}
      </>
    );
  }

  if (pane === "chats") {
    return (
      <>
        <BackHead
          title={t(locale, "myChats")}
          backLabel={t(locale, "back")}
          onBack={() => setPane("root")}
        />
        {me.chats.length === 0 ? (
          <p className="empty">{t(locale, "noChats")}</p>
        ) : (
          me.chats.map((chat) => (
            <ChatSettingsCard key={chat.chat_id} chat={chat} locale={locale} onPatch={onChatPatch} />
          ))
        )}
      </>
    );
  }

  return (
    <>
      <header className="page-head">
        <h1>{t(locale, "settings")}</h1>
      </header>

      <div className="glass-card">
        <div className="ios-row">
          <span>{t(locale, "language")}</span>
          <div className="segment" role="group" aria-label={t(locale, "language")}>
            <button
              type="button"
              className={locale === "ru" ? "is-on" : undefined}
              onClick={() => onPatch({ locale: "ru" })}
            >
              RU
            </button>
            <button
              type="button"
              className={locale === "en" ? "is-on" : undefined}
              onClick={() => onPatch({ locale: "en" })}
            >
              EN
            </button>
          </div>
        </div>
        <label className="ios-row">
          <span>{t(locale, "timezone")}</span>
          <select
            className="tz-select"
            value={tz ?? ""}
            onChange={(e) => {
              const v = e.target.value;
              onPatch({ tz_offset_min: v === "" ? null : Number(v) });
            }}
            aria-label={t(locale, "timezone")}
          >
            <option value="">{t(locale, "tzUnset")}</option>
            {tzOptions.map((z) => (
              <option key={z.min} value={z.min}>
                {locale === "en" ? z.en : z.ru}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="ios-row" onClick={() => setPane("achievements")}>
          <span>{t(locale, "homeAchievements")}</span>
          <span className="ios-value">›</span>
        </button>
        <button type="button" className="ios-row" onClick={() => setPane("notifications")}>
          <span>{t(locale, "notifications")}</span>
          <span className="ios-value">›</span>
        </button>
        <button type="button" className="ios-row" onClick={() => setPane("chats")}>
          <span>{t(locale, "myChats")}</span>
          <span className="ios-value">
            {me.chats.filter((c) => c.is_subscribed).length || "—"} ›
          </span>
        </button>
      </div>

      <p className="kicker">{t(locale, "accounts")}</p>
      <Me
        me={me}
        locale={locale}
        onConnectXbox={onConnectXbox}
        onConnectSteam={onConnectSteam}
        onConnectPsn={onConnectPsn}
        onDisconnectXbox={onDisconnectXbox}
        onDisconnectSteam={onDisconnectSteam}
        onDisconnectPsn={onDisconnectPsn}
        onSync={onSync}
        notes={notes}
      />

      {me.is_admin && onAdmin ? (
        <>
          <p className="kicker">{t(locale, "admin")}</p>
          <div className="glass-card">
            <button type="button" className="ios-row" onClick={onAdmin}>
              <span>{t(locale, "adminHome")}</span>
              <span className="ios-value">›</span>
            </button>
          </div>
        </>
      ) : null}
    </>
  );
}

function ChatSettingsCard({
  chat,
  locale,
  onPatch,
}: {
  chat: ChatRow;
  locale: Locale;
  onPatch: (chatId: number, body: Record<string, unknown>) => void;
}) {
  return (
    <div className="glass-card">
      <div className="ios-row">
        <span>{t(locale, "subscribe")}</span>
        <Toggle
          on={chat.is_subscribed}
          label={t(locale, "subscribe")}
          onClick={() =>
            onPatch(chat.chat_id, {
              action: chat.is_subscribed ? "unsubscribe" : "subscribe",
            })
          }
        />
      </div>
      <p className="ios-sub">{chat.title || chat.chat_id}</p>
      {chat.is_subscribed ? (
        <>
          <label className="ios-row">
            <span>{t(locale, "rarity")}</span>
            <select
              className="tz-select"
              value={chat.rarity_mode ?? "all"}
              onChange={(e) =>
                onPatch(chat.chat_id, { rarity_mode: e.target.value })
              }
            >
              <option value="all">{rarityLabel("all", locale)}</option>
              <option value="rare">{rarityLabel("rare", locale)}</option>
              <option value="hidden">{rarityLabel("hidden", locale)}</option>
            </select>
          </label>
          <label className="ios-row">
            <span>{t(locale, "digest")}</span>
            <select
              className="tz-select"
              value={chat.digest_threshold ?? 3}
              onChange={(e) =>
                onPatch(chat.chat_id, { digest_threshold: Number(e.target.value) })
              }
            >
              {DIGEST_CHOICES.map((n) => (
                <option key={n} value={n}>
                  {digestLabel(n, locale)}
                </option>
              ))}
            </select>
          </label>
        </>
      ) : null}
    </div>
  );
}

export function ConnectForm({
  locale,
  platform,
  label,
  onBack,
  onSubmit,
}: {
  locale: Locale;
  platform: "steam" | "psn";
  label: string;
  onBack: () => void;
  onSubmit: (identity: string) => Promise<void>;
}) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const title = platform === "steam" ? "Steam" : "PlayStation";

  const send = () => {
    if (!value.trim() || busy) return;
    setBusy(true);
    setNote(null);
    void onSubmit(value.trim())
      .catch((err: unknown) => setNote(String(err)))
      .finally(() => setBusy(false));
  };

  return (
    <>
      <BackHead title={t(locale, "connect")} backLabel={t(locale, "back")} onBack={onBack} />
      <form
        className="glass-card connect-form"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <div className="connect-form-head">
          <PlatformLogo platform={platform} size={40} />
          <span>
            <strong>{title}</strong>
            <p>{label}</p>
          </span>
        </div>
        <input
          className="input wide"
          value={value}
          placeholder={platform === "steam" ? "steamcommunity.com/id/…" : "Online ID"}
          onChange={(e) => setValue(e.target.value)}
          autoCapitalize="off"
          autoCorrect="off"
          spellCheck={false}
          enterKeyHint="done"
          autoFocus
        />
        {note ? <p className="plat-note is-error">{note}</p> : null}
        <button type="submit" className="btn" disabled={!value.trim() || busy}>
          {t(locale, "submit")}
        </button>
      </form>
    </>
  );
}
