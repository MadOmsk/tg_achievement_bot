import type { ReactNode } from "react";
import type { PersonPayload } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { Avatar, Icon, ScoreCup, isOnline } from "../../shared/lib";
import {
  COMPLETION_BADGES,
  PLATFORMS,
} from "../../shared/constants";
import { PlayedGames } from "../played-games/PlayedGames";
import { RecentPosts } from "../recent-posts/RecentPosts";

export function PersonProfile({
  person,
  status,
  locale,
  revealed,
  showSecrets,
  monthChip,
  onBack,
  onReveal,
}: {
  person: PersonPayload;
  /** What they are doing now ("В сети", "3 ч назад", the game), shown after the nick. */
  status?: string | null;
  locale: Locale;
  revealed: Set<string>;
  showSecrets?: boolean;
  monthChip?: ReactNode;
  onBack: () => void;
  onReveal: (key: string) => void;
}) {
  const feed = person.feed ?? [];
  const scoreLines = (person.platforms ?? []).flatMap((p) => {
    const xbox = p.platform.startsWith(PLATFORMS.XBOX);
    const count =
      xbox && p.gamerscore != null
        ? p.gamerscore
        : p.achievement_count ?? p.trophy_count;
    if (count == null) return [];
    const extra = xbox
      ? p.completed_games
        ? `${COMPLETION_BADGES.XBOX} ${p.completed_games}`
        : null
      : p.trophy_level != null
        ? `${t(locale, "level")} ${p.trophy_level}`
        : p.completed_games
          ? `${COMPLETION_BADGES.STEAM} ${p.completed_games}`
          : p.platinum_count
            ? `${COMPLETION_BADGES.PSN} ${p.platinum_count}`
            : null;
    const key = xbox
      ? PLATFORMS.XBOX
      : p.platform === PLATFORMS.STEAM
        ? PLATFORMS.STEAM
        : PLATFORMS.PSN;
    const tiers =
      key === PLATFORMS.PSN && p.bronze != null
        ? {
            bronze: p.bronze,
            silver: p.silver ?? 0,
            gold: p.gold ?? 0,
            platinum: p.platinum_count ?? 0,
          }
        : null;
    return [
      {
        platform: p.platform,
        count,
        extra,
        unit: xbox && p.gamerscore != null ? "G" : null,
        day: person.today?.[key] ?? 0,
        month: person.month?.[key] ?? 0,
        tiers,
      },
    ];
  });
  const live = isOnline(person.presence ?? {});
  const playing = Boolean(person.presence?.playing);
  return (
    <>
      <header className="account-bar person-bar">
        <div className="account-top">
          <div className="account-who">
            <button
              type="button"
              className="person-back"
              onClick={onBack}
              aria-label={t(locale, "back")}
            >
              <Icon name="back" size={28} />
            </button>
            <Avatar
              name={person.name}
              tgId={person.tg_id}
              size={48}
              zoomLabel={t(locale, "close")}
              online={live}
              playing={playing}
              platform={person.presence?.platform}
            />
            <span className="person-bar-title">
              <strong>{person.name}</strong>
              {status && <small>{status}</small>}
            </span>
          </div>
          <ScoreCup locale={locale} lines={scoreLines} />
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
        <p className="empty">{t(locale, "emptyFeed")}</p>
      )}
      <div className="section-head achievements-head">
        <h1 className="kicker" style={{ margin: 0 }}>
          {t(locale, "games")}
        </h1>
        {monthChip}
      </div>
      {(feed.length > 0) && (
        <PlayedGames items={feed} locale={locale} />
      )}
    </>
  );
}
