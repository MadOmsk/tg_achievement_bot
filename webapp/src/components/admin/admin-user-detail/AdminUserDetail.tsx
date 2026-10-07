import { useEffect, useState } from "react";
import { fetchAdminUser, patchAdminUser, type AdminUserCard as AdminUserCardType } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { BackHead, Group, InfoRow, NavRow, PlatformLogo, SettingsSkel } from "../../shared/lib";
import { ADMIN_USER_PLATFORMS, PLATFORMS } from "../../shared/constants";

const LABEL = { xbox: "platformXbox", psn: "platformPsn", steam: "platformSteam" } as const;
const MARK = { xbox: PLATFORMS.XBOX, psn: PLATFORMS.PSN, steam: PLATFORMS.STEAM } as const;

export function AdminUserDetail({
  data,
  personId,
  locale,
  onBack,
  onFail,
}: {
  data: string;
  personId: number;
  locale: Locale;
  onBack: () => void;
  onFail: (err: unknown) => void;
}) {
  const [user, setUser] = useState<AdminUserCardType | null>(null);

  useEffect(() => {
    void fetchAdminUser(data, personId).then(setUser).catch(onFail);
  }, [data, onFail, personId]);

  const linked = user ? ADMIN_USER_PLATFORMS.filter((p) => user[p]) : [];
  const patch = (body: Parameters<typeof patchAdminUser>[2]) =>
    user && void patchAdminUser(data, user.person_id, body).then(setUser).catch(onFail);

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

          {linked.length > 0 && (
            <Group title={t(locale, "groupRefreshData")}>
              {linked.map((p) => (
                <NavRow
                  key={p}
                  lead={<PlatformLogo platform={MARK[p]} size={18} />}
                  label={t(locale, LABEL[p])}
                  onClick={() => patch({ action: "sync", platform: p })}
                />
              ))}
            </Group>
          )}

          <Group>
            {linked.map((p) => (
              <NavRow
                key={p}
                danger
                label={`${t(locale, "reset")} ${t(locale, LABEL[p])}`}
                onClick={() => {
                  if (!window.confirm(t(locale, "confirmReset"))) return;
                  patch({ action: "reset", platform: p });
                }}
              />
            ))}
            <NavRow
              danger={!user.is_excluded}
              label={user.is_excluded ? t(locale, "restore") : t(locale, "exclude")}
              onClick={() => {
                if (!user.is_excluded && !window.confirm(t(locale, "confirmExclude"))) return;
                patch({ excluded: !user.is_excluded });
              }}
            />
          </Group>
        </>
      )}
    </>
  );
}
