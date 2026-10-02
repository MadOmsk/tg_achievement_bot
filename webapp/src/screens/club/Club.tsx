import { useEffect, useRef, useState } from "react";
import {
  fetchFeed,
  fetchOnline,
  fetchPerson,
  fetchSummary,
  type FeedItem,
  type HltbHit,
  type MeResponse,
  type OnlineMember,
  type PersonPayload,
  type SummaryGame,
  type SummaryMember,
} from "../../api";
import { t, type Locale } from "../../i18n";
import { GameHits, GameSheet, useHltbSearch } from "../hltb";
import { FeedPosts, HiddenProfile, PeopleHits, PersonProfile, PlayedGames, RecentPosts, matchQuery } from "../person";
import { AccountBar, Avatar, EmptyState, FeedSkel, HomeBodySkel, HomeSkel, PersonSkel, RowsSkel, preloadImages, ScoreCup, StatsSkel, SearchBar, accountLabel, isOnline, meScoreLines, telegramPhoto } from "../../components/shared/lib";
import {
  ClubStats,
  FriendsStrip,
  MonthSheet,
  RosterSheet,
  formatMonth,
  statusOf,
} from "../../components/club";
import { Icon } from "../../components/shared/lib/icon/Icon";
import { ScopeChips, type FeedScope } from "../../components/club/scope-chips/ScopeChips";
import { SCREEN_NAMES, type ClubPane } from "../../components/shared/constants";
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
}) {
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [homeFeed, setHomeFeed] = useState<FeedItem[]>([]);
  const [statsFeed, setStatsFeed] = useState<FeedItem[]>([]);
  // One month for every pane (Home, Feed, Stats, a person's profile) — picking
  // it anywhere moves all of them together instead of each keeping its own.
  const [selectedMonth, setSelectedMonth] = useState("");
  const [months, setMonths] = useState<string[]>([]);
  const [liveMonth, setLiveMonth] = useState("");
  const [monthPicker, setMonthPicker] = useState(false);
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
  const [query, setQuery] = useState("");
  const [rosterOpen, setRosterOpen] = useState(false);
  const [hltbGame, setHltbGame] = useState<HltbHit | null>(null);
  const [gameSort, setGameSort] = useState<"recent" | "progress">("recent");
  const [revealed, setRevealed] = useState<Set<string>>(new Set());
  const feedRef = useRef(feed);
  const onlineRef = useRef(online);
  feedRef.current = feed;
  onlineRef.current = online;

  // What the Feed and the Ranking are about: the people you follow, or a chat.
  // Remembered per device; "following" only stands while it can be asked for.
  const [scope, setScope] = useState<FeedScope>(() => {
    try {
      const saved = window.localStorage.getItem("club-scope");
      if (saved === "following") return "following";
      const chat = Number(saved);
      if (saved && me.chats.some((c) => c.chat_id === chat)) return chat;
    } catch {
      /* storage may be blocked */
    }
    return chatId ?? me.chats[0]?.chat_id ?? "following";
  });
  const changeScope = (next: FeedScope) => {
    setScope(next);
    try {
      window.localStorage.setItem("club-scope", String(next));
    } catch {
      /* storage may be blocked */
    }
  };
  const scopeRef = scope === "following" || me.chats.some((c) => c.chat_id === scope) ? scope : null;

  const showSecrets = me.settings.show_secrets;
  // The friends are everybody but you.
  const others = online.filter((m) => m.tg_id !== me.tg_id);
  const activeId =
    (me.chats.find((c) => c.chat_id === chatId) ?? me.chats[0])?.chat_id ?? null;

  useEffect(() => {
    // Blank only when the chat/account changes — pull-to-refresh keeps the UI.
    setClubReady(false);
  }, [activeId, data, me.tg_id, scopeRef]);

  useEffect(() => {
    if (!activeId || !data) return;
    let cancelled = false;
    const load = async () => {
      const [f, o, s, mine] = await Promise.allSettled([
        fetchFeed(data, scopeRef ?? activeId),
        fetchOnline(data, activeId),
        fetchSummary(data, scopeRef ?? activeId),
        // Own unlocks from every linked platform — not the chat feed slice,
        // which is dominated by whoever unlocked most recently in-group.
        fetchPerson(data, activeId, me.tg_id),
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

  const needle = query.trim();
  const gameSearch = useHltbSearch(data, needle, locale, onFlash);
  const peopleHits = needle
    ? online.filter((m) => matchQuery(m.name, needle))
    : [];

  // One picker for every pane: moving the month refetches the feed, the
  // summary and "my" games together, so wherever it was opened from, every
  // other pane already has the right month's data when the person switches to it.
  const pickMonth = (ym: string) => {
    setMonthPicker(false);
    if (!activeId || !data || ym === selectedMonth) return;
    setMonthBusy(true);
    void Promise.allSettled([
      fetchFeed(data, scopeRef ?? activeId, { month: ym }),
      fetchSummary(data, scopeRef ?? activeId, { month: ym }),
      fetchPerson(data, activeId, me.tg_id, { month: ym }),
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
  const monthChip = (ym: string) =>
    ym && (
      <button type="button" className="month-chip" onClick={() => setMonthPicker(true)}>
        <span>{formatMonth(ym, locale, "chip")}</span>
        <Icon name="forward" size={17} />
      </button>
    );
  // No provisional, half-loaded view: the page stays on the skeleton until
  // the real payload (with its gallery picture and covers already preloaded)
  // is ready, so it appears once, whole, instead of in visible stages.
  const openProfile =
    openPersonId && person && person.tg_id === openPersonId ? person : null;
  const [scoreOpen, setScoreOpen] = useState(false);
  // A past month never changes once fetched — pull-to-refresh would just
  // reset the view back to the live month instead of refreshing anything.
  const isPastMonth = Boolean(selectedMonth) && Boolean(liveMonth) && selectedMonth !== liveMonth;

  if (me.chats.length === 0) {
    return <p className="empty">{t(locale, "noChats")}</p>;
  }

  if (openPersonId && personBusy) {
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
      {monthPicker && (
        <MonthSheet
          months={months}
          selected={selectedMonth}
          liveMonth={liveMonth}
          locale={locale}
          onClose={() => setMonthPicker(false)}
          onPick={pickMonth}
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
                    onProfile={() => setScoreOpen(true)}
                    status={
                      statusOf(online.find((m) => m.tg_id === me.tg_id)) ??
                      t(locale, "notOnline")
                    }
                    plats={
                      <ScoreCup
                        locale={locale}
                        lines={meScoreLines(me, locale)}
                        onEmpty={onSettings}
                        markSize={12}
                        open={scoreOpen}
                        onOpenChange={setScoreOpen}
                      />
                    }
                  />
                </div>
                {clubReady ? (
                  monthChip(selectedMonth)
                ) : (
                  <span className="skel month-chip-skel" aria-hidden />
                )}
              </div>
              <div className="home-top-search">
                <SearchBar locale={locale} value={query} onChange={setQuery} />
              </div>
            </div>
          </div>
          {!clubReady && !needle && <HomeBodySkel />}
          {(clubReady || needle) &&
            (needle ? (
              <div className="search-pane">
                {peopleHits.length > 0 && (
                  <PeopleHits members={peopleHits} locale={locale} onOpen={openPerson} />
                )}
                <GameHits
                  hits={gameSearch.hits}
                  busy={gameSearch.busy}
                  searched={gameSearch.searched}
                  locale={locale}
                  onOpen={setHltbGame}
                />
              </div>
            ) : (
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
                  mine.length === 0 &&
                  (me.xbox.linked || me.steam.linked || me.psn.linked) && (
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
            ))}
        </>
      )}

      {pane === SCREEN_NAMES.FEED && (
        <>
          <header className="page-head is-split">
            <div className="segment feed-switch" role="group">
              <button type="button" className={"is-on"} onClick={() => onPane(SCREEN_NAMES.FEED)}>
                {t(locale, "feed")}
              </button>
              <button type="button" className={undefined} onClick={() => onPane(SCREEN_NAMES.SUMMARY)}>
                {t(locale, "ranking")}
              </button>
            </div>
            {clubReady ? (
              monthChip(selectedMonth)
            ) : (
              <span className="skel month-chip-skel" aria-hidden />
            )}
          </header>
          <ScopeChips
            locale={locale}
            chats={me.chats}
            value={scopeRef ?? "following"}
            onChange={changeScope}
          />
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

      {pane === SCREEN_NAMES.SUMMARY && (
        <>
          <header className="page-head is-split">
            <div className="segment feed-switch" role="group">
              <button type="button" className={undefined} onClick={() => onPane(SCREEN_NAMES.FEED)}>
                {t(locale, "feed")}
              </button>
              <button type="button" className={"is-on"} onClick={() => onPane(SCREEN_NAMES.SUMMARY)}>
                {t(locale, "ranking")}
              </button>
            </div>
            {clubReady ? (
              monthChip(selectedMonth)
            ) : (
              <span className="skel month-chip-skel" aria-hidden />
            )}
          </header>
          <ScopeChips
            locale={locale}
            chats={me.chats}
            value={scopeRef ?? "following"}
            onChange={changeScope}
          />
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
        <RosterSheet
          members={others}
          locale={locale}
          onClose={() => setRosterOpen(false)}
          onOpen={(id) => {
            setRosterOpen(false);
            openPerson(id);
          }}
        />
      )}
      {monthPicker && (
        <MonthSheet
          months={months}
          selected={selectedMonth}
          liveMonth={liveMonth}
          locale={locale}
          onClose={() => setMonthPicker(false)}
          onPick={pickMonth}
        />
      )}
      {hltbGame && (
        <GameSheet
          preview={hltbGame}
          data={data}
          locale={locale}
          onClose={() => setHltbGame(null)}
          onFlash={onFlash}
        />
      )}
    </>
  );
}
