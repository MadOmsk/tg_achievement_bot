import { useEffect, useState, type ReactNode } from "react";
import { peopleApi, type PersonProfile, type Relation } from "../../../api/people/peopleApi";
import { formatWhen, t, type Locale } from "../../../i18n";
import {
  Avatar,
  CoverImg,
  DropdownArrow,
  EmptyState,
  PlatformLogo,
  Sheet,
  TierMedals,
  useOpenGame,
} from "../../shared/lib";
import { PLATFORMS } from "../../shared/constants";
import { FollowsSheet } from "../../club/follows-sheet/FollowsSheet";
import { FollowButton } from "../follow-button/FollowButton";
import { FriendMark } from "../friend-mark/FriendMark";
import "./PersonSheet.css";
import { HandleName } from "../../shared/lib/handle-name/HandleName";

/** A person's card (#157): who they are, the follow button beside the name, how
 * many follow them and whom they follow (each opens the list), their accounts and
 * this month's games (when their privacy lets you see them). One's own card has
 * no button and no counts: only the accounts and the games. */
const EMPTY: Relation = { following: false, followed_by: false, friends: false, blocked: false };

export type SheetPerson = {
  /** The person's own id (#156). */
  id: number;
  handle: string;
  relation?: Relation;
};

export function PersonSheet({
  locale,
  data,
  person,
  onClose,
  onChange,
  onFlash,
  onOpenProfile,
  self = false,
}: {
  locale: Locale;
  data: string;
  /** Who: a row from the People lists, or just the author of a feed post. */
  person: SheetPerson;
  onClose: () => void;
  onChange?: (relation: Relation) => void;
  onFlash: (message: string) => void;
  /** Tapping the avatar or the nickname opens the full profile. */
  onOpenProfile?: (personId: number) => void;
  /** The viewer's own card. */
  self?: boolean;
}) {
  const [follows, setFollows] = useState<"following" | "followers" | null>(null);
  // One account's table open at a time, as with a game's updates; the first
  // is open until one is picked (owner, 2026-10-07).
  const [openAccount, setOpenAccount] = useState<string | null | undefined>(undefined);
  const [profile, setProfile] = useState<PersonProfile | null>(null);
  const [own, setOwn] = useState<Relation | null>(person.relation ?? null);
  const openGame = useOpenGame();
  const relation = own ?? profile?.relation ?? EMPTY;
  const personId = person.id;
  const handle = profile?.handle ?? person.handle;

  useEffect(() => {
    let cancelled = false;
    peopleApi
      .profile(data, person.id)
      .then((res) => {
        if (!cancelled) setProfile(res);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [data, person.id, own?.following, own?.blocked, own?.followed_by]);

  const changed = (next: Relation) => {
    setOwn(next);
    onChange?.(next);
  };

  const activity = profile?.activity ?? null;
  const shownAccount =
    openAccount === undefined
      ? activity?.platforms.length === 1
        ? activity.platforms[0].platform
        : null
      : openAccount;
  const presence = activity?.presence ?? null;
  const online = Boolean(presence && (presence.playing || presence.state === "Online"));
  const status = presence?.playing
    ? `${t(locale, "playing")} ${presence.title_name ?? ""}`.trim()
    : online
      ? t(locale, "online")
      : activity
        ? t(locale, "notOnline")
        : "";
  // "Friends" already reads on the button; only a one-way follower is said here.
  const tie = relation.followed_by && !relation.following ? t(locale, "followsYou") : "";
  const loading = profile === null;
  const games = activity?.games ?? [];

  const toProfile = personId != null && onOpenProfile ? () => onOpenProfile(personId) : undefined;

  // The page's head is the person (owner, 2026-10-07): face, nickname and
  // where they are on the left, the follow control on the right.
  const head = (
    <button type="button" className="account-who" onClick={toProfile} disabled={!toProfile}>
      <FriendMark friend={relation.friends && !self} label={t(locale, "friends")}>
        <Avatar
          name={handle}
          personId={personId ?? undefined}
          online={online}
          playing={Boolean(presence?.playing)}
          platform={presence?.platform}
          size={48}
        />
      </FriendMark>
      <span className="person-bar-title">
        <span className="account-name-row">
          <strong>
            <HandleName text={handle} />
          </strong>
        </span>
        {loading ? (
          <span className="skel ps-skel-line" aria-hidden />
        ) : (
          (status || tie) && <small>{[tie, status].filter(Boolean).join(" · ")}</small>
        )}
      </span>
    </button>
  );
  const follow =
    personId != null && !self ? (
      <FollowButton
        locale={locale}
        data={data}
        personId={personId}
        relation={relation}
        onChange={changed}
        onFlash={onFlash}
      />
    ) : undefined;

  return (
    <>
      <Sheet
        onClose={onClose}
        mid
        head={head}
        // Whether one follows them is not known until the card loads.
        aside={loading && !self ? <span className="skel line ps-skel-follow" aria-hidden /> : follow}
      >
        <div className="person-sheet">
          {loading ? (
            // The card opens at its loaded height and shape; nothing jumps when it fills.
            <>
              {!self && (
                <div className="ps-stats" aria-hidden>
                  <span className="skel ps-skel-tile" />
                  <span className="skel ps-skel-tile" />
                </div>
              )}
              {/* One account, open — most people have one platform — in the
                  account row's own classes. */}
              <div className="ps-section" aria-hidden>
                <span className="skel ps-skel-label" />
                <div className="ps-account is-open">
                  <div className="ps-row">
                    <span className="ps-mark">
                      <span className="skel ps-skel-mark" />
                    </span>
                    <span className="ps-row-main">
                      <span className="skel line ps-skel-name-line" />
                    </span>
                    <span className="skel line ps-skel-value" />
                  </div>
                  <div className="ps-details">
                    <dl className="ps-facts">
                      {[46, 30, 54, 34, 38, 62].map((width, i) => (
                        <div key={i} className="ps-fact">
                          <dt>
                            <span className="skel line ps-skel-fact" style={{ width: `${width}%` }} />
                          </dt>
                          <dd>
                            <span className="skel line ps-skel-fact" style={{ width: 44 }} />
                          </dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                </div>
              </div>
              <div className="ps-section" aria-hidden>
                <span className="skel ps-skel-label" />
                <div className="ps-games">
                  {[0, 1, 2].map((i) => (
                    <span key={i} className="ps-game">
                      <span className="skel ps-skel-cover" />
                      <span className="skel ps-skel-name" />
                      <span className="skel ps-skel-count" />
                    </span>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <>
              {!self && (
                <div className="ps-stats">
                  <button
                    type="button"
                    disabled={!profile.can_view || profile.followers === 0}
                    onClick={() => setFollows("followers")}
                  >
                    <strong>{profile.followers}</strong>
                    <span>{t(locale, "followersCount")}</span>
                  </button>
                  <button
                    type="button"
                    disabled={!profile.can_view || profile.following === 0}
                    onClick={() => setFollows("following")}
                  >
                    <strong>{profile.following}</strong>
                    <span>{t(locale, "followingCount")}</span>
                  </button>
                </div>
              )}

              {!profile.can_view && (
                <EmptyState
                  title={t(locale, "activityHidden")}
                  hint={t(locale, "activityHiddenHint")}
                  icon="lock"
                  slide
                />
              )}

              {activity && activity.platforms.length > 0 && (
                <div className="ps-section">
                  <p className="ps-label">{t(locale, "accounts")}</p>
                  {activity.platforms.map((p) => (
                    <AccountRow
                      key={p.platform}
                      p={p}
                      locale={locale}
                      open={shownAccount === p.platform}
                      onToggle={() => setOpenAccount(shownAccount === p.platform ? null : p.platform)}
                    />
                  ))}
                </div>
              )}

              {games.length > 0 && (
                <div className="ps-section">
                  <p className="ps-label">
                    {t(locale, "personMonthGames")}
                    <span className="ps-count">{games.length}</span>
                  </p>
                  <div className="ps-games">
                    {games.map((game) => (
                      <button
                        key={`${game.platform}:${game.title_id}`}
                        type="button"
                        className="ps-game"
                        onClick={() =>
                          openGame?.({
                            platform: game.platform,
                            title_id: game.title_id,
                            name: game.name,
                            icon_url: game.cover,
                            person:
                              personId != null ? { person_id: personId, name: handle } : null,
                          })
                        }
                      >
                        <CoverImg src={game.cover} className="ps-game-cover" />
                        <strong>{game.name}</strong>
                        <small>+{game.count}</small>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

        </div>
      </Sheet>
      {/* Over the card, not in its place: each is a step of its own for the
          phone's back. */}
      {follows && personId != null && (
        <FollowsSheet
          locale={locale}
          data={data}
          owner={personId}
          initial={follows}
          onClose={() => setFollows(null)}
          onOpen={(id) => onOpenProfile?.(id)}
          onFind={() => undefined}
          onFlash={onFlash}
        />
      )}
    </>
  );
}

type PlatformRow = NonNullable<PersonProfile["activity"]>["platforms"][number];

/** One account: its nickname and one number — Xbox its gamerscore, PlayStation
 * its trophies, Steam its achievements. What else there is (the achievements
 * behind the gamerscore, the medals, the level, finished games) opens under
 * the row on a tap. */
function AccountRow({
  p,
  locale,
  open,
  onToggle,
}: {
  p: PlatformRow;
  locale: Locale;
  open: boolean;
  onToggle: () => void;
}) {
  const xbox = p.platform.startsWith(PLATFORMS.XBOX);
  const psn = p.platform === PLATFORMS.PSN;
  const count = p.achievement_count ?? p.trophy_count ?? 0;
  const tiers =
    psn && p.bronze != null
      ? {
          platinum: p.platinum_count ?? 0,
          gold: p.gold ?? 0,
          silver: p.silver ?? 0,
          bronze: p.bronze,
        }
      : null;
  const finished = !psn && p.completed_games ? p.completed_games : 0;

  // A small table, like a game's "Об игре": one fact a line, only the known ones.
  const facts: Array<[string, ReactNode]> = [];
  const add = (label: string, value: ReactNode, when = true) => {
    if (when) facts.push([label, value]);
  };
  add(t(locale, "factLevel"), p.trophy_level, psn && p.trophy_level != null);
  add(t(locale, psn ? "factTrophies" : "factAchievements"), count, xbox || psn);
  add(t(locale, "factMedals"), tiers && <TierMedals counts={tiers} discSize={14} />, Boolean(tiers));
  add(t(locale, "factGames"), p.games, Boolean(p.games));
  add(t(locale, "factCompleted"), finished, finished > 0);
  add(t(locale, "factRare"), p.rare, !psn && Boolean(p.rare));
  add(t(locale, "factMonth"), `+${p.month_count}`, Boolean(p.month_count));
  add(
    t(locale, psn ? "factLastTrophy" : "factLast"),
    formatWhen(p.last_at, locale),
    Boolean(p.last_at),
  );
  add(t(locale, "factLinked"), formatWhen(p.linked_at, locale), Boolean(p.linked_at));

  const main =
    xbox && p.gamerscore != null ? (
      <>
        {p.gamerscore.toLocaleString("ru-RU")}
        <em>G</em>
      </>
    ) : (
      <>{count} 🏆</>
    );
  const more = facts.length > 0;

  return (
    <div className={open ? "ps-account is-open" : "ps-account"}>
      <button
        type="button"
        className="ps-row"
        onClick={more ? onToggle : undefined}
        disabled={!more}
        aria-expanded={more ? open : undefined}
      >
        <span className="ps-mark">
          <PlatformLogo platform={p.platform} size={24} />
        </span>
        <span className="ps-row-main">{p.name}</span>
        <strong className="ps-row-value">{main}</strong>
        {more && <DropdownArrow />}
      </button>
      {more && (
        <div className="ps-details" aria-hidden={!open}>
          <dl className="ps-facts">
            {facts.map(([label, value]) => (
              <div key={label} className="ps-fact">
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
}
