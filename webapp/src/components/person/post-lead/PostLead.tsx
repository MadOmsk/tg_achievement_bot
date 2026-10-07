import type { FeedItem } from "../../../api";
import { timeAgo, type Locale } from "../../../i18n";
import { Avatar } from "../../shared/lib";
import { HeroGame } from "../hero-game/HeroGame";
import { HandleName } from "../../shared/lib/handle-name/HandleName";

export function PostLead({
  item,
  locale,
  onOpenPerson,
  whoOnly = false,
}: {
  item: FeedItem;
  locale: Locale;
  onOpenPerson?: (personId: number) => void;
  whoOnly?: boolean;
}) {
  return (
    <span className="feed-post-lead">
      <button
        type="button"
        className="feed-post-who"
        onClick={(e) => {
          e.stopPropagation();
          onOpenPerson?.(item.person_id);
        }}
      >
        <Avatar name={item.person} personId={item.person_id} size={36} />
        <span>
          <strong>
            <HandleName text={item.person} />
          </strong>
          <p>{timeAgo(item.unlocked_at, locale)}</p>
        </span>
      </button>
      {!whoOnly && <HeroGame item={item} locale={locale} />}
    </span>
  );
}
