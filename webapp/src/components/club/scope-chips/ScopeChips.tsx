import type { ChatRow } from "../../../api";
import { t, type Locale } from "../../../i18n";
import "./ScopeChips.css";

export type FeedScope = "following" | number;

/** What the Feed and the Ranking are about (#157): the people you follow, or one
 * of your chats. Plain text on a soft fill, no outlines, like the segment above. */
export function ScopeChips({
  locale,
  chats,
  value,
  onChange,
}: {
  locale: Locale;
  chats: ChatRow[];
  value: FeedScope;
  onChange: (scope: FeedScope) => void;
}) {
  return (
    <div className="scope-chips" role="group">
      <button
        type="button"
        className={value === "following" ? "is-on" : undefined}
        onClick={() => onChange("following")}
      >
        {t(locale, "peopleFollowing")}
      </button>
      {chats.map((chat) => (
        <button
          key={chat.chat_id}
          type="button"
          className={value === chat.chat_id ? "is-on" : undefined}
          onClick={() => onChange(chat.chat_id)}
        >
          {chat.title || String(chat.chat_id)}
        </button>
      ))}
    </div>
  );
}
