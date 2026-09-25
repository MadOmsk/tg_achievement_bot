import type { ReactNode } from "react";
import type { PersonPayload } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { Avatar, Icon, ScoreCup, isOnline } from "../../shared/lib";
import {
  COMPLETION_BADGES,
  PLATFORMS,
  TROPHY_BADGES,
} from "../../shared/constants";
import { recentGames } from "../utils";
import { FeedList } from "../feed-list/FeedList";
import { UnlockSlider } from "../unlock-slider/UnlockSlider";

export function PersonProfile({
  person,
  locale,
  revealed,
  showSecrets,
  monthChip,
  onBack,
  onReveal,
}: {
  person: PersonPayload;
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
        ? `${TROPHY_BADGES.BRONZE} ${p.bronze} · ${TROPHY_BADGES.SILVER} ${p.silver ?? 0} · ${TROPHY_BADGES.GOLD} ${p.gold ?? 0} · ${TROPHY_BADGES.PLATINUM} ${p.platinum_count ?? 0}`
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
  const games = recentGames(feed);
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
            <span>
              <strong>{person.name}</strong>
            </span>
          </div>
          <ScoreCup locale={locale} lines={scoreLines} />
        </div>
      </header>
      <div className="person-stage">
        {games.length > 0 ? (
          <UnlockSlider items={games} locale={locale} variant="game" />
        ) : (
          <p className="empty">{t(locale, "emptyFeed")}</p>
        )}
      </div>
      <div className="section-head achievements-head">
        <h1 className="kicker" style={{ margin: 0 }}>
          {t(locale, "homeAchievements")}
        </h1>
        {monthChip}
      </div>
      {(feed.length > 0) && (
        <FeedList
          items={feed}
          locale={locale}
          revealed={revealed}
          showSecrets={showSecrets}
          onReveal={onReveal}
        />
      )}
    </>
  );
}
