import type { MeResponse } from "../../api";
import { t, type Locale } from "../../i18n";
import { PLATFORMS } from "../../components/shared/constants";
import { PlatformCard, type PlatNotes } from "../../components/me";

export {
  PlatformCard,
  Settings,
  ConnectForm,
  type AccountRow,
  type PlatNote,
  type PlatNotes,
} from "../../components/me";

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
  const xboxAccounts = me.xbox.linked
    ? [
        {
          key: "xbox",
          name: me.xbox.gamertag_modern || me.xbox.gamertag || t(locale, "notLinked"),
          profileUrl: me.xbox.profile_url,
          onDisconnect: onDisconnectXbox,
        },
      ]
    : [];

  const psnAccounts = !me.psn.linked
    ? []
    : (me.psn.accounts ?? [
        {
          account_id: me.psn.account_id,
          name: me.psn.online_id || me.psn.account_id,
          profile_url: me.psn.profile_url,
          publishes: true,
          trophy_count: 0,
          platinum_count: 0,
          trophy_level: null,
          visibility: "public",
          achievements_visible: true,
          online_id: me.psn.online_id,
        },
      ]).map((account) => ({
        key: account.account_id,
        name: `PSN: ${account.name}`,
        profileUrl: account.profile_url,
        onDisconnect: onDisconnectPsn,
      }));

  const steamAccounts = me.steam.linked
    ? [
        {
          key: "steam",
          name: me.steam.display_name || me.steam.steam_id,
          profileUrl: me.steam.profile_url,
          onDisconnect: onDisconnectSteam,
        },
      ]
    : [];

  return (
    <>
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
        title="PSN"
        accounts={psnAccounts}
        locale={locale}
        onConnect={onConnectPsn}
        onSync={me.psn.linked ? onSync : undefined}
        notes={[
          me.psn.linked && me.psn.achievements_visible === false
            ? { kind: "warn", text: t(locale, "hiddenPsn") }
            : null,
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
    </>
  );
}
