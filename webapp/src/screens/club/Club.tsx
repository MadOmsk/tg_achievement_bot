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
import { AccountBar, Avatar, EmptyState, FeedSkel, HomeBodySkel, HomeSkel, PersonSkel, RowsSkel, preloadImages, ScoreCup, StatsSkel, Dropdown, DropdownArrow, accountLabel, isOnline, meScoreLines, telegramPhoto } from "../../components/shared/lib";
import {
  ClubStats,
  FriendsStrip,
  formatMonth,
  statusOf,
} from "../../components/club";
import { Icon } from "../../components/shared/lib/icon/Icon";
import { SCREEN_NAMES, type ClubPane } from "../../components/shared/constants";
import { FollowsSheet } from "../../components/club/follows-sheet/FollowsSheet";
import { PersonSheet, type SheetPerson } from "../../components/people/person-sheet/PersonSheet";
import "./Club.css";

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
  onOpenPerson?: (tgId: number) => void;
  onClosePerson?: () => void;
  onPersonVisible?: (open: boolean) => void;
  onSettings?: () => void;
  /** Open the People tab with its search focused. */
  onFind: () => void;
}) {
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [homeFeed, setHomeFeed] = useState<FeedItem[]>([]);
  const [statsFeed, setStatsFeed] = useState<FeedItem[]>([]);
  // One month for every pane (Home, Feed, Stats, a person's profile) — picking
  // it anywhere moves all of them together instead of each keeping its own.
  const [selectedMonth, setSelectedMonth] = useState("");
  const [months, setMonths] = useState<string[]>([]);
  const [liveMonth, setLiveMonth] = useState("");
  const [monthBusy, setMonthBusy] = useState(false);
  const [online, setOnline] = useState<OnlineMember[]>([]);
  const [day, setDay] = useState<SummaryMember[]>([]);
  const [monthBoard, setMonthBoard] = useState<SummaryMember[]>([]);
  const [games, setGames] = useState<SummaryGame[]>([]);
  const [monthLabel, setMonthLabel] = useState("");
  const [person, setPerson] = useState<PersonPayload | null>(null);
  const [myPerson, setMyPerson] = useState<PersonPayload | null>(null);
  const [clubReady, setClubReady] = useState(false);
  const [personBusy, setPersonBusy] = useState(false);
  // The profile that could not be loaded: no skeleton is held for it.
  const [personFailed, setPersonFailed] = useState<number | null>(null);
  const [rosterOpen, setRosterOpen] = useState(false);
  const [gameSort, setGameSort] = useState<"recent" | "progress">("recent");
  const [revealed, setRevealed] = useState<Set<string>>(new Set());
  const [author, setAuthor] = useState<SheetPerson | null>(null);
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
  const others = online.filter((m) => m.tg_id !== me.tg_id);
  const activeId =
    (me.chats.find((c) => c.chat_id === chatId) ?? me.chats[0])?.chat_id ?? null;

  useEffect(() => {
    // Blank only when the chat/account changes — pull-to-refresh keeps the UI.
    setClubReady(false);
  }, [activeId, data, me.tg_id, scopeRef]);

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
        // A profile page is read inside a chat; with none, the home page falls
        // back to the feed below.
        activeId ? fetchPerson(data, activeId, me.tg_id) : Promise.reject(new Error("no chat")),
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
        setGames(s.value.games);
        setMonthLabel(s.value.month_label);
      }
      if (mine.status === "fulfilled") setMyPerson(mine.value);
      // The same "mine" games list the page renders below — preloaded before
      // the skeleton lifts, so the header, the gallery and the games appear
      // together instead of the gallery (and every game's cover) popping in
      // a beat after the text around them.
      if (refreshKey === 0) {
        const myItems =
          mine.status === "fulfilled" && mine.value.feed?.length
            ? mine.value.feed
            : f.status === "fulfilled"
              ? f.value.items.filter((row) => row.tg_id === me.tg_id)
              : [];
        await preloadImages(
          [myItems[0]?.icon_url, ...myItems.slice(0, 8).map((row) => row.game_icon_url)],
          5000,
        );
      }
      if (cancelled) return;
      setClubReady(true);
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [activeId, data, me.tg_id, refreshKey, scopeRef]);

  useEffect(() => {
    if (!openPersonId || !activeId) {
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
          if (openPersonId === me.tg_id) setMyPerson(payload);
          if (payload.months?.length) setMonths(payload.months);
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const items = feedRef.current.filter((row) => row.tg_id === openPersonId);
        const member = onlineRef.current.find((row) => row.tg_id === openPersonId);
        if (items.length > 0 || member) {
          setPerson({
            tg_id: openPersonId,
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
  }, [openPersonId, activeId, data, locale, onFlash, me.tg_id, selectedMonth, refreshKey]);

  useEffect(() => {
    onPersonVisible?.(person != null);
    return () => onPersonVisible?.(false);
  }, [person, onPersonVisible]);

  const openPerson = (tgId: number) => {
    onOpenPerson?.(tgId);
  };
  // Someone's card: from a feed author, or from the nickname on a profile.
  const authorSheet = author && (
    <PersonSheet
      locale={locale}
      data={data}
      person={author}
      onClose={() => setAuthor(null)}
      onFlash={onFlash}
      onOpenProfile={(id) => {
        setAuthor(null);
        // After the drawer has let the page go: it gives the old scroll back as
        // it closes, which would fight the profile's own scroll to the top.
        if (id !== openPersonId) requestAnimationFrame(() => openPerson(id));
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
      activeId
        ? fetchPerson(data, activeId, me.tg_id, { month: ym })
        : Promise.reject(new Error("no chat")),
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
          setGames(s.value.games);
          setMonthLabel(s.value.month_label);
        }
        if (mine.status === "fulfilled") setMyPerson(mine.value);
      })
      .finally(() => setMonthBusy(false));
  };

  const mine = myPerson?.feed?.length
    ? myPerson.feed
    : homeFeed.filter((row) => row.tg_id === me.tg_id);
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
      value={pane === SCREEN_NAMES.SUMMARY ? SCREEN_NAMES.SUMMARY : SCREEN_NAMES.FEED}
      options={[
        { value: SCREEN_NAMES.FEED, label: t(locale, "feed") },
        { value: SCREEN_NAMES.SUMMARY, label: t(locale, "ranking") },
      ]}
      onChange={(next) => onPane(next)}
      trigger={
        <>
          <h1>{t(locale, pane === SCREEN_NAMES.SUMMARY ? "ranking" : "feed")}</h1>
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
    openPersonId && person && person.tg_id === openPersonId ? person : null;
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
        tgId={openProfile.tg_id}
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
          onOpenCard={
            openProfile.tg_id === me.tg_id
              ? undefined
              : () => setAuthor({ tg_id: openProfile.tg_id, handle: openProfile.name })
          }
          status={
            statusOf(online.find((m) => m.tg_id === openProfile.tg_id)) ??
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
                  onClick={() => openPerson(me.tg_id)}
                  aria-label={accountLabel(me)}
                >
                  <Avatar
                    name={accountLabel(me)}
                    photo={telegramPhoto()}
                    tgId={me.tg_id}
                    online={isOnline(online.find((m) => m.tg_id === me.tg_id) ?? {})}
                    platform={online.find((m) => m.tg_id === me.tg_id && isOnline(m))?.platform}
                    size={48}
                    zoomLabel={t(locale, "close")}
                  />
                </button>
                <div className="home-hello-row">
                  <AccountBar
                    me={me}
                    locale={locale}
                    onProfile={() => undefined}
                    status={
                      statusOf(online.find((m) => m.tg_id === me.tg_id)) ??
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
                {!hasAccounts ? null : clubReady ? (
                  monthChip(selectedMonth)
                ) : (
                  <span className="skel month-chip-skel" aria-hidden />
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
                    {monthBusy && <RowsSkel count={3} />}
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
              <span className="skel month-chip-skel" aria-hidden />
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
              onOpenPerson={(id) => {
                // The author's card first; the full profile is a tap away in it.
                if (id === me.tg_id) {
                  openPerson(id);
                  return;
                }
                const post = feed.find((row) => row.tg_id === id);
                setAuthor({ tg_id: id, handle: post?.person ?? "" });
              }}
            />
          )}
        </>
      )}

      {pane === SCREEN_NAMES.SUMMARY && (
        <>
          <header className="page-head is-split">
            {paneSwitch}
            {clubReady ? (
              monthChip(selectedMonth)
            ) : (
              <span className="skel month-chip-skel" aria-hidden />
            )}
          </header>
          {!clubReady ? (
            <StatsSkel head={false} />
          ) : (
            <ClubStats
              meId={me.tg_id}
              locale={locale}
              day={day}
              month={monthBoard}
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
            requestAnimationFrame(() => openPerson(id));
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
