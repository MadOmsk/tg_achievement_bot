import { useEffect, useRef, useState, type ReactNode } from "react";
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
  type DroppedGame,
  type SummaryMember,
} from "./api";
import { t, timeAgo, type Locale } from "./i18n";
import { GameHits, GameSheet, useHltbSearch } from "./Hltb";
import { FeedList, FeedPosts, PeopleHits, PersonProfile, UnlockCard, UnlockSlider, HeroMarks, feedKey, matchQuery, recentGames } from "./Person";
import { AccountBar, Avatar, CoverImg, GlassWait, HomeSkel, PageSkel, PlatformDot, PlatformLogo, ScoreCup, SearchBar, Sheet, accountLabel, isOnline, meScoreLines, telegramPhoto, Icon } from "./ui";

type ClubPane = "home" | "feed" | "summary";

const FRIENDS_PREVIEW = 6;
const GAMES_PREVIEW = 6;

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
  const [monthPicker, setMonthPicker] = useState<"feed" | "home" | "stats" | "person" | null>(null);
  const [feedBusy, setFeedBusy] = useState(false);
  const [homeBusy, setHomeBusy] = useState(false);
  const [statsBusy, setStatsBusy] = useState(false);
  const [online, setOnline] = useState<OnlineMember[]>([]);
  const [day, setDay] = useState<SummaryMember[]>([]);
  const [month, setMonth] = useState<SummaryMember[]>([]);
  const [games, setGames] = useState<SummaryGame[]>([]);
  const [dropped, setDropped] = useState<DroppedGame[]>([]);
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
        setDropped(s.value.dropped ?? []);
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
    if (target === "feed") {
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
    if (target === "home") {
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
    if (target === "stats") {
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
          setDropped(summary.dropped ?? []);
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
  const monthChip = (ym: string, which: "feed" | "home" | "stats" | "person") =>
    ym ? (
      <button type="button" className="month-chip" onClick={() => setMonthPicker(which)}>
        {formatMonth(ym, locale, "chip")}
      </button>
    ) : null;
  const myGames = recentGames(mine, 5);
  const openProfile = person && openPersonId ? person : null;
  const [homeCompact, setHomeCompact] = useState(false);
  const homeCompactRef = useRef(false);
  const homeLockRef = useRef(0);
  const homeFrameRef = useRef(0);

  useEffect(() => {
    if (pane !== "home" || openProfile) {
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
          monthChip={monthChip(personMonth, "person")}
          onBack={() => {
            setPerson(null);
            onClosePerson?.();
          }}
          onReveal={(key) => setRevealed(new Set(revealed).add(key))}
        />
        </div>
      {monthPicker === "person" ? (
        <MonthSheet
          months={months}
          selected={personMonth}
          liveMonth={liveMonth}
          locale={locale}
          onClose={() => setMonthPicker(null)}
          onPick={pickMonth}
        />
      ) : null}
      </>
    );
  }

  return (
    <>
      <div className="pane-fade" key={pane}>
      {pane === "home" ? (
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
          {!clubReady && !needle ? <HomeSkel /> : null}
          {clubReady || needle ? needle ? (
            <div className="search-pane">
              {peopleHits.length > 0 ? (
                <PeopleHits members={peopleHits} locale={locale} onOpen={openPerson} />
              ) : null}
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
              {myGames.length > 0 ? (
                <UnlockSlider
                  items={myGames}
                  locale={locale}
                  variant="game"
                />
              ) : me.xbox.linked || me.steam.linked || me.psn.linked ? (
                <p className="empty">{t(locale, "emptyFeed")}</p>
              ) : null}
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
                {monthChip(homeMonth, "home")}
              </div>
              {homeBusy ? (
                <GlassWait />
              ) : mine.length > 0 ? (
                <FeedList
                  items={mine}
                  locale={locale}
                  revealed={revealed}
                  showSecrets={showSecrets}
                  onReveal={(key) => setRevealed(new Set(revealed).add(key))}
                  onOpenPerson={openPerson}
                />
              ) : null}
            </>
          ) : null}
        </>
      ) : null}

      {pane === "feed" ? (
        !clubReady ? (
          <PageSkel />
        ) : (
          <>
            <header className="page-head is-split">
              <h1>{t(locale, "feed")}</h1>
              {monthChip(feedMonth, "feed")}
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
        )
      ) : null}

      {pane === "summary" ? (
        !clubReady ? (
          <PageSkel />
        ) : (
          <ClubStats
            meId={me.tg_id}
            locale={locale}
            day={day}
            month={month}
            games={games}
            dropped={dropped}
            monthLabel={monthLabel}
            feed={statsFeed}
            online={online}
            monthChip={monthChip(statsMonth, "stats")}
            busy={statsBusy}
            revealed={revealed}
            showSecrets={showSecrets}
            onReveal={(key) => setRevealed(new Set(revealed).add(key))}
            onOpenPerson={openPerson}
          />
        )
      ) : null}
      </div>

      {rosterOpen ? (
        <RosterSheet
          members={online}
          locale={locale}
          onClose={() => setRosterOpen(false)}
          onOpen={(id) => {
            setRosterOpen(false);
            openPerson(id);
          }}
        />
      ) : null}
      {monthPicker && monthPicker !== "person" ? (
        <MonthSheet
          months={months}
          selected={
            monthPicker === "feed" ? feedMonth : monthPicker === "home" ? homeMonth : statsMonth
          }
          liveMonth={liveMonth}
          locale={locale}
          onClose={() => setMonthPicker(null)}
          onPick={pickMonth}
        />
      ) : null}
      {hltbGame ? (
        <GameSheet
          preview={hltbGame}
          data={data}
          locale={locale}
          onClose={() => setHltbGame(null)}
          onFlash={onFlash}
        />
      ) : null}
    </>
  );
}

function formatMonth(ym: string, locale: Locale, kind: "chip" | "sheet" = "sheet"): string {
  const [year, month] = ym.split("-").map(Number);
  if (!year || !month) return ym;
  const tag = locale === "ru" ? "ru-RU" : "en-US";
  const nowYear = new Date().getFullYear();
  const opts: Intl.DateTimeFormatOptions =
    kind === "chip"
      ? { month: "short", ...(year === nowYear ? {} : { year: "numeric" }) }
      : { month: "long", year: "numeric" };
  return new Date(year, month - 1, 1).toLocaleDateString(tag, opts).replace(" г.", "");
}

function MonthSheet({
  months,
  selected,
  liveMonth,
  locale,
  onClose,
  onPick,
}: {
  months: string[];
  selected: string;
  liveMonth: string;
  locale: Locale;
  onClose: () => void;
  onPick: (ym: string) => void;
}) {
  return (
    <Sheet onClose={onClose} closeLabel={t(locale, "close")} noClose mid>
      <div className="sheet-content score-sheet picker-sheet">
        <h2>{t(locale, "pickMonth")}</h2>
        <div className="picker-list">
          {months.map((ym) => (
            <button
              key={ym}
              type="button"
              className={ym === selected ? "picker-row is-on" : "picker-row"}
              onClick={() => onPick(ym)}
            >
              <strong>{formatMonth(ym, locale, "sheet")}</strong>
              {ym === liveMonth ? <span>{t(locale, "nowMonth")}</span> : null}
            </button>
          ))}
        </div>
      </div>
    </Sheet>
  );
}

function rankPeople(members: OnlineMember[]): OnlineMember[] {
  return [...members].sort(
    (a, b) =>
      Number(b.playing) - Number(a.playing) ||
      Number(b.state === "Online") - Number(a.state === "Online"),
  );
}

function FriendsStrip({
  members,
  locale,
  limit,
  onOpen,
  onSeeAll,
}: {
  members: OnlineMember[];
  locale: Locale;
  limit: number;
  onOpen: (tgId: number) => void;
  onSeeAll: () => void;
}) {
  const pool = rankPeople(members);
  if (pool.length === 0) return null;
  const shown = pool.slice(0, limit);
  return (
    <>
      <div className="section-head">
        <h1 className="kicker" style={{ margin: 0 }}>
          {t(locale, "friends")}
        </h1>
        <button type="button" className="see-all" onClick={onSeeAll}>
          <span>{t(locale, "seeAll")}</span>
          <Icon name="forward" size={16} />
        </button>
      </div>
      <div className="friends">
        {shown.map((m) => (
          <button key={m.tg_id} type="button" className="friend" onClick={() => onOpen(m.tg_id)}>
            <Avatar name={m.name} tgId={m.tg_id} online={isOnline(m)} platform={m.platform} size={80} />
            <strong>{m.name}</strong>
            <p>{m.playing ? m.title_name : m.status}</p>
          </button>
        ))}
      </div>
    </>
  );
}

function RosterSheet({
  members,
  locale,
  onClose,
  onOpen,
}: {
  members: OnlineMember[];
  locale: Locale;
  onClose: () => void;
  onOpen: (tgId: number) => void;
}) {
  const rows = rankPeople(members);
  return (
    <Sheet onClose={onClose} closeLabel={t(locale, "close")} noClose mid>
      <div className="sheet-content score-sheet picker-sheet">
        <h2>{t(locale, "friends")}</h2>
        {rows.length === 0 ? (
          <p className="empty">{t(locale, "nobodyOnline")}</p>
        ) : (
          <div className="picker-list">
            {rows.map((m) => (
              <button key={m.tg_id} type="button" className="picker-row is-person" onClick={() => onOpen(m.tg_id)}>
                <Avatar name={m.name} tgId={m.tg_id} online={isOnline(m)} platform={m.platform} size={40} />
                <span className="picker-row-copy">
                  <strong>{m.name}</strong>
                  <p>{m.playing ? m.title_name : m.status}</p>
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </Sheet>
  );
}

function GamesSheet({
  games,
  locale,
  onClose,
}: {
  games: SummaryGame[];
  locale: Locale;
  onClose: () => void;
}) {
  return (
    <Sheet onClose={onClose} closeLabel={t(locale, "close")} noClose mid>
      <div className="sheet-content score-sheet picker-sheet games-sheet">
        <h2>{t(locale, "monthGames")}</h2>
        <div className="picker-list games-sheet-list">
          {games.map((g) => {
            const meta = [
              `${g.count} ${t(locale, "achievements")}`,
              g.score > 0 ? `+${g.score} G` : null,
            ]
              .filter(Boolean)
              .join(" · ");
            return (
              <div key={`${g.platform}:${g.title_id}`} className="picker-row is-game">
                <span className="picker-game-art">
                  <CoverImg src={g.icon_url} kind="game" className="picker-game-cover" />
                  <PlatformLogo platform={g.platform} size={14} />
                </span>
                <span className="picker-row-copy">
                  <strong>{g.name || "—"}</strong>
                  <p>{meta}</p>
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </Sheet>
  );
}

function DroppedSheet({
  rows,
  locale,
  onClose,
  onOpenPerson,
}: {
  rows: DroppedGame[];
  locale: Locale;
  onClose: () => void;
  onOpenPerson: (tgId: number) => void;
}) {
  return (
    <Sheet onClose={onClose} closeLabel={t(locale, "close")} noClose mid>
      <div className="sheet-content score-sheet picker-sheet games-sheet">
        <h2>{t(locale, "droppedGames")}</h2>
        <div className="picker-list games-sheet-list">
          {rows.map((row) => (
            <button
              key={`${row.tg_id}:${row.platform}:${row.title_id}`}
              type="button"
              className="picker-row is-game"
              onClick={() => {
                onClose();
                onOpenPerson(row.tg_id);
              }}
            >
              <span className="picker-game-art">
                <CoverImg src={row.icon_url} kind="game" className="picker-game-cover" />
                <PlatformLogo platform={row.platform} size={14} />
              </span>
              <span className="picker-row-copy">
                <strong>{row.name || "—"}</strong>
                <p>
                  {row.person}
                  <i aria-hidden> · </i>
                  {timeAgo(row.last_earned, locale)}
                </p>
              </span>
            </button>
          ))}
        </div>
      </div>
    </Sheet>
  );
}

function ClubStats({
  meId,
  locale,
  day,
  month,
  games,
  dropped,
  monthLabel,
  feed,
  online,
  monthChip,
  busy,
  revealed,
  showSecrets,
  onReveal,
  onOpenPerson,
}: {
  meId: number;
  locale: Locale;
  day: SummaryMember[];
  month: SummaryMember[];
  games: SummaryGame[];
  dropped: DroppedGame[];
  monthLabel: string;
  feed: FeedItem[];
  online: OnlineMember[];
  monthChip: ReactNode;
  busy: boolean;
  revealed: Set<string>;
  showSecrets?: boolean;
  onReveal: (key: string) => void;
  onOpenPerson: (tgId: number) => void;
}) {
  const [gamesOpen, setGamesOpen] = useState(false);
  const [droppedOpen, setDroppedOpen] = useState(false);
  const [board, setBoard] = useState<"day" | "month">("day");
  const [finds, setFinds] = useState<"plats" | "rares">("plats");
  const [rareItem, setRareItem] = useState<FeedItem | null>(null);
  const [huntOpen, setHuntOpen] = useState<{
    key: string;
    name: string;
    platform: string;
    cover: string | null;
    people: Map<number, string>;
    items: FeedItem[];
  } | null>(null);
  if (day.length === 0 && month.length === 0 && feed.length === 0) {
    return (
      <>
        <header className="page-head is-split">
          <h1>{t(locale, "stats")}</h1>
          {monthChip}
        </header>
        <p className="empty">{t(locale, "emptySummary")}</p>
      </>
    );
  }
  const me = Number(meId);
  const dayFromFeed = countByPerson(feed, Date.now() - 24 * 60 * 60 * 1000);
  const monthFromFeed = countByPerson(feed);
  const mineDay = pickCount(day, me, dayFromFeed);
  const mineMonth = pickCount(month, me, monthFromFeed);
  const clubDay = sumCounts(day) || sumMap(dayFromFeed);
  const clubMonth = sumCounts(month) || sumMap(monthFromFeed);
  const together = new Map<
    string,
    {
      key: string;
      name: string;
      platform: string;
      cover: string | null;
      people: Map<number, string>;
      items: FeedItem[];
    }
  >();
  for (const row of feed) {
    if (!row.game) continue;
    const key = `${row.platform}:${row.title_id}`;
    const cur = together.get(key) ?? {
      key,
      name: row.game,
      platform: row.platform,
      cover: row.game_icon_url || null,
      people: new Map<number, string>(),
      items: [],
    };
    cur.people.set(row.tg_id, row.person);
    cur.items.push(row);
    if (!cur.cover && row.game_icon_url) cur.cover = row.game_icon_url;
    together.set(key, cur);
  }
  const hunts = [...together.values()]
    .filter((row) => row.people.size > 1)
    .sort(
      (a, b) =>
        b.people.size - a.people.size || b.items.length - a.items.length,
    )
    .slice(0, 4);
  const rares = [...feed]
    .filter((row) => row.rarity_percent != null)
    .sort((a, b) => (a.rarity_percent ?? 100) - (b.rarity_percent ?? 100))
    .slice(0, 5);
  const plats = recentCompletions(feed).slice(0, 8);
  const boardRows = board === "day" ? day : month;
  const findsTab = finds === "plats" && plats.length === 0 && rares.length > 0 ? "rares" : finds;
  const findsRows = findsTab === "plats" ? plats : rares;
  return (
    <>
      <header className="page-head is-split">
        <h1>{t(locale, "stats")}</h1>
        {monthChip}
      </header>
      {busy ? <GlassWait /> : null}
      <section className="stat-hero">
        <StatTile
          label={t(locale, "today")}
          club={clubDay}
          mine={mineDay}
          hint={t(locale, "youShare")}
        />
        <StatTile
          label={monthLabel || t(locale, "thisMonth")}
          club={clubMonth}
          mine={mineMonth}
          hint={t(locale, "youShare")}
        />
      </section>
      {games.length > 0 ? (
        <section className="stat-games-block">
          <div className="section-head">
            <p className="stat-block-title" style={{ margin: 0 }}>
              {t(locale, "monthGames")}
            </p>
            {games.length > 0 ? (
              <button type="button" className="see-all" onClick={() => setGamesOpen(true)}>
                <span>{t(locale, "seeAll")}</span>
                <Icon name="forward" size={16} />
              </button>
            ) : null}
          </div>
          <div className="stat-games">
            {games.slice(0, GAMES_PREVIEW).map((g) => (
              <div key={`${g.platform}:${g.title_id}`} className="stat-game-tile">
                <span className="stat-game-art">
                  <CoverImg src={g.icon_url} kind="game" className="stat-game-fallback" />
                  <PlatformLogo platform={g.platform} size={14} />
                </span>
                <strong>{g.name || "—"}</strong>
                <p>{g.count}</p>
              </div>
            ))}
          </div>
        </section>
      ) : null}
      {dropped.length > 0 ? (
        <section className="stat-games-block">
          <div className="section-head">
            <p className="stat-block-title" style={{ margin: 0 }}>
              {t(locale, "droppedGames")}
            </p>
            <button type="button" className="see-all" onClick={() => setDroppedOpen(true)}>
              <span>{t(locale, "seeAll")}</span>
              <Icon name="forward" size={16} />
            </button>
          </div>
          <div className="stat-games">
            {dropped.slice(0, GAMES_PREVIEW).map((row) => (
              <button
                key={`${row.tg_id}:${row.platform}:${row.title_id}`}
                type="button"
                className="stat-game-tile"
                onClick={() => onOpenPerson(row.tg_id)}
              >
                <span className="stat-game-art">
                  <CoverImg src={row.icon_url} kind="game" className="stat-game-fallback" />
                  <PlatformLogo platform={row.platform} size={14} />
                </span>
                <strong>{row.name || "—"}</strong>
                <p>{row.person}</p>
              </button>
            ))}
          </div>
        </section>
      ) : null}
      {gamesOpen ? (
        <GamesSheet games={games} locale={locale} onClose={() => setGamesOpen(false)} />
      ) : null}
      {droppedOpen ? (
        <DroppedSheet
          rows={dropped}
          locale={locale}
          onClose={() => setDroppedOpen(false)}
          onOpenPerson={onOpenPerson}
        />
      ) : null}
      {day.length > 0 || month.length > 0 ? (
        <section className="stat-block">
          <div className="stat-block-head">
            <p className="stat-block-title">{t(locale, "leaders")}</p>
            <div className="segment" role="tablist" aria-label={t(locale, "leaders")}>
              <button
                type="button"
                role="tab"
                aria-selected={board === "day"}
                className={board === "day" ? "is-on" : undefined}
                onClick={() => setBoard("day")}
              >
                {t(locale, "boardDay")}
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={board === "month"}
                className={board === "month" ? "is-on" : undefined}
                onClick={() => setBoard("month")}
              >
                {t(locale, "boardMonth")}
              </button>
            </div>
          </div>
          {boardRows.length > 0 ? (
            <Leaderboard
              rows={boardRows}
              live={online}
              showRare={board === "month"}
              onOpen={onOpenPerson}
            />
          ) : (
            <p className="empty">{t(locale, "emptySummary")}</p>
          )}
        </section>
      ) : null}
      {plats.length > 0 || rares.length > 0 ? (
        <section className="stat-rares-block">
          <div className="stat-block-head">
            <p className="stat-block-title">{t(locale, "finds")}</p>
            <div className="segment" role="tablist" aria-label={t(locale, "finds")}>
              {plats.length > 0 ? (
                <button
                  type="button"
                  role="tab"
                  aria-selected={findsTab === "plats"}
                  className={findsTab === "plats" ? "is-on" : undefined}
                  onClick={() => setFinds("plats")}
                >
                  {t(locale, "recentPlats")}
                </button>
              ) : null}
              {rares.length > 0 ? (
                <button
                  type="button"
                  role="tab"
                  aria-selected={findsTab === "rares"}
                  className={findsTab === "rares" ? "is-on" : undefined}
                  onClick={() => setFinds("rares")}
                >
                  {t(locale, "rareFinds")}
                </button>
              ) : null}
            </div>
          </div>
          <div className="stat-rares">
            {findsRows.map((row) => {
              const key = feedKey(row);
              const secret = Boolean(
                row.is_secret && !showSecrets && !revealed.has(key),
              );
              const isPlat = findsTab === "plats";
              return (
                <button
                  key={key}
                  type="button"
                  className={["feed-row", secret ? "is-secret" : "", isPlat ? "is-done" : ""]
                    .filter(Boolean)
                    .join(" ")}
                  onClick={() => setRareItem(row)}
                >
                  <CoverImg
                    src={isPlat ? row.game_icon_url || row.icon_url : row.icon_url}
                    kind={isPlat ? "game" : "achievement"}
                    className="feed-cover"
                    imgClassName="cover"
                  >
                    {secret ? (
                      <span className="feed-lock">
                        <Icon name="lock" size={18} />
                      </span>
                    ) : null}
                  </CoverImg>
                  <span className="feed-copy">
                    <span className="feed-copy-head">
                      <p className="unlock-title">
                        <span>
                          {isPlat
                            ? row.game || row.name
                            : secret
                              ? t(locale, "secret")
                              : row.name}
                        </span>
                        <PlatformDot platform={row.platform} locale={locale} />
                      </p>
                      {isPlat ? (
                        <span className="feed-plat is-plat" aria-hidden>
                          💠
                        </span>
                      ) : (
                        <HeroMarks
                          compact
                          score={
                            row.tier_badge || (row.gamerscore ? `${row.gamerscore} G` : null)
                          }
                          rarity={
                            row.rarity_percent != null ? `${row.rarity_percent}%` : null
                          }
                        />
                      )}
                    </span>
                    {isPlat ? (
                      <p className="unlock-game">{timeAgo(row.unlocked_at, locale)}</p>
                    ) : row.game ? (
                      <p className="unlock-game">{row.game}</p>
                    ) : null}
                    <p className="feed-person">{row.person}</p>
                  </span>
                </button>
              );
            })}
          </div>
        </section>
      ) : null}
      {hunts.length > 0 ? (
        <section className="stat-hunts-block">
          <p className="stat-block-title">{t(locale, "huntTogether")}</p>
          <div className="stat-hunts">
            {hunts.map((hunt) => {
              const faces = [...hunt.people.entries()];
              const shown = faces.slice(0, 4);
              const extra = faces.length - shown.length;
              return (
                <button
                  key={hunt.key}
                  type="button"
                  className="stat-hunt"
                  onClick={() => setHuntOpen(hunt)}
                >
                  <span className="stat-hunt-art">
                    <CoverImg src={hunt.cover} kind="game" className="stat-game-fallback" />
                    <PlatformLogo platform={hunt.platform} size={14} />
                  </span>
                  <div className="stat-hunt-copy">
                    <strong>{hunt.name}</strong>
                    <div className="stat-hunt-faces">
                      {shown.map(([tgId, name]) => (
                        <Avatar
                          key={tgId}
                          name={name}
                          tgId={tgId}
                          online={isOnline(online.find((m) => m.tg_id === tgId) ?? {})}
                          platform={
                            online.find((m) => m.tg_id === tgId && isOnline(m))?.platform
                          }
                          size={28}
                        />
                      ))}
                      {extra > 0 ? <span className="stat-hunt-more">+{extra}</span> : null}
                    </div>
                  </div>
                  <p className="stat-hunt-count">{hunt.items.length}</p>
                </button>
              );
            })}
          </div>
        </section>
      ) : null}
      {huntOpen ? (
        <Sheet mid onClose={() => setHuntOpen(null)} closeLabel={t(locale, "close")} noClose>
          <div className="sheet-content score-sheet picker-sheet hunt-sheet">
            <h2>{huntOpen.name}</h2>
            <div className="stat-hunt-sheet-list">
              {huntOpen.items.map((row) => {
                const key = feedKey(row);
                const secret = Boolean(
                  row.is_secret && !showSecrets && !revealed.has(key),
                );
                return (
                  <button
                    key={key}
                    type="button"
                    className={["feed-row", secret ? "is-secret" : ""]
                      .filter(Boolean)
                      .join(" ")}
                    onClick={() => setRareItem(row)}
                  >
                    <CoverImg
                      src={row.icon_url}
                      kind="achievement"
                      className="feed-cover"
                      imgClassName="cover"
                    >
                      {secret ? (
                        <span className="feed-lock">
                          <Icon name="lock" size={18} />
                        </span>
                      ) : null}
                    </CoverImg>
                    <span className="feed-copy">
                      <span className="feed-copy-head">
                        <p className="unlock-title">
                          <span>{secret ? t(locale, "secret") : row.name}</span>
                          <PlatformDot platform={row.platform} locale={locale} />
                        </p>
                        <HeroMarks
                          compact
                          score={
                            row.tier_badge || (row.gamerscore ? `${row.gamerscore} G` : null)
                          }
                          rarity={
                            row.rarity_percent != null ? `${row.rarity_percent}%` : null
                          }
                        />
                      </span>
                      {row.game ? <p className="unlock-game">{row.game}</p> : null}
                      <p className="feed-person">{row.person}</p>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </Sheet>
      ) : null}
      {rareItem ? (
        <Sheet mid onClose={() => setRareItem(null)} closeLabel={t(locale, "close")} noClose>
          <div className="sheet-unlock">
            <UnlockCard
              item={rareItem}
              locale={locale}
              secret={Boolean(
                rareItem.is_secret && !showSecrets && !revealed.has(feedKey(rareItem)),
              )}
              author
              gameInCopy
              onOpenPerson={onOpenPerson}
              onReveal={onReveal}
            />
          </div>
        </Sheet>
      ) : null}
    </>
  );
}

function countByPerson(items: FeedItem[], sinceMs?: number): Map<number, number> {
  const counts = new Map<number, number>();
  for (const row of items) {
    if (sinceMs != null) {
      const at = Date.parse(row.unlocked_at ?? "");
      if (!Number.isFinite(at) || at < sinceMs) continue;
    }
    const id = Number(row.tg_id);
    counts.set(id, (counts.get(id) ?? 0) + 1);
  }
  return counts;
}

/** Games closed to 100% — PSN platinum, or any platform with unlocked ≥ total. */
function recentCompletions(items: FeedItem[]): FeedItem[] {
  const best = new Map<string, FeedItem>();
  for (const row of items) {
    const done =
      row.trophy_type === "platinum" ||
      Boolean(row.progress && row.progress.total > 0 && row.progress.unlocked >= row.progress.total);
    if (!done) continue;
    const key = `${row.tg_id}:${row.platform}:${row.title_id}`;
    const prev = best.get(key);
    if (!prev) {
      best.set(key, row);
      continue;
    }
    // Prefer the real platinum trophy over another unlock of the same finished game.
    if (row.trophy_type === "platinum" && prev.trophy_type !== "platinum") {
      best.set(key, row);
      continue;
    }
    if (prev.trophy_type === "platinum" && row.trophy_type !== "platinum") continue;
    if (Date.parse(row.unlocked_at ?? "") > Date.parse(prev.unlocked_at ?? "")) {
      best.set(key, row);
    }
  }
  return [...best.values()].sort(
    (a, b) => Date.parse(b.unlocked_at ?? "") - Date.parse(a.unlocked_at ?? ""),
  );
}

function sumMap(counts: Map<number, number>): number {
  return [...counts.values()].reduce((n, row) => n + row, 0);
}

function sumCounts(rows: SummaryMember[]): number {
  return rows.reduce((n, row) => n + row.count, 0);
}

function pickCount(rows: SummaryMember[], meId: number, fallback: Map<number, number>): number {
  const fromApi = rows.find((row) => Number(row.tg_id) === meId)?.count ?? 0;
  return fromApi || fallback.get(meId) || 0;
}

function StatTile({
  label,
  mine,
  club,
  hint,
}: {
  label: string;
  mine: number;
  club: number;
  hint: string;
}) {
  // Club total is the hero number — personal 0 with a busy club used to
  // look like both tiles were broken. Share stays on the secondary line.
  const pct = club ? Math.round((mine / club) * 100) : 0;
  return (
    <div className="stat-tile">
      <p>{label}</p>
      <strong>{club}</strong>
      <small>
        {mine} · {pct}% {hint}
      </small>
    </div>
  );
}

function Leaderboard({
  rows,
  live,
  showRare,
  onOpen,
}: {
  rows: SummaryMember[];
  live?: OnlineMember[];
  showRare?: boolean;
  onOpen: (tgId: number) => void;
}) {
  return (
    <div className="stat-leads">
      {rows.map((row, i) => (
        <button key={row.tg_id} type="button" className="stat-lead" onClick={() => onOpen(row.tg_id)}>
          <span className="stat-rank">{i + 1}</span>
          <Avatar
            name={row.name}
            tgId={row.tg_id}
            online={isOnline(live?.find((m) => m.tg_id === row.tg_id) ?? {})}
            platform={live?.find((m) => m.tg_id === row.tg_id && isOnline(m))?.platform}
            size={36}
          />
          <span className="stat-lead-copy">
            <strong>{row.name}</strong>
          </span>
          <span className="stat-lead-n">
            {row.count}
            {showRare && row.rare ? ` · 💎${row.rare}` : ""}
          </span>
        </button>
      ))}
    </div>
  );
}


