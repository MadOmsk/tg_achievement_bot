import { useEffect, useState } from "react";
import { fetchAdminChats, type AdminChatRow } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { BackHead, GlassWait, Chevron } from "../../shared/lib";

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
      <BackHead
        title={t(locale, "adminChats")}
        backLabel={t(locale, "back")}
        onBack={onBack}
      />
      {chats == null ? (
        <GlassWait />
      ) : chats.length === 0 ? (
        <p className="empty">{t(locale, "noChats")}</p>
      ) : (
        <div className="glass-card">
          {chats.map((row) => (
            <button
              key={row.chat_id}
              type="button"
              className={`ios-row admin-user-row${row.is_active ? "" : " is-off"}`}
              onClick={() => onSelectChat(row.chat_id)}
            >
              <span className="admin-limit-copy">
                <strong>{row.title || row.chat_id}</strong>
                <small>
                  {row.subscribers} {t(locale, "subscribers")} ·{" "}
                  {row.rare_threshold_percent}%
                </small>
              </span>
              <span
                className={`admin-chat-state${row.is_active ? " is-on" : ""}`}
              >
                {row.is_active ? t(locale, "on") : t(locale, "off")}
              </span>
              <span className="ios-value">
                <Chevron />
              </span>
            </button>
          ))}
        </div>
      )}
    </>
  );
}
