import type { FeedItem } from "../../../api";
import type { Locale } from "../../../i18n";
import "./RecentPosts.css";
import { UnlockSlider } from "../unlock-slider/UnlockSlider";

const RECENT = 5;

/**
 * A person's last few achievements as a gallery across the full width of the
 * page — square edges, the achievement's picture stretched over the whole
 * block, the newest first. Their name is left off: the page is theirs already.
 */
export function RecentPosts({
  items,
  locale,
  revealed,
  showSecrets,
  onReveal,
}: {
  items: FeedItem[];
  locale: Locale;
  revealed: Set<string>;
  showSecrets?: boolean;
  onReveal: (key: string) => void;
}) {
  if (items.length === 0) return null;
  return (
    <div className="person-stage">
      <UnlockSlider
        items={items.slice(0, RECENT)}
        locale={locale}
        revealed={revealed}
        showSecrets={showSecrets}
        onReveal={onReveal}
        variant="hero"
        author={false}
        minimal
      />
    </div>
  );
}
