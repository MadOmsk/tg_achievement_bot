import { useState, type ReactNode } from "react";
import type { PersonPayload } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { Avatar, EmptyState, Icon, isOnline } from "../../shared/lib";
import { PlayedGames } from "../played-games/PlayedGames";
import { RecentPosts } from "../recent-posts/RecentPosts";
import { HandleName } from "../../shared/lib/handle-name/HandleName";

export function PersonProfile({
  person,
  status,
  locale,
  revealed,
  showSecrets,
  monthChip,
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
  monthChip?: ReactNode;
  onBack: () => void;
  /** The nickname in the bar opens the person's card. */
  onOpenCard?: () => void;
  onReveal: (key: string) => void;
  /** Whom they follow, as on Home: a strip under the gallery. */
  people?: ReactNode;
}) {
  const [gameSort, setGameSort] = useState<"recent" | "progress">("recent");
  const feed = person.feed ?? [];
  const gameCount = new Set(
    feed.filter((row) => row.game).map((row) => `${row.platform}:${row.title_id}`),
  ).size;
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
          {monthChip}
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
      {feed.length > 0 && (
        <>
      <div className="section-head achievements-head">
        <span className="section-title-group">
          <h1 className="kicker" style={{ margin: 0 }}>
            {t(locale, "games")}
          </h1>
          {gameCount > 0 && <span className="section-count">{gameCount}</span>}
        </span>
        {gameCount > 1 && (
          <button
            type="button"
            className="sort-toggle"
            aria-label={t(locale, gameSort === "recent" ? "sortProgress" : "sortRecent")}
            onClick={() => setGameSort((cur) => (cur === "recent" ? "progress" : "recent"))}
          >
            <Icon name={gameSort === "recent" ? "sort" : "stats"} size={18} />
          </button>
        )}
      </div>
      <PlayedGames items={feed} locale={locale} sort={gameSort} />
        </>
      )}
    </>
  );
}
