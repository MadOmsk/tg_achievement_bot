import type { MeResponse } from "../../api";
import { t, type Locale } from "../../i18n";
import { PLATFORMS } from "../../components/shared/constants";
import { PlatformCard, type PlatNotes } from "../../components/me";

export {
  PlatformCard,
  Settings,
  ConnectForm,
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
  const xboxName =
    me.xbox.gamertag_modern || me.xbox.gamertag || t(locale, "notLinked");

  return (
    <>
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
    </>
  );
}
