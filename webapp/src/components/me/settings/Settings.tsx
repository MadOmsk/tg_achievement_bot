import { useState } from "react";
import type { AccountPlatform, MeResponse } from "../../../api";
import { t, timezoneLabel, type Locale } from "../../../i18n";
import {
  BackHead,
  ChoiceRow,
  Group,
  InfoRow,
  NavRow,
  PlatformLogo,
  SelectRow,
  ToggleRow,
} from "../../shared/lib";
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
    notify_followers?: boolean;
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
        name: account.name,
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

  const back = () => setPane(SETTINGS_PANES.ROOT);
  // Said as what goes to the chats, not as a rarity: "everything", "only rare", "nothing".
  const publishOptions = [
    { value: RARITY_MODES.ALL as string, label: t(locale, "publishAll") },
    { value: RARITY_MODES.RARE as string, label: t(locale, "publishRare") },
    { value: RARITY_MODES.HIDDEN as string, label: t(locale, "publishNone") },
  ];
  // A sentinel for "no timezone set": a select's options are all of one type.
  const TZ_UNSET = -100000;
  const tzOptions = [
    { value: TZ_UNSET, label: t(locale, "tzUnset") },
    ...TIMEZONES.map((z) => ({ value: z.min, label: timezoneLabel(z, locale) })),
  ];

  if (pane === SETTINGS_PANES.NICKNAME && me.handle) {
    return (
      <NicknameForm
        locale={locale}
        handle={me.handle}
        onBack={back}
        onSubmit={async (value) => {
          await onNickname(value);
          back();
        }}
      />
    );
  }

  if (pane === SETTINGS_PANES.NOTIFICATIONS) {
    return (
      <>
        <BackHead title={t(locale, "notifications")} backLabel={t(locale, "back")} onBack={back} />
        <Group>
          <ToggleRow
            label={t(locale, "notifyFollowers")}
            sub={t(locale, "notifyFollowersHint")}
            on={me.settings.notify_followers !== false}
            onChange={(on) => onPatch({ notify_followers: on })}
          />
        </Group>
      </>
    );
  }

  if (pane === SETTINGS_PANES.PRIVACY) {
    return (
      <PrivacyPane
        locale={locale}
        data={data}
        initial={me.settings.activity_visible ?? "all"}
        onBack={back}
        onFlash={onFlash}
      />
    );
  }

  if (pane === SETTINGS_PANES.PUBLISHING) {
    // One switch per game account (#20): a muted account still counts in stats.
    const accountSwitches: Array<{ key: string; mark: string; label: string; on: boolean; toggle: () => void }> = [];
    if (me.xbox.linked) {
      accountSwitches.push({
        key: "xbox",
        mark: PLATFORMS.XBOX,
        label: me.xbox.gamertag_modern || me.xbox.gamertag || "Xbox",
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
          mark: PLATFORMS.PSN,
          label: account.name,
          on: account.publishes !== false,
          toggle: () => onAccountPublishes("psn", account.publishes === false, account.account_id),
        });
      }
    }
    const steam = me.steam;
    if (steam.linked) {
      accountSwitches.push({
        key: "steam",
        mark: PLATFORMS.STEAM,
        label: steam.display_name || steam.steam_id,
        on: steam.publishes !== false,
        toggle: () => onAccountPublishes("steam", steam.publishes === false),
      });
    }
    return (
      <>
        <BackHead title={t(locale, "publishing")} backLabel={t(locale, "back")} onBack={back} />
        {/* First what the app shows you; then what goes to the chats: what,
            where, from which accounts — one question per group. */}
        <Group>
          <ToggleRow
            label={t(locale, "showSecrets")}
            on={me.settings.show_secrets}
            onChange={(on) => onPatch({ show_secrets: on })}
          />
        </Group>
        <Group title={t(locale, "publishingWhat")}>
          {/* One mode for every chat this person publishes to (#126). */}
          <SelectRow
            label={t(locale, "publishingWhich")}
            sub={t(locale, "publishingWhatHint")}
            value={me.settings.rarity_mode ?? RARITY_MODES.ALL}
            options={publishOptions}
            onChange={(v) => onPatch({ rarity_mode: v })}
          />
        </Group>

        <Group title={t(locale, "publishingWhere")}>
          {me.chats.length === 0 ? (
            <InfoRow label={t(locale, "noChatsShort")} />
          ) : (
            me.chats.map((chat) => (
              <ToggleRow
                key={chat.chat_id}
                label={chat.title || String(chat.chat_id)}
                on={chat.is_subscribed}
                onChange={() => {
                  // Turning it off silences the chat for this person, so ask first.
                  if (
                    chat.is_subscribed &&
                    !window.confirm(`${chat.title || chat.chat_id}\n\n${t(locale, "confirmUnsubscribe")}`)
                  ) {
                    return;
                  }
                  onChatPatch(chat.chat_id, { action: chat.is_subscribed ? "unsubscribe" : "subscribe" });
                }}
              />
            ))
          )}
        </Group>

        {accountSwitches.length > 0 && (
          <Group title={t(locale, "publishingFrom")}>
            {accountSwitches.map((item) => (
              <ToggleRow
                key={item.key}
                lead={<PlatformLogo platform={item.mark} size={20} />}
                label={item.label}
                on={item.on}
                onChange={item.toggle}
              />
            ))}
          </Group>
        )}
      </>
    );
  }

  return (
    <>
      <header className="page-head">
        <h1>{t(locale, "settings")}</h1>
      </header>

      <Group title={t(locale, "groupProfile")}>
        {me.handle && (
          <NavRow
            label={t(locale, "nickname")}
            value={me.handle.display}
            onClick={() => setPane(SETTINGS_PANES.NICKNAME)}
          />
        )}
        <NavRow label={t(locale, "privacy")} onClick={() => setPane(SETTINGS_PANES.PRIVACY)} />
        <NavRow
          label={t(locale, "notifications")}
          onClick={() => setPane(SETTINGS_PANES.NOTIFICATIONS)}
        />
        <NavRow
          label={t(locale, "publishing")}
          value={me.chats.filter((c) => c.is_subscribed).length || undefined}
          onClick={() => setPane(SETTINGS_PANES.PUBLISHING)}
        />
      </Group>

      <Group title={t(locale, "groupGeneral")}>
        <ChoiceRow
          label={t(locale, "language")}
          value={locale}
          options={[
            { value: "ru", label: "RU" },
            { value: "en", label: "EN" },
          ]}
          onChange={(v) => onPatch({ locale: v as Locale })}
        />
        <SelectRow
          label={t(locale, "timezone")}
          value={tz ?? TZ_UNSET}
          options={tzOptions}
          onChange={(v) => onPatch({ tz_offset_min: v === TZ_UNSET ? null : v })}
        />
      </Group>

      <Group title={t(locale, "accounts")}>
        <PlatformCard
          mark={PLATFORMS.XBOX}
          title="Xbox"
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
          title="PlayStation"
          accounts={psnAccounts}
          locale={locale}
          onConnect={onConnectPsn}
          onAdd={psnAccounts.length && psnAccounts.length < psnMax ? onConnectPsn : undefined}
          onSync={me.psn.linked ? onSync : undefined}
          notes={[psnHidden ? { kind: "warn", text: t(locale, "hiddenPsn") } : null, notes?.psn]}
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
      </Group>

      {me.is_admin && onAdmin && (
        <AdminSection
          data={data}
          locale={locale}
          onNavigate={onAdmin}
          onFail={(err) => onFlash(`${t(locale, "error")}: ${String(err)}`)}
        />
      )}

      <Group>
        {onLogout && <NavRow danger label={t(locale, "logout")} onClick={onLogout} />}
        <NavRow
          danger
          disabled={deleting}
          label={t(locale, "deleteAccount")}
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
        />
      </Group>
    </>
  );
}
