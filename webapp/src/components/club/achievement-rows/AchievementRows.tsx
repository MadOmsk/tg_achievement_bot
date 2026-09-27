import type { FeedItem } from "../../../api";
import { FeedRow, feedKey, veiled } from "../../person";

/**
 * Achievements as the same plates the profile's compact list uses — the
 * body of the stats drawers. A secret one keeps its game and rarity and
 * blurs the rest until it is revealed.
 */
export function AchievementRows({
  items,
  revealed,
  showSecrets,
  detailed = false,
  onOpen,
}: {
  items: FeedItem[];
  revealed: Set<string>;
  showSecrets?: boolean;
  detailed?: boolean;
  onOpen: (row: FeedItem) => void;
}) {
  return (
    <div className="feed-day">
      {items.map((row) => (
        <FeedRow
          key={feedKey(row)}
          row={row}
          secret={veiled(row, feedKey(row), revealed, showSecrets)}
          detailed={detailed}
          onOpen={onOpen}
        />
      ))}
    </div>
  );
}
