import type { ReactNode } from "react";
import type { FeedItem, PersonPayload } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { Avatar, EmptyState, Icon, isOnline } from "../../shared/lib";
import { GamesSection } from "../games-section/GamesSection";
import { RecentPosts } from "../recent-posts/RecentPosts";
import { HandleName } from "../../shared/lib/handle-name/HandleName";

export function PersonProfile({
  person,
  status,
  locale,
  revealed,
  showSecrets,
  loadMonth,
  aside,
  onBack,
  onOpenCard,
  onReveal,
  people,
}: {
  person: PersonPayload;
  /** What they are doing now ("В сети", "3 ч назад", the game), shown after the nick. */
  status?: string | null;
  locale: Locale;
  revealed: Set<string>;
  showSecrets?: boolean;
  /** Their achievements in a past month, for the games block's own pick. */
  loadMonth: (month: string) => Promise<FeedItem[]>;
  /** At the head's right: the follow control, for somebody else. */
  aside?: ReactNode;
  onBack: () => void;
  /** The nickname in the bar opens the person's card. */
  onOpenCard?: () => void;
  onReveal: (key: string) => void;
  /** Whom they follow, as on Home: a strip under the gallery. */
  people?: ReactNode;
}) {
  const feed = person.feed ?? [];
  const months = person.months ?? [];
  const live = isOnline(person.presence ?? {});
  const playing = Boolean(person.presence?.playing);
  return (
    <>
      <header className="account-bar person-bar">
        <div className="account-top">
          <button
            type="button"
            className="person-back"
            onClick={onBack}
            aria-label={t(locale, "back")}
          >
            <Icon name="back" size={26} />
          </button>
          <button
            type="button"
            className="account-who"
            onClick={onOpenCard}
          >
              <Avatar
                name={person.name}
                personId={person.person_id}
                size={48}
                zoomLabel={t(locale, "close")}
                online={live}
                playing={playing}
                platform={person.presence?.platform}
              />
            <span className="person-bar-title">
              <span className="account-name-row">
                <strong>
                  <HandleName text={person.name} />
                </strong>
              </span>
              {status && <small>{status}</small>}
            </span>
          </button>
          {aside && <span className="person-bar-aside">{aside}</span>}
        </div>
      </header>
      {feed.length > 0 ? (
        <RecentPosts
          items={feed}
          locale={locale}
          revealed={revealed}
          showSecrets={showSecrets}
          onReveal={onReveal}
        />
      ) : (
        <EmptyState
          title={t(locale, "emptyPersonTitle")}
          hint={t(locale, "emptyFeedHint")}
          slide
        />
      )}
      {people}
      {(feed.length > 0 || months.length > 0) && (
        <GamesSection items={feed} months={months} locale={locale} load={loadMonth} />
      )}
    </>
  );
}
