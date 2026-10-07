import { useEffect, useRef, useState } from "react";
import {
  fetchFeed,
  fetchOnline,
  fetchPerson,
  fetchSummary,
  type FeedItem,
  type MeResponse,
  type OnlineMember,
  type PersonPayload,
  type SummaryGame,
  type SummaryMember,
} from "../../api";
import { t, type Locale } from "../../i18n";
import { FeedPosts, HiddenProfile, PersonProfile, PlayedGames, RecentPosts } from "../person";
import { AccountBar, Avatar, EmptyState, MonthChipSkel, FeedSkel, FriendsSkel, HomeBodySkel, HomeSkel, PersonSkel, PlayedGamesSkel, preloadImages, ScoreCup, StatsSkel, Dropdown, DropdownArrow, accountLabel, isOnline, meScoreLines, telegramPhoto } from "../../components/shared/lib";
import {
  ClubStats,
  FriendsStrip,
  NewsFeed,
  currentMonth,
  formatMonth,
  statusOf,
} from "../../components/club";
import { Icon } from "../../components/shared/lib/icon/Icon";
import { SCREEN_NAMES, type ClubPane } from "../../components/shared/constants";
import { FollowsSheet } from "../../components/club/follows-sheet/FollowsSheet";
import { PersonSheet, type SheetPerson } from "../../components/people/person-sheet/PersonSheet";
import { peopleApi, type PersonRow } from "../../api/people/peopleApi";
import "./Club.css";
import { NotificationsBell } from "../../components/me/notifications/NotificationsBell";
import { cachedHome, rememberHome } from "../../components/shared/lib/home-cache/homeCache";

const FRIENDS_PREVIEW = 6;

