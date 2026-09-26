import { useState } from "react";
import type { ChatRow, MeResponse } from "./api";
import { rarityLabel, t, type Locale } from "./i18n";
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

type PlatformKey = "xbox" | "psn" | "steam";

type AccountRow = {
  key: string;
  name: string;
  profileUrl: string | null;
  publishes: boolean;
  onTogglePublish?: () => void;
  onDisconnect: () => void;
};

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
  onTogglePublish,
}: {
  me: MeResponse;
  locale: Locale;
  notes?: PlatNotes;
  onConnectXbox: () => void;
  onConnectSteam: () => void;
  onConnectPsn: () => void;
  onDisconnectXbox: () => void;
  onDisconnectSteam: () => void;
  onDisconnectPsn: (accountId?: string) => void;
  onSync: () => void;
  onTogglePublish?: (platform: PlatformKey, publishes: boolean, accountId?: string) => void;
}) {
  const toggle = (platform: PlatformKey, publishes: boolean, accountId?: string) =>
    onTogglePublish ? () => onTogglePublish(platform, !publishes, accountId) : undefined;

  const xboxAccounts: AccountRow[] = me.xbox.linked
    ? [
        {
          key: "xbox",
          name: me.xbox.gamertag_modern || me.xbox.gamertag || t(locale, "notLinked"),
          profileUrl: me.xbox.profile_url,
          publishes: me.xbox.publishes !== false,
          onTogglePublish: toggle("xbox", me.xbox.publishes !== false),
          onDisconnect: onDisconnectXbox,
        },
      ]
    : [];

  // Several PSN accounts (#10), each named "PSN: nick" — a bare nickname
  // does not say which platform the row is (owner).
  const psnAccounts: AccountRow[] = !me.psn.linked
    ? []
    : (
        me.psn.accounts ?? [
          {
            account_id: me.psn.account_id,
            name: me.psn.online_id || me.psn.account_id,
            publishes: me.psn.publishes !== false,
            profile_url: me.psn.profile_url,
          },
        ]
      ).map((account) => ({
        key: account.account_id,
        name: `PSN: ${account.name}`,
        profileUrl: account.profile_url,
        publishes: account.publishes,
        onTogglePublish: toggle("psn", account.publishes, account.account_id),
        onDisconnect: () => onDisconnectPsn(account.account_id),
      }));
  const psnMax = me.psn.linked ? (me.psn.max_accounts ?? 1) : 1;
  const psnHidden =
    me.psn.linked &&
    (me.psn.accounts ?? []).some((account) => account.achievements_visible === false);

  const steamAccounts: AccountRow[] = me.steam.linked
    ? [
        {
          key: "steam",
          name: me.steam.display_name || me.steam.steam_id,
          profileUrl: me.steam.profile_url,
          publishes: me.steam.publishes !== false,
          onTogglePublish: toggle("steam", me.steam.publishes !== false),
          onDisconnect: onDisconnectSteam,
        },
      ]
    : [];

  return (
    <>
      <PlatformCard
        mark="xbox"
        title="XBOX"
        accounts={xboxAccounts}
        locale={locale}
        onConnect={onConnectXbox}
        onSync={me.xbox.linked ? onSync : undefined}
        notes={[
          me.xbox.needs_reconnect ? { kind: "error", text: t(locale, "reconnectHint") } : null,
          notes?.xbox,
        ]}
      />

      <PlatformCard
        mark="psn"
        title={
          psnAccounts.length > 1
            ? `PSN · ${psnAccounts.length} ${t(locale, "of")} ${psnMax}`
            : "PSN"
        }
        accounts={psnAccounts}
        locale={locale}
        onConnect={onConnectPsn}
        onAdd={psnAccounts.length && psnAccounts.length < psnMax ? onConnectPsn : undefined}
        onSync={me.psn.linked ? onSync : undefined}
        notes={[
          psnHidden || (me.psn.linked && me.psn.achievements_visible === false)
            ? { kind: "warn", text: t(locale, "hiddenPsn") }
            : null,
          notes?.psn,
        ]}
      />

      <PlatformCard
        mark="steam"
        title="Steam"
        accounts={steamAccounts}
        locale={locale}
        onConnect={onConnectSteam}
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

/** One platform: its name, then every account it holds with worded
 * buttons — profile, posting, unlink (#10; an icon alone said nothing). */
function PlatformCard({
  mark,
  title,
  accounts,
  locale,
  onConnect,
  onAdd,
  onSync,
  notes,
}: {
  mark: string;
  title: string;
  accounts: AccountRow[];
  locale: Locale;
  onConnect: () => void;
  onAdd?: () => void;
  onSync?: () => void;
  notes?: Array<PlatNote | null | undefined>;
}) {
  const linked = accounts.length > 0;
  return (
    <div className={linked ? "plat-card is-linked" : "plat-card"}>
      <div className="plat-card-main">
        <PlatformLogo platform={mark} size={22} />
        <strong className="plat-card-nick">
          {linked ? title : `${title} · ${t(locale, "notLinked")}`}
        </strong>
        {linked ? null : (
          <button type="button" className="btn sm" onClick={onConnect}>
            {t(locale, "connect")}
          </button>
        )}
      </div>
      {accounts.map((account) => (
        <div key={account.key} className="plat-account">
          <p className="plat-account-name">{account.name}</p>
          <div className="plat-buttons">
            {account.profileUrl ? (
              <a
                className="btn sm ghost"
                href={account.profileUrl}
                target="_blank"
                rel="noreferrer"
              >
                {t(locale, "profile")}
              </a>
            ) : null}
            {account.onTogglePublish ? (
              <button type="button" className="btn sm ghost" onClick={account.onTogglePublish}>
                {t(locale, account.publishes ? "publishingOn" : "publishingOff")}
              </button>
            ) : null}
            <button type="button" className="btn sm ghost is-danger" onClick={account.onDisconnect}>
              {t(locale, "disconnect")}
            </button>
          </div>
        </div>
      ))}
      {linked && (onSync || onAdd) ? (
        <div className="plat-buttons plat-buttons-foot">
          {onSync ? (
            <button type="button" className="btn sm ghost" onClick={onSync}>
              {t(locale, "sync")}
            </button>
          ) : null}
          {onAdd ? (
            <button type="button" className="btn sm ghost" onClick={onAdd}>
              {t(locale, "addPsnAccount")}
            </button>
          ) : null}
        </div>
      ) : null}
      {(notes ?? []).filter((n): n is PlatNote => Boolean(n)).map((note) => (
        <p key={`${note.kind}:${note.text}`} className={`plat-note is-${note.kind}`}>
          {note.text}
        </p>
      ))}
    </div>
  );
}


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
  onTogglePublish,
}: {
  me: MeResponse;
  locale: Locale;
  notes?: PlatNotes;
  onTogglePublish?: (platform: PlatformKey, publishes: boolean, accountId?: string) => void;
  onPatch: (body: {
    locale?: Locale;
    tz_offset_min?: number | null;
    show_profile_links?: boolean;
    show_secrets?: boolean;
    rarity_mode?: string;
  }) => void;
  onChatPatch: (chatId: number, body: Record<string, unknown>) => void;
  onAdmin?: () => void;
  onConnectXbox: () => void;
  onConnectSteam: () => void;
  onConnectPsn: () => void;
  onDisconnectXbox: () => void;
  onDisconnectSteam: () => void;
  onDisconnectPsn: (accountId?: string) => void;
  onSync: () => void;
}) {
  const [pane, setPane] = useState<"root" | "achievements" | "chats">("root");
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
          {/* One mode for every chat this person publishes to (#126). */}
          <label className="ios-row">
            <span>{t(locale, "rarity")}</span>
            <select
              className="tz-select"
              value={me.settings.rarity_mode ?? "all"}
              onChange={(e) => onPatch({ rarity_mode: e.target.value })}
            >
              <option value="all">{rarityLabel("all", locale)}</option>
              <option value="rare">{rarityLabel("rare", locale)}</option>
              <option value="hidden">{rarityLabel("hidden", locale)}</option>
            </select>
          </label>
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

  if (pane === "chats") {
    return (
      <>
        <BackHead
          title={t(locale, "myChats")}
          backLabel={t(locale, "back")}
          onBack={() => setPane("root")}
        />
        <p className="settings-hint">{t(locale, "myChatsHint")}</p>
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
        onTogglePublish={onTogglePublish}
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
    <div className="glass-card chat-settings-card">
      <p className="chat-settings-title">{chat.title || String(chat.chat_id)}</p>
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
