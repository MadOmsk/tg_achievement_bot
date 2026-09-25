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
import { FeedList, FeedPosts, PeopleHits, PersonProfile, UnlockSlider, matchQuery, recentGames } from "../person";
import { AccountBar, Avatar, GlassWait, HomeSkel, PageSkel, ScoreCup, SearchBar, accountLabel, isOnline, meScoreLines, telegramPhoto } from "../../components/shared/lib";
import {
  ClubStats,
  FriendsStrip,
  MonthSheet,
  RosterSheet,
  formatMonth,
} from "../../components/club";
import { SCREEN_NAMES, type ClubPane } from "../../components/shared/constants";
import "./Club.css";

const FRIENDS_PREVIEW = 6;

// The four contexts a month picker can be opened from on this screen — two
// of them (feed/home) happen to share a spelling with SCREEN_NAMES, the
// other two (stats/person) exist only here, so this stays its own small
// enum rather than stretching the navigation one to fit.
const MONTH_TARGETS = {
  FEED: SCREEN_NAMES.FEED,
  HOME: SCREEN_NAMES.HOME,
  STATS: "stats",
  PERSON: "person",
} as const;
type MonthTarget = (typeof MONTH_TARGETS)[keyof typeof MONTH_TARGETS];

export function Club({
  me,
  locale,
  chatId,
  openPersonId,
  data,
  pane,
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
  const [feedMonth, setFeedMonth] = useState("");
  const [homeMonth, setHomeMonth] = useState("");
  const [statsMonth, setStatsMonth] = useState("");
  const [personMonth, setPersonMonth] = useState("");
  const [months, setMonths] = useState<string[]>([]);
  const [liveMonth, setLiveMonth] = useState("");
  const [monthPicker, setMonthPicker] = useState<MonthTarget | null>(null);
  const [feedBusy, setFeedBusy] = useState(false);
  const [homeBusy, setHomeBusy] = useState(false);
  const [statsBusy, setStatsBusy] = useState(false);
  const [online, setOnline] = useState<OnlineMember[]>([]);
  const [day, setDay] = useState<SummaryMember[]>([]);
  const [month, setMonth] = useState<SummaryMember[]>([]);
  const [games, setGames] = useState<SummaryGame[]>([]);
  const [monthLabel, setMonthLabel] = useState("");
  const [person, setPerson] = useState<PersonPayload | null>(null);
  const [myPerson, setMyPerson] = useState<PersonPayload | null>(null);
  const [clubReady, setClubReady] = useState(false);
  const [personBusy, setPersonBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [rosterOpen, setRosterOpen] = useState(false);
  const [hltbGame, setHltbGame] = useState<HltbHit | null>(null);
  const [revealed, setRevealed] = useState<Set<string>>(new Set());
  const feedRef = useRef(feed);
  const onlineRef = useRef(online);
  feedRef.current = feed;
  onlineRef.current = online;

  const showSecrets = me.settings.show_secrets;
  const activeId =
    (me.chats.find((c) => c.chat_id === chatId) ?? me.chats[0])?.chat_id ?? null;

  useEffect(() => {
    // Blank only when the chat/account changes — pull-to-refresh keeps the UI.
    setClubReady(false);
  }, [activeId, data, me.tg_id]);

  useEffect(() => {
    if (!activeId || !data) return;
    let cancelled = false;
    const load = async () => {
      const [f, o, s, mine] = await Promise.allSettled([
        fetchFeed(data, activeId),
        fetchOnline(data, activeId),
        fetchSummary(data, activeId),
        // Own unlocks from every linked platform — not the chat feed slice,
        // which is dominated by whoever unlocked most recently in-group.
        fetchPerson(data, activeId, me.tg_id),
      ]);
      if (cancelled) return;
      if (f.status === "fulfilled") {
        setFeed(f.value.items);
        setHomeFeed(f.value.items);
        setStatsFeed(f.value.items);
        setFeedMonth(f.value.month);
        setHomeMonth(f.value.month);
        setStatsMonth(f.value.month);
        setPersonMonth(f.value.month);
        setLiveMonth(f.value.month);
        setMonths(f.value.months);
      }
      if (o.status === "fulfilled") setOnline(o.value.members);
      if (s.status === "fulfilled") {
        setDay(s.value.day);
        setMonth(s.value.month);
        setGames(s.value.games);
        setMonthLabel(s.value.month_label);
      }
      if (mine.status === "fulfilled") setMyPerson(mine.value);
      setClubReady(true);
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [activeId, data, me.tg_id, refreshKey]);

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
    void fetchPerson(data, activeId, openPersonId, personMonth ? { month: personMonth } : undefined)
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
  }, [openPersonId, activeId, data, locale, onFlash, me.tg_id, personMonth, refreshKey]);

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

  const pickMonth = (ym: string) => {
    const target = monthPicker;
    setMonthPicker(null);
    if (!activeId || !data || !target) return;
    if (target === MONTH_TARGETS.FEED) {
      if (ym === feedMonth) return;
      setFeedBusy(true);
      void fetchFeed(data, activeId, { month: ym })
        .then((payload) => {
          setFeed(payload.items);
          setFeedMonth(payload.month);
          setMonths(payload.months);
        })
        .catch((err: unknown) => onFlash(`${t(locale, "error")}: ${String(err)}`))
        .finally(() => setFeedBusy(false));
      return;
    }
    if (target === MONTH_TARGETS.HOME) {
      if (ym === homeMonth) return;
      setHomeBusy(true);
      void Promise.all([
        fetchFeed(data, activeId, { month: ym }),
        fetchPerson(data, activeId, me.tg_id, { month: ym }),
      ])
        .then(([payload, minePayload]) => {
          setHomeFeed(payload.items);
          setHomeMonth(payload.month);
          setMonths(payload.months);
          setMyPerson(minePayload);
        })
        .catch((err: unknown) => onFlash(`${t(locale, "error")}: ${String(err)}`))
        .finally(() => setHomeBusy(false));
      return;
    }
    if (target === MONTH_TARGETS.STATS) {
      if (ym === statsMonth) return;
      setStatsBusy(true);
      void Promise.all([
        fetchSummary(data, activeId, { month: ym }),
        fetchFeed(data, activeId, { month: ym }),
      ])
        .then(([summary, feedPayload]) => {
          setStatsMonth(feedPayload.month);
          setMonths(feedPayload.months);
          setStatsFeed(feedPayload.items);
          setDay(summary.day);
          setMonth(summary.month);
          setGames(summary.games);
          setMonthLabel(summary.month_label);
        })
        .catch((err: unknown) => onFlash(`${t(locale, "error")}: ${String(err)}`))
        .finally(() => setStatsBusy(false));
      return;
    }
    if (ym === personMonth) return;
    setPersonMonth(ym);
  };

  const mine = myPerson?.feed?.length
    ? myPerson.feed
    : homeFeed.filter((row) => row.tg_id === me.tg_id);
  const monthChip = (ym: string, which: MonthTarget) =>
    ym && (
      <button type="button" className="month-chip" onClick={() => setMonthPicker(which)}>
        {formatMonth(ym, locale, "chip")}
      </button>
    );
  const myGames = recentGames(mine, 5);
  const openProfile = (person && openPersonId) && person;
  const [homeCompact, setHomeCompact] = useState(false);
  const homeCompactRef = useRef(false);
  const homeLockRef = useRef(0);
  const homeFrameRef = useRef(0);

  useEffect(() => {
    if (pane !== SCREEN_NAMES.HOME || openProfile) {
      homeCompactRef.current = false;
      setHomeCompact(false);
      return;
    }
    const apply = (next: boolean) => {
      if (homeCompactRef.current === next) return;
      homeCompactRef.current = next;
      homeLockRef.current = performance.now() + 420;
      setHomeCompact(next);
    };
    const update = () => {
      if (query.trim()) {
        apply(true);
        return;
      }
      if (performance.now() < homeLockRef.current) return;
      const y = window.scrollY || document.documentElement.scrollTop || 0;
      if (homeCompactRef.current) {
        if (y <= 2) apply(false);
        return;
      }
      if (y > 88) apply(true);
    };
    const onScroll = () => {
      cancelAnimationFrame(homeFrameRef.current);
      homeFrameRef.current = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      cancelAnimationFrame(homeFrameRef.current);
      window.removeEventListener("scroll", onScroll);
    };
  }, [pane, openProfile, query]);

  if (me.chats.length === 0) {
    return <p className="empty">{t(locale, "noChats")}</p>;
  }

  if (openPersonId && personBusy && !openProfile) {
    return (
      <div className="pane-fade person-wait">
        <GlassWait tall />
      </div>
    );
  }

  if (openProfile) {
    return (
      <>
        <div className="pane-fade">
        <PersonProfile
          person={openProfile}
          locale={locale}
          revealed={revealed}
          showSecrets={showSecrets}
          monthChip={monthChip(personMonth, MONTH_TARGETS.PERSON)}
          onBack={() => {
            setPerson(null);
            onClosePerson?.();
          }}
          onReveal={(key) => setRevealed(new Set(revealed).add(key))}
        />
        </div>
      {monthPicker === MONTH_TARGETS.PERSON && (
        <MonthSheet
          months={months}
          selected={personMonth}
          liveMonth={liveMonth}
          locale={locale}
          onClose={() => setMonthPicker(null)}
          onPick={pickMonth}
        />
      )}
      </>
    );
  }

  return (
    <>
      <div className="pane-fade" key={pane}>
      {pane === SCREEN_NAMES.HOME && (
        <>
          <div className={homeCompact ? "home-chrome is-compact" : "home-chrome"}>
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
            <ScoreCup
              locale={locale}
              lines={meScoreLines(me, locale)}
              onEmpty={needle || homeCompact ? undefined : onSettings}
            />
            <div className="home-hello-row">
              <AccountBar
                me={me}
                locale={locale}
                onProfile={() => openPerson(me.tg_id)}
                score={false}
              />
            </div>
            <div className="home-search-row">
              <SearchBar locale={locale} value={query} onChange={setQuery} />
            </div>
          </div>
          {!clubReady && !needle && <HomeSkel />}
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
                {myGames.length > 0 && (
                  <UnlockSlider items={myGames} locale={locale} variant="game" />
                )}
                {myGames.length === 0 &&
                  (me.xbox.linked || me.steam.linked || me.psn.linked) && (
                    <p className="empty">{t(locale, "emptyFeed")}</p>
                  )}
                <FriendsStrip
                  members={online}
                  locale={locale}
                  limit={FRIENDS_PREVIEW}
                  onOpen={openPerson}
                  onSeeAll={() => setRosterOpen(true)}
                />
                <div className="section-head achievements-head">
                  <h1 className="kicker" style={{ margin: 0 }}>
                    {t(locale, "homeAchievements")}
                  </h1>
                  {monthChip(homeMonth, MONTH_TARGETS.HOME)}
                </div>
                {homeBusy && <GlassWait />}
                {!homeBusy && mine.length > 0 && (
                  <FeedList
                    items={mine}
                    locale={locale}
                    revealed={revealed}
                    showSecrets={showSecrets}
                    onReveal={(key) => setRevealed(new Set(revealed).add(key))}
                    onOpenPerson={openPerson}
                  />
                )}
              </>
            ))}
        </>
      )}

      {pane === SCREEN_NAMES.FEED &&
        (!clubReady ? (
          <PageSkel />
        ) : (
          <>
            <header className="page-head is-split">
              <h1>{t(locale, "feed")}</h1>
              {monthChip(feedMonth, MONTH_TARGETS.FEED)}
            </header>
            {feedBusy ? (
              <GlassWait />
            ) : feed.length === 0 ? (
              <p className="empty">{t(locale, "emptyFeed")}</p>
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
        ))}

      {pane === SCREEN_NAMES.SUMMARY &&
        (!clubReady ? (
          <PageSkel />
        ) : (
          <ClubStats
            meId={me.tg_id}
            locale={locale}
            day={day}
            month={month}
            games={games}
            monthLabel={monthLabel}
            feed={statsFeed}
            online={online}
            monthChip={monthChip(statsMonth, MONTH_TARGETS.STATS)}
            busy={statsBusy}
            revealed={revealed}
            showSecrets={showSecrets}
            onReveal={(key) => setRevealed(new Set(revealed).add(key))}
            onOpenPerson={openPerson}
          />
        ))}
      </div>

      {rosterOpen && (
        <RosterSheet
          members={online}
          locale={locale}
          onClose={() => setRosterOpen(false)}
          onOpen={(id) => {
            setRosterOpen(false);
            openPerson(id);
          }}
        />
      )}
      {monthPicker && monthPicker !== MONTH_TARGETS.PERSON && (
        <MonthSheet
          months={months}
          selected={
            monthPicker === MONTH_TARGETS.FEED
              ? feedMonth
              : monthPicker === MONTH_TARGETS.HOME
                ? homeMonth
                : statsMonth
          }
          liveMonth={liveMonth}
          locale={locale}
          onClose={() => setMonthPicker(null)}
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