export function Club({
  me,
  locale,
  chatId,
  openPersonId,
  data,
  pane,
  onPane,
  refreshKey = 0,
  onChat: _onChat,
  onFlash,
  onOpenPerson,
  onClosePerson,
  onPersonVisible,
  onSettings,
  onFind,
}: {
  me: MeResponse;
  locale: Locale;
  chatId: number | null;
  openPersonId?: number | null;
  data: string;
  pane: ClubPane;
  /** Switch between the Feed and the Ranking, which share one dock tab. */
  onPane: (pane: ClubPane) => void;
  /** Increment to refetch club data without leaving the current pane. */
  refreshKey?: number;
  onChat: (chatId: number) => void;
  onFlash: (message: string) => void;
  onOpenPerson?: (personId: number) => void;
  onClosePerson?: () => void;
  onPersonVisible?: (open: boolean) => void;
  onSettings?: () => void;
  /** Open the People tab with its search focused. */
  onFind: () => void;
}) {
  // Home as this device last saw it: shown at once, replaced by the answers.
  const [cache] = useState(() => cachedHome(me.person_id));
  const cachedReady = Boolean(cache?.feed && cache.summary && cache.mine);
  const [feed, setFeed] = useState<FeedItem[]>(cache?.feed?.items ?? []);
  const [homeFeed, setHomeFeed] = useState<FeedItem[]>(cache?.feed?.items ?? []);
  const [statsFeed, setStatsFeed] = useState<FeedItem[]>(cache?.feed?.items ?? []);
  // One month for every pane (Home, Feed, Stats, a person's profile) — picking
  // it anywhere moves all of them together instead of each keeping its own.
  const [selectedMonth, setSelectedMonth] = useState(cache?.feed?.month ?? "");
  const [months, setMonths] = useState<string[]>(cache?.feed?.months ?? []);
  const [liveMonth, setLiveMonth] = useState(cache?.feed?.month ?? "");
  const [monthBusy, setMonthBusy] = useState(false);
  const [online, setOnline] = useState<OnlineMember[]>(cache?.online?.members ?? []);
  const [day, setDay] = useState<SummaryMember[]>(cache?.summary?.day ?? []);
  const [monthBoard, setMonthBoard] = useState<SummaryMember[]>(cache?.summary?.month ?? []);
  const [yearBoard, setYearBoard] = useState<{ year: number; rows: SummaryMember[] } | null>(
    cache?.summary?.year_key ? { year: cache.summary.year_key, rows: cache.summary.year ?? [] } : null,
  );
  const [games, setGames] = useState<SummaryGame[]>(cache?.summary?.games ?? []);
  const [monthLabel, setMonthLabel] = useState(cache?.summary?.month_label ?? "");
  const [person, setPerson] = useState<PersonPayload | null>(null);
  const [myPerson, setMyPerson] = useState<PersonPayload | null>(cache?.mine ?? null);
  const [clubReady, setClubReady] = useState(cachedReady);
  // The first load over a remembered Home keeps it on screen, as a refresh does.
  const keepShown = useRef(cachedReady);
  const [personBusy, setPersonBusy] = useState(false);
  // The profile that could not be loaded: no skeleton is held for it.
  const [personFailed, setPersonFailed] = useState<number | null>(null);
  const [rosterOpen, setRosterOpen] = useState(false);
  const [gameSort, setGameSort] = useState<"recent" | "progress">("recent");
  const [revealed, setRevealed] = useState<Set<string>>(new Set());
  const [author, setAuthor] = useState<SheetPerson | null>(null);
  // Whom the open profile follows, for its own "Подписки" strip, and whose that is.
  // undefined while it loads (a skeleton strip), null when it is not to be shown.
  const [theirFollows, setTheirFollows] = useState<
    | {
        personId: number;
        rows: PersonRow[];
        /** Their friends (the people both following them and followed). */
        friends: Set<number>;
      }
    | null
    | undefined
  >(undefined);
  const [theirSheet, setTheirSheet] = useState<number | null>(null);
  // Who among the people followed follows back: the friend mark on Home's strip.
  const [myFriends, setMyFriends] = useState<Set<number>>(new Set());
  // Whether the profile open is the viewer's friend, for the mark in its bar.
  const [openFriend, setOpenFriend] = useState(false);
  const feedRef = useRef(feed);
  const onlineRef = useRef(online);
  feedRef.current = feed;
  onlineRef.current = online;

  // The Feed, the Ranking and the people strip are always about the people you
  // follow and yourself (#157); chats are only a way to find people to follow.
  const scopeRef = "following" as const;

  const showSecrets = me.settings.show_secrets;
  const hasAccounts = me.xbox.linked || me.steam.linked || me.psn.linked;
  // The friends are everybody but you.
  const others = online.filter((m) => m.person_id !== me.person_id);
  const activeId =
    (me.chats.find((c) => c.chat_id === chatId) ?? me.chats[0])?.chat_id ?? null;

  useEffect(() => {
    // Blank only when the chat/account changes — pull-to-refresh keeps the UI.
    if (keepShown.current) return;
    setClubReady(false);
  }, [activeId, data, me.person_id, scopeRef]);

  useEffect(() => {
    if (!data) return;
    let cancelled = false;
    const load = async () => {
      const [f, o, s, mine] = await Promise.allSettled([
        fetchFeed(data, scopeRef ?? activeId),
        fetchOnline(data, scopeRef ?? activeId),
        fetchSummary(data, scopeRef ?? activeId),
        // Own unlocks from every linked platform — not the chat feed slice,
        // which is dominated by whoever unlocked most recently in-group.
        // Read with or without a chat (#156): somebody who signed in by email
        // has none.
        fetchPerson(data, activeId, me.person_id),
      ]);
      if (cancelled) return;
      if (f.status === "fulfilled") {
        setFeed(f.value.items);
        setHomeFeed(f.value.items);
        setStatsFeed(f.value.items);
        setSelectedMonth(f.value.month);
        setLiveMonth(f.value.month);
        setMonths(f.value.months);
      }
      if (o.status === "fulfilled") setOnline(o.value.members);
      if (s.status === "fulfilled") {
        setDay(s.value.day);
        setMonthBoard(s.value.month);
        setYearBoard(s.value.year_key ? { year: s.value.year_key, rows: s.value.year ?? [] } : null);
        setGames(s.value.games);
        setMonthLabel(s.value.month_label);
      }
      if (mine.status === "fulfilled") setMyPerson(mine.value);
      rememberHome(me.person_id, {
        ...(f.status === "fulfilled" ? { feed: f.value } : {}),
        ...(o.status === "fulfilled" ? { online: o.value } : {}),
        ...(s.status === "fulfilled" ? { summary: s.value } : {}),
        ...(mine.status === "fulfilled" ? { mine: mine.value } : {}),
      });
      // The same "mine" games list the page renders below — preloaded before
      // the skeleton lifts, so the header, the gallery and the games appear
      // together instead of the gallery (and every game's cover) popping in
      // a beat after the text around them.
      if (refreshKey === 0 && !keepShown.current) {
        const myItems =
          mine.status === "fulfilled" && mine.value.feed?.length
            ? mine.value.feed
            : f.status === "fulfilled"
              ? f.value.items.filter((row) => row.person_id === me.person_id)
              : [];
        await preloadImages(
          [myItems[0]?.icon_url, ...myItems.slice(0, 8).map((row) => row.game_icon_url)],
          5000,
        );
      }
      if (cancelled) return;
      keepShown.current = false;
      setClubReady(true);
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [activeId, data, me.person_id, refreshKey, scopeRef]);

  useEffect(() => {
    if (!openPersonId) {
      setPerson(null);
      setPersonBusy(false);
      return;
    }
    // Own profile uses myPerson when the month matches; still refetch when
    // the picker moves so Steam/PSN/Xbox stay in sync with the chip.
    let cancelled = false;
    // Keep the open profile visible while pull-to-refresh refetches it.
    if (refreshKey === 0) setPersonBusy(true);
    void fetchPerson(data, activeId, openPersonId, selectedMonth ? { month: selectedMonth } : undefined)
      .then((payload) => {
        if (!cancelled) {
          setPerson(payload);
          if (openPersonId === me.person_id) setMyPerson(payload);
          if (payload.months?.length) setMonths(payload.months);
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const items = feedRef.current.filter((row) => row.person_id === openPersonId);
        const member = onlineRef.current.find((row) => row.person_id === openPersonId);
        if (items.length > 0 || member) {
          setPerson({
            person_id: openPersonId,
            name: member?.name ?? items[0]?.person ?? `id${openPersonId}`,
            platforms: [],
            today: { count: 0, score: 0, xbox: 0, steam: 0, psn: 0 },
            week: { count: 0, xbox: 0, steam: 0, psn: 0 },
            month: { count: 0, score: 0, xbox: 0, steam: 0, psn: 0 },
            games: [],
            feed: items,
          });
        } else {
          setPerson(null);
          setPersonFailed(openPersonId);
          onFlash(`${t(locale, "error")}: ${String(err)}`);
        }
      })
      .finally(() => {
        if (!cancelled) setPersonBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [openPersonId, activeId, data, locale, onFlash, me.person_id, selectedMonth, refreshKey]);

  useEffect(() => {
    if (!data) return;
    let cancelled = false;
    peopleApi
      .following(data)
      .then((res) => {
        if (cancelled) return;
        setMyFriends(
          new Set(
            res.people.flatMap((row) => (row.relation.friends ? [row.id] : [])),
          ),
        );
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [data, refreshKey]);

  // The open profile's follows: its person id comes with the card, and the list
  // only when their privacy lets the viewer see it.
  useEffect(() => {
    if (!openPersonId || !data) {
      setTheirFollows(null);
      return;
    }
    let cancelled = false;
    if (refreshKey === 0) {
      setTheirFollows(undefined);
      setOpenFriend(false);
    }
    peopleApi
      .profile(data, openPersonId)
      .then(async (card) => {
        if (!cancelled) setOpenFriend(card.relation.friends);
        if (!card.can_view) return null;
        if (openPersonId === me.person_id) {
          const res = await peopleApi.following(data);
          const friends = res.people.filter((row) => row.relation.friends);
          return {
            personId: openPersonId,
            rows: res.people,
            friends: new Set(friends.map((row) => row.id)),
          };
        }
        const [following, followers] = await Promise.all([
          peopleApi.followingOf(data, card.id),
          peopleApi.followersOf(data, card.id),
        ]);
        const back = new Set(followers.people.map((row) => row.id));
        return {
          personId: openPersonId,
          rows: following.people,
          friends: new Set(following.people.filter((row) => back.has(row.id)).map((row) => row.id)),
        };
      })
      .then((value) => {
        if (!cancelled) setTheirFollows(value);
      })
      .catch(() => {
        if (!cancelled) setTheirFollows(null);
      });
    return () => {
      cancelled = true;
    };
  }, [openPersonId, data, me.person_id, refreshKey]);

  useEffect(() => {
    onPersonVisible?.(person != null);
    return () => onPersonVisible?.(false);
  }, [person, onPersonVisible]);

  const openPerson = (personId: number) => {
    onOpenPerson?.(personId);
  };
  // Someone's card: from a feed author, or from the nickname on a profile.
  const authorSheet = author && (
    <PersonSheet
      locale={locale}
      data={data}
      person={author}
      onClose={() => setAuthor(null)}
      onFlash={onFlash}
      self={author.id === me.person_id}
      onOpenProfile={(id) => {
        setAuthor(null);
        // In the same turn as the card closes: the profile takes the card's
        // place in the history. A frame later the page was pushed apart from
        // the tap, and a phone's back skips such an entry and leaves the app.
        // The card's scroll is given back before the profile scrolls to its top.
        if (id !== openPersonId) openPerson(id);
      }}
    />
  );

  // One picker for every pane: moving the month refetches the feed, the
  // summary and "my" games together, so wherever it was opened from, every
  // other pane already has the right month's data when the person switches to it.
  const pickMonth = (ym: string) => {
    if (!data || ym === selectedMonth) return;
    setMonthBusy(true);
    void Promise.allSettled([
      fetchFeed(data, scopeRef ?? activeId, { month: ym }),
      fetchSummary(data, scopeRef ?? activeId, { month: ym }),
      fetchPerson(data, activeId, me.person_id, { month: ym }),
    ])
      .then(([f, s, mine]) => {
        if (f.status === "fulfilled") {
          setFeed(f.value.items);
          setHomeFeed(f.value.items);
          setStatsFeed(f.value.items);
          setSelectedMonth(f.value.month);
          setMonths(f.value.months);
        } else {
          onFlash(`${t(locale, "error")}: ${String(f.reason)}`);
        }
        if (s.status === "fulfilled") {
          setDay(s.value.day);
          setMonthBoard(s.value.month);
          setYearBoard(s.value.year_key ? { year: s.value.year_key, rows: s.value.year ?? [] } : null);
        setYearBoard(s.value.year_key ? { year: s.value.year_key, rows: s.value.year ?? [] } : null);
          setGames(s.value.games);
          setMonthLabel(s.value.month_label);
        }
        if (mine.status === "fulfilled") setMyPerson(mine.value);
      })
      .finally(() => setMonthBusy(false));
  };

  const mine = myPerson?.feed?.length
    ? myPerson.feed
    : homeFeed.filter((row) => row.person_id === me.person_id);
  const mineGameCount = new Set(
    mine.filter((row) => row.game).map((row) => `${row.platform}:${row.title_id}`),
  ).size;
  // An empty month points at the month before it, when there is one.
  const earlier = months[months.indexOf(selectedMonth) + 1];
  const previousMonthAction =
    selectedMonth && earlier
      ? { label: t(locale, "emptyPrevMonth"), onClick: () => pickMonth(earlier) }
      : undefined;
  // The Feed and the Ranking share one dock tab; the page title picks between
  // them, and more views can join the list later.
  const paneSwitch = (
    <Dropdown
      className="dd-trigger pane-switch"
      align="start"
      value={pane === SCREEN_NAMES.HOME ? SCREEN_NAMES.FEED : pane}
      options={[
        { value: SCREEN_NAMES.FEED, label: t(locale, "achievementsTab") },
        { value: SCREEN_NAMES.NEWS, label: t(locale, "news") },
        { value: SCREEN_NAMES.SUMMARY, label: t(locale, "ranking") },
      ]}
      onChange={(next) => onPane(next)}
      trigger={
        <>
          <h1>
            {t(
              locale,
              pane === SCREEN_NAMES.SUMMARY ? "ranking" : pane === SCREEN_NAMES.NEWS ? "news" : "achievementsTab",
            )}
          </h1>
          <DropdownArrow />
        </>
      }
    />
  );
  const monthChip = (ym: string) =>
    ym && (
      <Dropdown
        className="month-chip"
        value={ym}
        options={(months.length ? months : [ym]).map((m) => ({
          value: m,
          label: formatMonth(m, locale, "sheet"),
          hint: m === liveMonth ? t(locale, "nowMonth") : undefined,
        }))}
        onChange={pickMonth}
        trigger={
          <>
            <span>{formatMonth(ym, locale, "chip")}</span>
            <DropdownArrow />
          </>
        }
      />
    );
  // No provisional, half-loaded view: the page stays on the skeleton until
  // the real payload (with its gallery picture and covers already preloaded)
  // is ready, so it appears once, whole, instead of in visible stages.
  const openProfile =
    openPersonId && person && person.person_id === openPersonId ? person : null;
  // A past month never changes once fetched — pull-to-refresh would just
  // reset the view back to the live month instead of refreshing anything.
  const isPastMonth = Boolean(selectedMonth) && Boolean(liveMonth) && selectedMonth !== liveMonth;

  // The skeleton from the very first frame: personBusy is only set by an effect,
  // after a frame of the page underneath.
  if (openPersonId && (personBusy || (!openProfile && personFailed !== openPersonId))) {
    return (
      <div className="pane-fade person-wait">
        <PersonSkel />
      </div>
    );
  }

  if (openProfile?.hidden) {
    return (
      <HiddenProfile
        personId={openProfile.person_id}
        name={openProfile.name}
        locale={locale}
        onBack={() => {
          setPerson(null);
          onClosePerson?.();
        }}
      />
    );
  }

  if (openProfile) {
    return (
      <>
        <div className="pane-fade" data-no-pull={isPastMonth || undefined}>
        <PersonProfile
          person={openProfile}
          onOpenCard={() => setAuthor({ id: openProfile.person_id, handle: openProfile.name })}
          friend={openFriend && openProfile.person_id !== me.person_id}
          people={
            theirFollows === undefined ? (
              <FriendsSkel />
            ) : theirFollows && theirFollows.personId === openProfile.person_id ? (
              <FriendsStrip
                members={theirFollows.rows.flatMap((row) => {
                  // Where they are now, as on Home, for whoever the viewer's own
                  // online list knows; nobody else gets a made-up status.
                  const known = online.find((m) => m.person_id === row.id);
                  return [
                    known
                      ? { ...known, name: row.handle }
                      : {
                          person_id: row.id,
                          name: row.handle,
                          state: null,
                          platform: "",
                          title_name: null,
                          playing: false,
                          status: "",
                          icon: "",
                        },
                  ];
                })}
                locale={locale}
                limit={FRIENDS_PREVIEW}
                onOpen={(id) => {
                  if (id !== openPersonId) openPerson(id);
                }}
                onSeeAll={() => setTheirSheet(theirFollows.personId)}
                // Friends of either: theirs, and the viewer's own.
                friendIds={new Set([...theirFollows.friends, ...myFriends])}
                emptyText={t(
                  locale,
                  openProfile.person_id === me.person_id ? "friendsEmpty" : "theirFollowingEmpty",
                )}
              />
            ) : null
          }
          status={
            statusOf(online.find((m) => m.person_id === openProfile.person_id)) ??
            t(locale, "notOnline")
          }
          locale={locale}
          revealed={revealed}
          showSecrets={showSecrets}
          monthChip={monthChip(selectedMonth)}
          onBack={() => {
            setPerson(null);
            onClosePerson?.();
          }}
          onReveal={(key) => setRevealed(new Set(revealed).add(key))}
        />
        </div>
        {authorSheet}
        {theirSheet != null && (
          <FollowsSheet
            locale={locale}
            data={data}
            owner={openProfile.person_id === me.person_id ? undefined : theirSheet}
            onClose={() => setTheirSheet(null)}
            onOpen={(id) => {
              setTheirSheet(null);
              if (id !== openPersonId) openPerson(id);
            }}
            onFind={() => {
              setTheirSheet(null);
              onFind();
            }}
            onFlash={onFlash}
          />
        )}
      </>
    );
  }

  return (
    <>
      <div key={pane} data-no-pull={isPastMonth || undefined}>
      {pane === SCREEN_NAMES.HOME && (
        <>
          <div className="home-chrome">
            <div className="home-top">
              <div className="home-top-main">
                <button
                  type="button"
                  className="home-me"
                  onClick={() => setAuthor({ id: me.person_id, handle: accountLabel(me) })}
                  aria-label={accountLabel(me)}
                >
                  <Avatar
                    name={accountLabel(me)}
                    photo={telegramPhoto()}
                    personId={me.person_id ?? undefined}
                    online={isOnline(online.find((m) => m.person_id === me.person_id) ?? {})}
                    platform={online.find((m) => m.person_id === me.person_id && isOnline(m))?.platform}
                    size={48}
                    zoomLabel={t(locale, "close")}
                  />
                </button>
                <div className="home-hello-row">
                  <AccountBar
                    me={me}
                    locale={locale}
                    onProfile={() => setAuthor({ id: me.person_id, handle: accountLabel(me) })}
                    status={
                      statusOf(online.find((m) => m.person_id === me.person_id)) ??
                      t(locale, "notOnline")
                    }
                    plats={
                      <ScoreCup
                        locale={locale}
                        lines={meScoreLines(me, locale)}
                        markSize={12}
                      />
                    }
                  />
                </div>
                <NotificationsBell
                  data={data}
                  locale={locale}
                  unread={me.notifications_unread ?? 0}
                  onOpenPerson={openPerson}
                />
                {!hasAccounts ? null : clubReady ? (
                  monthChip(selectedMonth)
                ) : (
                  <MonthChipSkel label={formatMonth(selectedMonth || currentMonth(), locale, "chip")} />
                )}
              </div>
            </div>
          </div>
          {!clubReady && <HomeBodySkel />}
          {clubReady && (
              <>
                {monthBusy && <HomeSkel />}
                {!monthBusy && mine.length > 0 && (
                  <RecentPosts
                    items={mine}
                    locale={locale}
                    revealed={revealed}
                    showSecrets={showSecrets}
                    onReveal={(key) => setRevealed(new Set(revealed).add(key))}
                  />
                )}
                {!monthBusy &&
                  !hasAccounts && (
                    <EmptyState
                      title={t(locale, "welcomeTitle")}
                      hint={t(locale, "welcomeText")}
                      action={onSettings ? { label: t(locale, "connect"), onClick: onSettings } : undefined}
                      slide
                    />
                  )}
                {!monthBusy &&
                  mine.length === 0 &&
                  hasAccounts && (
                    <EmptyState
                      title={t(locale, isPastMonth ? "emptyTitlePast" : "emptyTitleNow")}
                      hint={t(locale, "emptyHomeHint")}
                      action={previousMonthAction}
                      slide
                    />
                  )}
                <FriendsStrip
                  members={others}
                  locale={locale}
                  limit={FRIENDS_PREVIEW}
                  friendIds={myFriends}
                  onOpen={openPerson}
                  onSeeAll={() => setRosterOpen(true)}
                  onFind={onFind}
                />
                {(monthBusy || mine.length > 0) && (
                  <>
                    <div className="section-head achievements-head">
                      <span className="section-title-group">
                        <h1 className="kicker" style={{ margin: 0 }}>
                          {t(locale, "games")}
                        </h1>
                        {!monthBusy && mineGameCount > 0 && (
                          <span className="section-count">{mineGameCount}</span>
                        )}
                      </span>
                      {!monthBusy && mineGameCount > 1 && (
                        <button
                          type="button"
                          className="sort-toggle"
                          aria-label={t(locale, gameSort === "recent" ? "sortProgress" : "sortRecent")}
                          onClick={() =>
                            setGameSort((cur) => (cur === "recent" ? "progress" : "recent"))
                          }
                        >
                          <Icon name={gameSort === "recent" ? "sort" : "stats"} size={18} />
                        </button>
                      )}
                    </div>
                    {monthBusy && <PlayedGamesSkel />}
                    {!monthBusy && mine.length > 0 && (
                      <PlayedGames items={mine} locale={locale} sort={gameSort} />
                    )}
                  </>
                )}
              </>
          )}
        </>
      )}

      {pane === SCREEN_NAMES.FEED && (
        <>
          <header className="page-head is-split">
            {paneSwitch}
            {clubReady ? (
              monthChip(selectedMonth)
            ) : (
              <MonthChipSkel label={formatMonth(selectedMonth || currentMonth(), locale, "chip")} />
            )}
          </header>
          {!clubReady || monthBusy ? (
            <FeedSkel head={false} />
          ) : feed.length === 0 ? (
            <EmptyState
              title={t(locale, isPastMonth ? "emptyTitlePast" : "emptyTitleNow")}
              hint={t(locale, "emptyFeedHint")}
              action={previousMonthAction}
              slide
            />
          ) : (
            <FeedPosts
              items={feed}
              locale={locale}
              revealed={revealed}
              showSecrets={showSecrets}
              onReveal={(key) => setRevealed(new Set(revealed).add(key))}
              onOpenPerson={openPerson}
            />
          )}
        </>
      )}

      {pane === SCREEN_NAMES.NEWS && (
        <>
          <header className="page-head is-split">
            {paneSwitch}
            {clubReady ? (
              monthChip(selectedMonth)
            ) : (
              <MonthChipSkel label={formatMonth(selectedMonth || currentMonth(), locale, "chip")} />
            )}
          </header>
          <NewsFeed data={data} locale={locale} month={selectedMonth || currentMonth()} />
        </>
      )}

      {pane === SCREEN_NAMES.SUMMARY && (
        <>
          <header className="page-head is-split">
            {paneSwitch}
            {clubReady ? (
              monthChip(selectedMonth)
            ) : (
              <MonthChipSkel label={formatMonth(selectedMonth || currentMonth(), locale, "chip")} />
            )}
          </header>
          {!clubReady ? (
            <StatsSkel head={false} />
          ) : (
            <ClubStats
              meId={me.person_id ?? 0}
              locale={locale}
              day={day}
              month={monthBoard}
              year={yearBoard}
              games={games}
              monthLabel={monthLabel}
              feed={statsFeed}
              online={online}
              monthChip={monthChip(selectedMonth)}
              busy={monthBusy}
              revealed={revealed}
              showSecrets={showSecrets}
              onReveal={(key) => setRevealed(new Set(revealed).add(key))}
              onOpenPerson={openPerson}
              hideHeader
            />
          )}
        </>
      )}
      </div>

      {rosterOpen && (
        <FollowsSheet
          locale={locale}
          data={data}
          onClose={() => setRosterOpen(false)}
          onOpen={(id) => {
            setRosterOpen(false);
            openPerson(id);
          }}
          onFind={() => {
            setRosterOpen(false);
            onFind();
          }}
          onFlash={onFlash}
        />
      )}
      {authorSheet}
    </>
  );
}
