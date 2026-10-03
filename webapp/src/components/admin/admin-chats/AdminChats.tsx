import { useEffect, useState } from "react";
import { fetchAdminChats, type AdminChatRow } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { BackHead, Group, NavRow, SettingsSkel } from "../../shared/lib";

export function AdminChats({
  data,
  locale,
  onSelectChat,
  onBack,
  onFail,
}: {
  data: string;
  locale: Locale;
  onSelectChat: (chatId: number) => void;
  onBack: () => void;
  onFail: (err: unknown) => void;
}) {
  const [chats, setChats] = useState<AdminChatRow[] | null>(null);

  useEffect(() => {
    void fetchAdminChats(data)
      .then((r) => setChats(r.chats))
      .catch(onFail);
  }, [data, onFail]);

  return (
    <>
      <BackHead title={t(locale, "adminChats")} backLabel={t(locale, "back")} onBack={onBack} />
      {chats == null ? (
        <SettingsSkel groups={[3]} />
      ) : chats.length === 0 ? (
        <p className="empty">{t(locale, "noChats")}</p>
      ) : (
        <Group>
          {chats.map((row) => (
            <NavRow
              key={row.chat_id}
              label={row.title || String(row.chat_id)}
              sub={`${row.subscribers} ${t(locale, "subscribers")}`}
              value={row.is_active ? t(locale, "on") : t(locale, "off")}
              onClick={() => onSelectChat(row.chat_id)}
            />
          ))}
        </Group>
      )}
    </>
  );
}
