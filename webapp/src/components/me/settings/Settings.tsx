import { useState } from "react";
import type { MeResponse } from "../../../api";
import { t, timezoneLabel, type Locale } from "../../../i18n";
import { BackHead, Chevron, Icon, Toggle } from "../../shared/lib";
import {
  PLATFORMS,
  SETTINGS_PANES,
  TIMEZONES,
  type AdminScreen,
  type SettingsPane,
} from "../../shared/constants";
import { AdminSection } from "../../admin";
import { ChatSettingsCard } from "../chat-settings-card/ChatSettingsCard";
import { PlatformCard, type PlatNotes } from "../platform-card/PlatformCard";
import "./Settings.css";

export function Settings({
  me,
  locale,
  data,
  notes,
  onPatch,
  onChatPatch,
  onAdmin,
  onFlash,
  onConnectSteam,
  onConnectPsn,
  onConnectXbox,
  onDisconnectXbox,
  onDisconnectSteam,
  onDisconnectPsn,
  onSync,
  onDeleteAccount,
}: {
  me: MeResponse;
  locale: Locale;
  data: string;
  notes?: PlatNotes;
  onPatch: (body: {
    locale?: Locale;
    tz_offset_min?: number | null;
    show_profile_links?: boolean;
    show_secrets?: boolean;
  }) => void;
  onChatPatch: (chatId: number, body: Record<string, unknown>) => void;
  onAdmin?: (screen: AdminScreen) => void;
  onFlash: (message: string) => void;
  onConnectXbox: () => void;
  onConnectSteam: () => void;
  onConnectPsn: () => void;
  onDisconnectXbox: () => void;
  onDisconnectSteam: () => void;
  onDisconnectPsn: () => void;
  onSync: () => void;
  onDeleteAccount: () => Promise<void>;
}) {
  const [pane, setPane] = useState<SettingsPane>(SETTINGS_PANES.ROOT);
  const [deleting, setDeleting] = useState(false);
  const tz = me.settings.tz_offset_min;
  const tzOptions = TIMEZONES;

  const xboxName =
    me.xbox.gamertag_modern || me.xbox.gamertag || t(locale, "notLinked");

  if (pane === SETTINGS_PANES.ACHIEVEMENTS) {
    return (
      <>
        <BackHead
          title={t(locale, "homeAchievements")}
          backLabel={t(locale, "back")}
          onBack={() => setPane(SETTINGS_PANES.ROOT)}
        />
        <div className="glass-card">
          <div className="ios-row">
            <span>{t(locale, "showSecrets")}</span>
            <Toggle
              on={me.settings.show_secrets}
              label={t(locale, "showSecrets")}
              onClick={() =>
                onPatch({ show_secrets: !me.settings.show_secrets })
              }
            />
          </div>
          <div className="ios-row">
            <span>{t(locale, "showLinks")}</span>
            <Toggle
              on={me.settings.show_profile_links}
              label={t(locale, "showLinks")}
              onClick={() =>
                onPatch({ show_profile_links: !me.settings.show_profile_links })
              }
            />
          </div>
        </div>
      </>
    );
  }

  if (pane === SETTINGS_PANES.CHATS) {
    return (
      <>
        <BackHead
          title={t(locale, "myChats")}
          backLabel={t(locale, "back")}
          onBack={() => setPane(SETTINGS_PANES.ROOT)}
        />
        <p className="settings-hint">{t(locale, "myChatsHint")}</p>
        {me.chats.length === 0 ? (
          <p className="empty">{t(locale, "noChats")}</p>
        ) : (
          me.chats.map((chat) => (
            <ChatSettingsCard
              key={chat.chat_id}
              chat={chat}
              locale={locale}
              onPatch={onChatPatch}
            />
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

      <p className="kicker">{t(locale, "general")}</p>
      <div className="glass-card">
        <div className="ios-row">
          <span>{t(locale, "language")}</span>
          <div
            className="segment"
            role="group"
            aria-label={t(locale, "language")}
          >
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
                {timezoneLabel(z, locale)}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="ios-row"
          onClick={() => setPane(SETTINGS_PANES.ACHIEVEMENTS)}
        >
          <span>{t(locale, "homeAchievements")}</span>
          <span className="ios-value">
            <Chevron />
          </span>
        </button>
        <button
          type="button"
          className="ios-row"
          onClick={() => setPane(SETTINGS_PANES.CHATS)}
        >
          <span>{t(locale, "myChats")}</span>
          <span className="ios-value">
            {me.chats.filter((c) => c.is_subscribed).length || "—"}
            <Chevron />
          </span>
        </button>
      </div>

      <div className="accounts-head">
        <p className="kicker">{t(locale, "accounts")}</p>
        <button
          type="button"
          className="accounts-delete"
          aria-label={t(locale, "deleteAccount")}
          title={t(locale, "deleteAccount")}
          disabled={deleting}
          onClick={async () => {
            // Telegram's own confirmation, like turning off publishing to a chat.
            if (!window.confirm(t(locale, "deleteWarning"))) return;
            setDeleting(true);
            try {
              await onDeleteAccount();
              window.alert(t(locale, "deleteDone"));
              window.Telegram?.WebApp?.close?.();
            } catch (err) {
              onFlash(`${t(locale, "error")}: ${String(err)}`);
            } finally {
              setDeleting(false);
            }
          }}
        >
          <Icon name="trash" size={20} />
        </button>
      </div>
      <PlatformCard
        linked={me.xbox.linked}
        name={xboxName}
        mark={PLATFORMS.XBOX}
        profileUrl={me.xbox.profile_url}
        locale={locale}
        onConnect={onConnectXbox}
        onDisconnect={onDisconnectXbox}
        onSync={me.xbox.linked ? onSync : undefined}
        notes={[
          me.xbox.needs_reconnect ? { kind: "error", text: t(locale, "reconnectHint") } : null,
          notes?.xbox,
        ]}
      />

      <PlatformCard
        linked={me.psn.linked}
        name={me.psn.linked ? me.psn.online_id || me.psn.account_id : ""}
        mark={PLATFORMS.PSN}
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
        mark={PLATFORMS.STEAM}
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


      {me.is_admin && onAdmin && (
        <AdminSection
          data={data}
          locale={locale}
          onNavigate={onAdmin}
          onFail={(err) => onFlash(`${t(locale, "error")}: ${String(err)}`)}
        />
      )}
    </>
  );
}
