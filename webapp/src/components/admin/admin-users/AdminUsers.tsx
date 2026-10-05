import { useEffect, useState } from "react";
import { fetchAdminUsers, type AdminUserRow } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { BackHead, Group, NavRow, PlatformLogo, SelectRow, SettingsSkel } from "../../shared/lib";
import { PLATFORMS } from "../../shared/constants";

export function AdminUsers({
  data,
  locale,
  onSelectUser,
  onBack,
  onFail,
}: {
  data: string;
  locale: Locale;
  onSelectUser: (tgId: number) => void;
  onBack: () => void;
  onFail: (err: unknown) => void;
}) {
  const [users, setUsers] = useState<AdminUserRow[] | null>(null);
  const [chats, setChats] = useState<Array<{ chat_id: number; title: string | null }>>([]);
  const [chat, setChat] = useState<number>(0);

  useEffect(() => {
    void fetchAdminUsers(data)
      .then((r) => {
        setUsers(r.users);
        setChats(r.chats ?? []);
      })
      .catch(onFail);
  }, [data, onFail]);

  const shown =
    users?.filter((row) => chat === 0 || (row.chat_ids ?? []).includes(chat)) ?? [];

  return (
    <>
      <BackHead title={t(locale, "adminUsers")} backLabel={t(locale, "back")} onBack={onBack} />
      {users == null ? (
        <SettingsSkel groups={[1, 6]} />
      ) : (
        <>
          {chats.length > 0 && (
            <Group>
              <SelectRow
                label={t(locale, "adminChats")}
                value={chat}
                options={[
                  { value: 0, label: t(locale, "allChats") },
                  ...chats.map((c) => ({ value: c.chat_id, label: c.title || `chat ${c.chat_id}` })),
                ]}
                onChange={setChat}
              />
            </Group>
          )}
          {shown.length === 0 ? (
            <p className="empty">{t(locale, "noUsers")}</p>
          ) : (
            <Group>
              {shown.map((row) => (
                <NavRow
                  key={row.tg_id}
                  label={row.name}
                  sub={[
                    `${t(locale, "usersToday")} ${row.today}`,
                    `${t(locale, "usersMonth")} ${row.month}`,
                    row.is_excluded ? t(locale, "excluded") : "",
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                  value={
                    <span className="fr-marks">
                      {row.xbox && <PlatformLogo platform={PLATFORMS.XBOX} size={16} />}
                      {row.psn && <PlatformLogo platform={PLATFORMS.PSN} size={16} />}
                      {row.steam && <PlatformLogo platform={PLATFORMS.STEAM} size={16} />}
                    </span>
                  }
                  onClick={() => onSelectUser(row.tg_id)}
                />
              ))}
            </Group>
          )}
        </>
      )}
    </>
  );
}
