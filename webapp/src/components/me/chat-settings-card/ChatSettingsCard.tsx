import type { ChatRow } from "../../../api";
import { digestLabel, rarityLabel, t, type Locale } from "../../../i18n";
import { Toggle } from "../../shared/lib";
import { DIGEST_CHOICES, RARITY_MODES } from "../../shared/constants";

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
      {chat.is_subscribed && (
        <>
          <label className="ios-row">
            <span>{t(locale, "rarity")}</span>
            <select
              className="tz-select"
              value={chat.rarity_mode ?? RARITY_MODES.ALL}
              onChange={(e) =>
                onPatch(chat.chat_id, { rarity_mode: e.target.value })
              }
            >
              <option value={RARITY_MODES.ALL}>{rarityLabel(RARITY_MODES.ALL, locale)}</option>
              <option value={RARITY_MODES.RARE}>{rarityLabel(RARITY_MODES.RARE, locale)}</option>
              <option value={RARITY_MODES.HIDDEN}>{rarityLabel(RARITY_MODES.HIDDEN, locale)}</option>
            </select>
          </label>
          <label className="ios-row">
            <span>{t(locale, "digest")}</span>
            <select
              className="tz-select"
              value={chat.digest_threshold ?? 3}
              onChange={(e) =>
                onPatch(chat.chat_id, {
                  digest_threshold: Number(e.target.value),
                })
              }
            >
              {DIGEST_CHOICES.map((n) => (
                <option key={n} value={n}>
                  {digestLabel(n, locale)}
                </option>
              ))}
            </select>
          </label>
        </>
      )}
    </div>
  );
}
