import { useEffect, useState } from "react";
import { fetchAdminUser, type AdminUserCard as AdminUserCardType } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { BackHead, Group, InfoRow, PlatformLogo, SettingsSkel } from "../../shared/lib";
import { ADMIN_USER_PLATFORMS, PLATFORMS } from "../../shared/constants";
import { AdminActions } from "../admin-actions/AdminActions";

const LABEL = { xbox: "platformXbox", psn: "platformPsn", steam: "platformSteam" } as const;
const MARK = { xbox: PLATFORMS.XBOX, psn: PLATFORMS.PSN, steam: PLATFORMS.STEAM } as const;

export function AdminUserDetail({
  data,
  personId,
  locale,
  onBack,
  onFlash,
  onFail,
}: {
  data: string;
  personId: number;
  locale: Locale;
  onBack: () => void;
  onFlash: (message: string) => void;
  onFail: (err: unknown) => void;
}) {
  const [user, setUser] = useState<AdminUserCardType | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    void fetchAdminUser(data, personId).then(setUser).catch(onFail);
  }, [data, onFail, personId, version]);

  const linked = user ? ADMIN_USER_PLATFORMS.filter((p) => user[p]) : [];

  return (
    <>
      <BackHead
        title={user?.name ?? t(locale, "adminUsers")}
        backLabel={t(locale, "back")}
        onBack={onBack}
      />
      {user == null ? (
        <SettingsSkel groups={[2, 4, 2, 2]} />
      ) : (
        <>
          <Group title={t(locale, "adminLoginsGroup")}>
            {user.logins.map((login) => (
              <InfoRow key={login.kind} label={login.label} value={login.value ?? "—"} />
            ))}
          </Group>

          <Group title={t(locale, "groupInfo")}>
            <InfoRow label="ID" value={String(user.person_id)} />
            {linked.map((p) => (
              <InfoRow
                key={p}
                lead={<PlatformLogo platform={MARK[p]} size={18} />}
                label={t(locale, LABEL[p])}
                value={String(user[p]?.name ?? "—")}
              />
            ))}
            <InfoRow
              label={t(locale, "myChats")}
              value={user.chats.join(", ") || t(locale, "notSubscribed")}
            />
          </Group>

          {user.is_excluded && (
            <Group>
              <InfoRow label={t(locale, "excluded")} value="🚫" />
            </Group>
          )}

          {/* The registry's actions (#176) — the bot's card offers the same. */}
          <AdminActions
            data={data}
            scope="user"
            target={`p${personId}`}
            reloadKey={version}
            onFlash={onFlash}
            onFail={onFail}
            onDone={(done) => (done.gone ? onBack() : setVersion((v) => v + 1))}
          />
        </>
      )}
    </>
  );
}
