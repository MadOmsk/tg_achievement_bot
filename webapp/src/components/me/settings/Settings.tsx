import { useState } from "react";
import type { AccountPlatform, MeResponse } from "../../../api";
import { rarityLabel, t, timezoneLabel, type Locale } from "../../../i18n";
import { BackHead, Chevron, Icon, Toggle } from "../../shared/lib";
import {
  PLATFORMS,
  RARITY_MODES,
  SETTINGS_PANES,
  TIMEZONES,
  type AdminScreen,
  type SettingsPane,
} from "../../shared/constants";
import { AdminSection } from "../../admin";
import { NicknameForm } from "../nickname/NicknameForm";
import { PrivacyPane } from "../privacy/PrivacyPane";
import { PlatformCard, type AccountRow, type PlatNotes } from "../platform-card/PlatformCard";
import "./Settings.css";

export function Settings({
  me,
  locale,
  data,
  notes,
  onPatch,
  onChatPatch,
  onNickname,
  onLogout,
  onAccountPublishes,
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
    show_secrets?: boolean;
    rarity_mode?: string;
  }) => void;
  onChatPatch: (chatId: number, body: Record<string, unknown>) => void;
  onNickname: (handle: string) => Promise<void>;
  /** Set only in a plain browser, where a session can be ended. */
  onLogout?: () => void;
  onAccountPublishes: (platform: AccountPlatform, publishes: boolean, accountId?: string) => void;
  onAdmin?: (screen: AdminScreen) => void;
  onFlash: (message: string) => void;
  onConnectXbox: () => void;
  onConnectSteam: () => void;
  onConnectPsn: () => void;
  onDisconnectXbox: () => void;
  onDisconnectSteam: () => void;
  onDisconnectPsn: (accountId?: string) => void;
  onSync: () => void;
  onDeleteAccount: () => Promise<void>;
}) {
  const [pane, setPane] = useState<SettingsPane>(SETTINGS_PANES.ROOT);
  const [deleting, setDeleting] = useState(false);
  const tz = me.settings.tz_offset_min;
  const tzOptions = TIMEZONES;

  const xboxAccounts: AccountRow[] = me.xbox.linked
    ? [
        {
          key: "xbox",
          name: me.xbox.gamertag_modern || me.xbox.gamertag || t(locale, "notLinked"),
          profileUrl: me.xbox.profile_url,
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
        onDisconnect: () => onDisconnectPsn(account.account_id),
      }));
  const psnMax = me.psn.linked ? (me.psn.max_accounts ?? 1) : 1;
  const psnHidden =
    me.psn.linked &&
    (me.psn.achievements_visible === false ||
      (me.psn.accounts ?? []).some((account) => account.achievements_visible === false));

  const steamAccounts: AccountRow[] = me.steam.linked
    ? [
        {
          key: "steam",
          name: me.steam.display_name || me.steam.steam_id,
          profileUrl: me.steam.profile_url,
          onDisconnect: onDisconnectSteam,
        },
      ]
    : [];

  if (pane === SETTINGS_PANES.NICKNAME && me.handle) {
    return (
      <NicknameForm
        locale={locale}
        handle={me.handle}
        onBack={() => setPane(SETTINGS_PANES.ROOT)}
        onSubmit={async (value) => {
          await onNickname(value);
          setPane(SETTINGS_PANES.ROOT);
        }}
      />
    );
  }

  if (pane === SETTINGS_PANES.PRIVACY) {
    return (
      <PrivacyPane
        locale={locale}
        data={data}
        onBack={() => setPane(SETTINGS_PANES.ROOT)}
        onFlash={onFlash}
      />
    );
  }

  if (pane === SETTINGS_PANES.PUBLISHING) {
    // One switch per game account (#20): a muted account still counts in stats.
    const accountSwitches: Array<{
      key: string;
      label: string;
      on: boolean;
      toggle: () => void;
    }> = [];
    if (me.xbox.linked) {
      accountSwitches.push({
        key: "xbox",
        label: `XBOX: ${me.xbox.gamertag_modern || me.xbox.gamertag || ""}`,
        on: me.xbox.publishes !== false,
        toggle: () => onAccountPublishes("xbox", me.xbox.publishes === false),
      });
    }
    if (me.psn.linked) {
      for (const account of me.psn.accounts ?? [
        {
          account_id: me.psn.account_id,
          name: me.psn.online_id || me.psn.account_id,
          publishes: me.psn.publishes !== false,
        },
      ]) {
        accountSwitches.push({
          key: `psn-${account.account_id}`,
          label: `PSN: ${account.name}`,
          on: account.publishes !== false,
          toggle: () => onAccountPublishes("psn", account.publishes === false, account.account_id),
        });
      }
    }
    const steam = me.steam;
    if (steam.linked) {
      accountSwitches.push({
        key: "steam",
        label: `Steam: ${steam.display_name || steam.steam_id}`,
        on: steam.publishes !== false,
        toggle: () => onAccountPublishes("steam", steam.publishes === false),
      });
    }
    return (
      <>
        <BackHead
          title={t(locale, "publishing")}
          backLabel={t(locale, "back")}
          onBack={() => setPane(SETTINGS_PANES.ROOT)}
        />
        <p className="settings-hint">{t(locale, "publishingHint")}</p>
        <div className="glass-card">
          {/* One mode for every chat this person publishes to (#126). */}
          <label className="ios-row">
            <span>{t(locale, "rarity")}</span>
            <select
              className="tz-select"
              value={me.settings.rarity_mode ?? RARITY_MODES.ALL}
              onChange={(e) => onPatch({ rarity_mode: e.target.value })}
            >
              <option value={RARITY_MODES.ALL}>{rarityLabel(RARITY_MODES.ALL, locale)}</option>
              <option value={RARITY_MODES.RARE}>{rarityLabel(RARITY_MODES.RARE, locale)}</option>
              <option value={RARITY_MODES.HIDDEN}>
                {rarityLabel(RARITY_MODES.HIDDEN, locale)}
              </option>
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
        </div>

        <p className="kicker">{t(locale, "publishingChats")}</p>
        {me.chats.length === 0 ? (
          <p className="empty">{t(locale, "noChats")}</p>
        ) : (
          <div className="glass-card">
            {me.chats.map((chat) => (
              <div key={chat.chat_id} className="ios-row">
                <span>{chat.title || String(chat.chat_id)}</span>
                <Toggle
                  on={chat.is_subscribed}
                  label={chat.title || String(chat.chat_id)}
                  onClick={() => {
                    // Turning it off silences the chat for this person, so ask first.
                    if (
                      chat.is_subscribed &&
                      !window.confirm(
                        `${chat.title || chat.chat_id}\n\n${t(locale, "confirmUnsubscribe")}`,
                      )
                    ) {
                      return;
                    }
                    onChatPatch(chat.chat_id, {
                      action: chat.is_subscribed ? "unsubscribe" : "subscribe",
                    });
                  }}
                />
              </div>
            ))}
          </div>
        )}

        {accountSwitches.length > 0 && (
          <>
            <p className="kicker">{t(locale, "publishingAccounts")}</p>
            <div className="glass-card">
              {accountSwitches.map((item) => (
                <div key={item.key} className="ios-row">
                  <span>{item.label}</span>
                  <Toggle on={item.on} label={item.label} onClick={item.toggle} />
                </div>
              ))}
            </div>
          </>
        )}
      </>
    );
  }

  return (
    <>
      <header className="page-head is-split">
        <h1>{t(locale, "settings")}</h1>
        {me.handle && <span className="page-sub">{me.handle.display}</span>}
      </header>

      <p className="kicker">{t(locale, "general")}</p>
      <div className="glass-card">
        {me.handle && (
          <button
            type="button"
            className="ios-row"
            onClick={() => setPane(SETTINGS_PANES.NICKNAME)}
          >
            <span>{t(locale, "nickname")}</span>
            <span className="ios-value">
              {me.handle.display}
              <Chevron />
            </span>
          </button>
        )}
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
          onClick={() => setPane(SETTINGS_PANES.PUBLISHING)}
        >
          <span>{t(locale, "publishing")}</span>
          <span className="ios-value">
            {me.chats.filter((c) => c.is_subscribed).length || "—"}
            <Chevron />
          </span>
        </button>
        <button
          type="button"
          className="ios-row"
          onClick={() => setPane(SETTINGS_PANES.PRIVACY)}
        >
          <span>{t(locale, "privacy")}</span>
          <span className="ios-value">
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
              if (window.Telegram?.WebApp?.close) window.Telegram.WebApp.close();
              else window.location.reload();
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
        mark={PLATFORMS.XBOX}
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
        mark={PLATFORMS.PSN}
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
          psnHidden ? { kind: "warn", text: t(locale, "hiddenPsn") } : null,
          notes?.psn,
        ]}
      />

      <PlatformCard
        mark={PLATFORMS.STEAM}
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

      {onLogout && (
        <div className="glass-card">
          <button type="button" className="ios-row danger" onClick={onLogout}>
            <span>{t(locale, "logout")}</span>
          </button>
        </div>
      )}

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
