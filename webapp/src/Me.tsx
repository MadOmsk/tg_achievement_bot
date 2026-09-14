import { useState, type ReactNode } from "react";
import type { ChatRow, MeResponse } from "./api";
import { digestLabel, formatOffset, rarityLabel, t, type Locale } from "./i18n";
import { BackHead, PlatformLogo, Toggle } from "./ui";

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
        title="Xbox"
        mark="xbox"
        linked={me.xbox.linked}
        name={xboxName}
        meta={
          me.xbox.linked
            ? [
                `${me.xbox.achievement_count} ${t(locale, "achievements")}`,
                me.xbox.completed_games ? `🏆 ${me.xbox.completed_games}` : null,
                `${me.xbox.gamerscore ?? 0} G`,
              ].filter(Boolean) as string[]
            : []
        }
        presence={presenceText(me.xbox.presence, locale)}
        profileUrl={me.xbox.profile_url}
        locale={locale}
        onConnect={onConnectXbox}
        onDisconnect={onDisconnectXbox}
        extra={
          me.xbox.linked ? (
            <button type="button" onClick={onSync}>
              {t(locale, "sync")}
            </button>
          ) : null
        }
        notes={[
          me.xbox.needs_reconnect
            ? { kind: "error", text: t(locale, "reconnectHint") }
            : null,
          notes?.xbox,
        ]}
      />

      <PlatformCard
        title="PlayStation"
        mark="psn"
        linked={me.psn.linked}
        name={me.psn.linked ? me.psn.online_id || me.psn.account_id : ""}
        meta={
          me.psn.linked
            ? [
                `${me.psn.trophy_count} ${t(locale, "trophies")}`,
                me.psn.platinum_count ? `🏆 ${me.psn.platinum_count}` : null,
                me.psn.trophy_level != null
                  ? `${t(locale, "level")} ${me.psn.trophy_level}`
                  : null,
                me.psn.visibility,
              ].filter(Boolean) as string[]
            : []
        }
        presence={me.psn.linked ? presenceText(me.psn.presence, locale) : null}
        profileUrl={me.psn.linked ? me.psn.profile_url : null}
        locale={locale}
        onConnect={onConnectPsn}
        onDisconnect={onDisconnectPsn}
        notes={[
          me.psn.linked && me.psn.achievements_visible === false
            ? { kind: "warn", text: t(locale, "hiddenPsn") }
            : null,
          notes?.psn,
        ]}
      />

      <PlatformCard
        title="Steam"
        mark="steam"
        linked={me.steam.linked}
        name={me.steam.linked ? me.steam.display_name || me.steam.steam_id : ""}
        meta={
          me.steam.linked
            ? [
                `${me.steam.achievement_count} ${t(locale, "achievements")}`,
                me.steam.completed_games ? `🏆 ${me.steam.completed_games}` : null,
                me.steam.visibility,
              ].filter(Boolean) as string[]
            : []
        }
        presence={me.steam.linked ? presenceText(me.steam.presence, locale) : null}
        profileUrl={me.steam.linked ? me.steam.profile_url : null}
        locale={locale}
        onConnect={onConnectSteam}
        onDisconnect={onDisconnectSteam}
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
  title,
  mark,
  linked,
  name,
  meta,
  presence,
  profileUrl,
  locale,
  onConnect,
  onDisconnect,
  extra,
  notes,
}: {
  title: string;
  mark: string;
  linked: boolean;
  name: string;
  meta: string[];
  presence: string | null;
  profileUrl: string | null;
  locale: Locale;
  onConnect: () => void;
  onDisconnect: () => void;
  extra?: ReactNode;
  notes?: Array<PlatNote | null | undefined>;
}) {
  const stats = [...meta, presence].filter(Boolean) as string[];
  return (
    <div className={linked ? "plat-card is-linked" : "plat-card"}>
      <div className="plat-card-main">
        <PlatformLogo platform={mark} size={36} />
        <span className="plat-card-copy">
          <strong>{title}</strong>
          <p>{linked ? name : t(locale, "notLinked")}</p>
          {linked && stats.length > 0 ? (
            <p className="plat-card-meta">{stats.join(" · ")}</p>
          ) : null}
        </span>
        {linked ? (
          <button type="button" className="btn sm danger" onClick={onDisconnect}>
            {t(locale, "disconnect")}
          </button>
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
      {linked && (profileUrl || extra) ? (
        <div className="plat-card-actions">
          {profileUrl ? (
            <a href={profileUrl} target="_blank" rel="noreferrer">
              {t(locale, "profile")}
            </a>
          ) : (
            <span />
          )}
          {extra ?? <span />}
        </div>
      ) : null}
    </div>
  );
}

const DIGEST_CHOICES = [2, 3, 4, 5, 6, 8, 10, 99] as const;

export function Settings({
  me,
  locale,
  onPatch,
  onChatPatch,
  onConnectSteam,
  onConnectPsn,
  onConnectXbox,
  onDisconnectXbox,
  onDisconnectSteam,
  onDisconnectPsn,
  onSync,
  notes,
  onAdmin,
}: {
  me: MeResponse;
  locale: Locale;
  onPatch: (body: {
    locale?: string;
    tz_offset_min?: number | null;
    show_profile_links?: boolean;
    show_secrets?: boolean;
  }) => void;
  onChatPatch: (chatId: number, body: Record<string, unknown>) => void;
  onConnectXbox: () => void;
  onConnectSteam: () => void;
  onConnectPsn: () => void;
  onDisconnectXbox: () => void;
  onDisconnectSteam: () => void;
  onDisconnectPsn: () => void;
  onSync: () => void;
  notes?: PlatNotes;
  onAdmin?: () => void;
}) {
  const [pane, setPane] = useState<"home" | "achievements" | "notifications" | "chats" | "chat">(
    "home",
  );
  const [chatId, setChatId] = useState<number | null>(null);
  const tz = me.settings.tz_offset_min;
  const tzOptions =
    tz != null && !TIMEZONES.some((z) => z.min === tz)
      ? [{ min: tz, ru: formatOffset(tz, "ru"), en: formatOffset(tz, "en") }, ...TIMEZONES]
      : TIMEZONES;
  const chat = chatId == null ? null : (me.chats.find((c) => c.chat_id === chatId) ?? null);

  if (pane === "notifications") {
    return (
      <>
        <BackHead
          title={t(locale, "notifications")}
          onBack={() => setPane("home")}
          backLabel={t(locale, "back")}
        />
        <div className="glass-card">
          <div className="ios-row">
            <span>{t(locale, "showLinks")}</span>
            <Toggle
              on={me.settings.show_profile_links}
              onClick={() => onPatch({ show_profile_links: !me.settings.show_profile_links })}
              label={t(locale, "showLinks")}
            />
          </div>
        </div>
      </>
    );
  }

  if (pane === "achievements") {
    return (
      <>
        <BackHead
          title={t(locale, "homeAchievements")}
          onBack={() => setPane("home")}
          backLabel={t(locale, "back")}
        />
        <div className="glass-card">
          <div className="ios-row">
            <span>{t(locale, "showSecrets")}</span>
            <Toggle
              on={me.settings.show_secrets}
              onClick={() => onPatch({ show_secrets: !me.settings.show_secrets })}
              label={t(locale, "showSecrets")}
            />
          </div>
        </div>
      </>
    );
  }

  if (pane === "chats") {
    return (
      <>
        <BackHead
          title={t(locale, "myChats")}
          onBack={() => setPane("home")}
          backLabel={t(locale, "back")}
        />
        {me.chats.length === 0 ? (
          <p className="empty">{t(locale, "noChats")}</p>
        ) : (
          <div className="glass-card">
            {me.chats.map((row) => (
              <button
                key={row.chat_id}
                type="button"
                className="ios-row admin-user-row"
                onClick={() => {
                  setChatId(row.chat_id);
                  setPane("chat");
                }}
              >
                <span className="admin-limit-copy">
                  <strong>{row.title || `chat ${row.chat_id}`}</strong>
                  <small>
                    {row.is_subscribed
                      ? rarityLabel(row.rarity_mode, locale)
                      : t(locale, "unsubscribe")}
                  </small>
                </span>
                <span className="ios-value">›</span>
              </button>
            ))}
          </div>
        )}
      </>
    );
  }

  if (pane === "chat") {
    return (
      <>
        <BackHead
          title={chat?.title || t(locale, "myChats")}
          onBack={() => {
            setPane("chats");
            setChatId(null);
          }}
          backLabel={t(locale, "back")}
        />
        {chat ? (
          <ChatSettingsCard chat={chat} locale={locale} onPatch={onChatPatch} />
        ) : (
          <p className="empty">{t(locale, "noChats")}</p>
        )}
      </>
    );
  }

  return (
    <>
      <header className="page-head">
        <h1>{t(locale, "settings")}</h1>
      </header>

      <p className="kicker">{t(locale, "general")}</p>
      <div className="glass-card">
        <div className="ios-row">
          <span>{t(locale, "language")}</span>
          <div className="segment">
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
      {chat.is_subscribed ? (
        <>
          <label className="ios-row">
            <span>{t(locale, "rarity")}</span>
            <select
              className="tz-select"
              value={chat.rarity_mode ?? "all"}
              aria-label={t(locale, "rarity")}
              onChange={(e) =>
                onPatch(chat.chat_id, {
                  action: "set_rarity",
                  rarity_mode: e.target.value,
                })
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
              aria-label={t(locale, "digest")}
              onChange={(e) =>
                onPatch(chat.chat_id, {
                  action: "set_digest",
                  digest_threshold: Number(e.target.value),
                })
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
  label,
  onBack,
  onSubmit,
}: {
  locale: Locale;
  label: string;
  onBack: () => void;
  onSubmit: (value: string) => Promise<void>;
}) {
  const [value, setValue] = useState("");
  const [note, setNote] = useState<PlatNote | null>(null);
  return (
    <>
      <BackHead title={t(locale, "connect")} onBack={onBack} backLabel={t(locale, "back")} />
      <div className="glass-card">
        <div className="ios-row">
          <span className="admin-limit-copy">
            <strong>{label}</strong>
          </span>
        </div>
        <label className="ios-row">
          <input
            className="admin-secret-input"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            autoFocus
            aria-label={label}
          />
        </label>
        {note ? (
          <div className="ios-row">
            <span className={`plat-note is-${note.kind}`}>{note.text}</span>
          </div>
        ) : null}
        <button
          type="button"
          className="ios-row"
          disabled={!value.trim()}
          onClick={() => {
            setNote(null);
            void onSubmit(value.trim()).catch((err: unknown) => {
              setNote({ kind: "error", text: String(err) });
            });
          }}
        >
          <span>{t(locale, "submit")}</span>
          <span className="ios-value">›</span>
        </button>
        <button type="button" className="ios-row" onClick={onBack}>
          <span>{t(locale, "cancel")}</span>
        </button>
      </div>
    </>
  );
}

function presenceText(
  presence: MeResponse["xbox"]["presence"],
  locale: Locale,
): string | null {
  if (!presence) return null;
  const game = presence.title_name || presence.game_name;
  if (presence.state === "Online" || presence.state === "online") {
    return game ? `${t(locale, "playing")} ${game}` : t(locale, "idle");
  }
  return t(locale, "offline");
}
