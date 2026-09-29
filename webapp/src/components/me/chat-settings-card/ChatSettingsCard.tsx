import type { ChatRow } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { Toggle } from "../../shared/lib";

export function ChatSettingsCard({
  chat,
  locale,
  onPatch,
}: {
  chat: ChatRow;
  locale: Locale;
  onPatch: (chatId: number, body: Record<string, unknown>) => void;
}) {
  return (
    <div className="glass-card chat-settings-card">
      <p className="chat-settings-title">{chat.title || String(chat.chat_id)}</p>
      <div className="ios-row">
        <span>{t(locale, "subscribe")}</span>
        <Toggle
          on={chat.is_subscribed}
          label={t(locale, "subscribe")}
          onClick={() => {
            // Turning it off silences the chat for this person, so ask first.
            if (
              chat.is_subscribed &&
              !window.confirm(
                `${chat.title || chat.chat_id}

${t(locale, "confirmUnsubscribe")}`,
              )
            ) {
              return;
            }
            onPatch(chat.chat_id, {
              action: chat.is_subscribed ? "unsubscribe" : "subscribe",
            });
          }}
        />
      </div>
    </div>
  );
}
