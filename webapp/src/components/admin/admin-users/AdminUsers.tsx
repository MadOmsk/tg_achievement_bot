import { useEffect, useState } from "react";
import { fetchAdminUsers, type AdminUserRow } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { BackHead, GlassWait, PlatformLogo, Chevron } from "../../shared/lib";
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
  const [userChats, setUserChats] = useState<
    Array<{ chat_id: number; title: string | null }>
  >([]);
  const [peopleChat, setPeopleChat] = useState("");

  useEffect(() => {
    void fetchAdminUsers(data)
      .then((r) => {
        setUsers(r.users);
        setUserChats(r.chats ?? []);
      })
      .catch(onFail);
  }, [data, onFail]);

  const filteredUsers =
    users?.filter((row) =>
      peopleChat === ""
        ? true
        : (row.chat_ids ?? []).includes(Number(peopleChat)),
    ) ?? [];

  return (
    <>
      <BackHead
        title={t(locale, "adminUsers")}
        backLabel={t(locale, "back")}
        onBack={onBack}
      />
      {users == null ? (
        <GlassWait />
      ) : (
        <>
          {(userChats.length > 0) && (
            <div className="glass-card">
              <label className="ios-row">
                <span>{t(locale, "adminChats")}</span>
                <select
                  className="tz-select"
                  value={peopleChat}
                  onChange={(e) => setPeopleChat(e.target.value)}
                  aria-label={t(locale, "adminChats")}
                >
                  <option value="">{t(locale, "allChats")}</option>
                  {userChats.map((c) => (
                    <option key={c.chat_id} value={c.chat_id}>
                      {c.title || `chat ${c.chat_id}`}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          )}

          {filteredUsers.length === 0 ? (
            <p className="empty">{t(locale, "noUsers")}</p>
          ) : (
            <div className="glass-card">
              {filteredUsers.map((row) => (
                <button
                  key={row.tg_id}
                  type="button"
                  className="ios-row admin-user-row"
                  onClick={() => onSelectUser(row.tg_id)}
                >
                  <span className="admin-limit-copy">
                    <strong>{row.name}</strong>
                    <small>
                      {row.today} / {row.month}
                      {row.is_excluded ? ` · ${t(locale, "excluded")}` : ""}
                    </small>
                  </span>
                  <span className="admin-plats">
                    {row.xbox && (
                      <PlatformLogo platform={PLATFORMS.XBOX} size={18} />
                    )}
                    {row.psn && (
                      <PlatformLogo platform={PLATFORMS.PSN} size={18} />
                    )}
                    {row.steam && (
                      <PlatformLogo platform={PLATFORMS.STEAM} size={18} />
                    )}
                    <span className="ios-value">
                      <Chevron />
                    </span>
                  </span>
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </>
  );
}
