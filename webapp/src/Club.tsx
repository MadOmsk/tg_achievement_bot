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
  type SummaryMember,
} from "./api";
import { t, type Locale } from "./i18n";
import { GameHits, GameSheet, useHltbSearch } from "./Hltb";
import { AccountBar, Avatar, GlassWait, HomeSkel, PageSkel, PlatformLogo, ScoreCup, SearchBar, Sheet, accountLabel, isOnline, meScoreLines, telegramPhoto, Icon } from "./ui";
import { FeedList, FeedPosts, PeopleHits, PersonProfile, UnlockSlider, feedKey, matchQuery } from "./Person";

type ClubPane = "home" | "feed" | "summary";

const FRIENDS_PREVIEW = 6;

export function Club({
  me,
  locale,
  chatId,
  openPersonId,
  data,
  pane,
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
  const [monthLabel, setMonthLabel] = useState("");
  const [person, setPerson] = useState<PersonPayload | null>(null);
  const [clubReady, setClubReady] = useState(false);
  const [personBusy, setPersonBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [rosterOpen, setRosterOpen] = useState(false);
  const [game, setGame] = useState<HltbHit | null>(null);
  const [revealed, setRevealed] = useState<Set<string>>(new Set());
  const feedRef = useRef(feed);
  const onlineRef = useRef(online);
  feedRef.current = feed;
  onlineRef.current = online;

  const showSecrets = me.settings.show_secrets;
  const activeId =
    (me.chats.find((c) => c.chat_id === chatId) ?? me.chats[0])?.chat_id ?? null;

  useEffect(() => {
    if (!activeId || !data) return;
    let cancelled = false;
    setClubReady(false);
    const load = async () => {
      const [f, o, s] = await Promise.allSettled([
        fetchFeed(data, activeId),
        fetchOnline(data, activeId),
        fetchSummary(data, activeId),
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
      setClubReady(true);
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [activeId, data]);

  useEffect(() => {
    if (!openPersonId || !activeId || openPersonId === me.tg_id) {
      setPerson(null);
      setPersonBusy(false);
      return;
    }
    let cancelled = false;
    setPersonBusy(true);
    void fetchPerson(data, activeId, openPersonId, personMonth ? { month: personMonth } : undefined)
      .then((payload) => {
        if (!cancelled) {
          setPerson(payload);
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
  }, [openPersonId, activeId, data, locale, onFlash, me.tg_id, personMonth]);

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
      void fetchFeed(data, activeId, { month: ym })
        .then((payload) => {
          setHomeFeed(payload.items);
          setHomeMonth(payload.month);
          setMonths(payload.months);
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
          setMonthLabel(summary.month_label);
        })
        .catch((err: unknown) => onFlash(`${t(locale, "error")}: ${String(err)}`))
        .finally(() => setStatsBusy(false));
      return;
    }
    if (ym === personMonth) return;
    setPersonMonth(ym);
  };

  const mine = homeFeed.filter((row) => row.tg_id === me.tg_id);
  const monthChip = (ym: string, which: "feed" | "home" | "stats" | "person") =>
    ym ? (
      <button type="button" className="month-chip" onClick={() => setMonthPicker(which)}>
        {formatMonth(ym, locale, "chip")}
      </button>
    ) : null;
  const mySlides = mine.slice(0, 5);
  const myRest = mine.slice(5);
  const otherProfile = person && openPersonId && openPersonId !== me.tg_id ? person : null;
  const [homeCompact, setHomeCompact] = useState(false);
  const homeCompactRef = useRef(false);
  const homeLockRef = useRef(0);
  const homeFrameRef = useRef(0);

  useEffect(() => {
    if (pane !== "home" || otherProfile) {
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
  }, [pane, otherProfile, query]);

  if (me.chats.length === 0) {
    return <p className="empty">{t(locale, "noChats")}</p>;
  }

  if (openPersonId && openPersonId !== me.tg_id && personBusy && !otherProfile) {
    return (
      <div className="pane-fade person-wait">
        <GlassWait tall />
      </div>
    );
  }

  if (otherProfile) {
    return (
      <>
        <div className="pane-fade">
        <PersonProfile
          person={otherProfile}
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
              <AccountBar me={me} locale={locale} onProfile={() => openPerson(me.tg_id)} score={false} />
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
                onOpen={setGame}
              />
            </div>
          ) : (
            <>
              {mySlides.length > 0 ? (
                <UnlockSlider
                  items={mySlides}
                  locale={locale}
                  revealed={revealed}
                  showSecrets={showSecrets}
                  onReveal={(key) => setRevealed(new Set(revealed).add(key))}
                  onOpenPerson={openPerson}
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
              ) : myRest.length > 0 ? (
                <FeedList
                  items={myRest}
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
            monthLabel={monthLabel}
            feed={statsFeed}
            online={online}
            monthChip={monthChip(statsMonth, "stats")}
            busy={statsBusy}
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
      {game ? (
        <GameSheet
          preview={game}
          data={data}
          locale={locale}
          onClose={() => setGame(null)}
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
      <div className="sheet-content picker-sheet">
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
      <div className="sheet-content picker-sheet">
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

function ClubStats({
  meId,
  locale,
  day,
  month,
  games,
  monthLabel,
  feed,
  online,
  monthChip,
  busy,
  onOpenPerson,
}: {
  meId: number;
  locale: Locale;
  day: SummaryMember[];
  month: SummaryMember[];
  games: SummaryGame[];
  monthLabel: string;
  feed: FeedItem[];
  online: OnlineMember[];
  monthChip: ReactNode;
  busy: boolean;
  onOpenPerson: (tgId: number) => void;
}) {
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
      count: number;
    }
  >();
  for (const row of feed) {
    if (!row.game) continue;
    const key = `${row.platform}:${row.title_id}`;
    const cur = together.get(key) ?? {
      key,
      name: row.game,
      platform: row.platform,
      cover: row.game_icon_url || row.icon_url,
      people: new Map<number, string>(),
      count: 0,
    };
    cur.people.set(row.tg_id, row.person);
    cur.count += 1;
    if (!cur.cover) cur.cover = row.game_icon_url || row.icon_url;
    together.set(key, cur);
  }
  const hunts = [...together.values()]
    .filter((row) => row.people.size > 1)
    .sort((a, b) => b.people.size - a.people.size || b.count - a.count)
    .slice(0, 6);
  const rares = [...feed]
    .filter((row) => row.rarity_percent != null)
    .sort((a, b) => (a.rarity_percent ?? 100) - (b.rarity_percent ?? 100))
    .slice(0, 5);
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
          <p className="stat-block-title">{t(locale, "monthGames")}</p>
          <div className="stat-games">
            {games.map((g) => (
              <div key={`${g.platform}:${g.title_id}`} className="stat-game-tile">
                <span className="stat-game-art">
                  {g.icon_url ? (
                    <img src={g.icon_url} alt="" />
                  ) : (
                    <span className="stat-game-fallback" />
                  )}
                  <PlatformLogo platform={g.platform} size={14} />
                </span>
                <strong>{g.name || "—"}</strong>
                <p>{g.count}</p>
              </div>
            ))}
          </div>
        </section>
      ) : null}
      {day.length > 0 ? (
        <section className="stat-block">
          <p className="stat-block-title">{t(locale, "leadersDay")}</p>
          <Leaderboard rows={day} live={online} onOpen={onOpenPerson} />
        </section>
      ) : null}
      {month.length > 0 ? (
        <section className="stat-block">
          <p className="stat-block-title">{t(locale, "leadersMonth")}</p>
          <Leaderboard rows={month} live={online} showRare onOpen={onOpenPerson} />
        </section>
      ) : null}
      {hunts.length > 0 ? (
        <section className="stat-hunts-block">
          <p className="stat-block-title">{t(locale, "huntTogether")}</p>
          <div className="stat-hunts">
            {hunts.map((row) => {
              const faces = [...row.people.entries()];
              const shown = faces.slice(0, 4);
              const extra = faces.length - shown.length;
              return (
                <article key={row.key} className="stat-hunt">
                  <span className="stat-hunt-art">
                    {row.cover ? <img src={row.cover} alt="" /> : <span className="stat-game-fallback" />}
                    <PlatformLogo platform={row.platform} size={14} />
                  </span>
                  <div className="stat-hunt-copy">
                    <strong>{row.name}</strong>
                    <div className="stat-hunt-faces">
                      {shown.map(([tgId, name]) => (
                        <button
                          key={tgId}
                          type="button"
                          onClick={() => onOpenPerson(tgId)}
                          aria-label={name}
                        >
                          <Avatar
                            name={name}
                            tgId={tgId}
                            online={isOnline(online.find((m) => m.tg_id === tgId) ?? {})}
                            platform={online.find((m) => m.tg_id === tgId && isOnline(m))?.platform}
                            size={28}
                          />
                        </button>
                      ))}
                      {extra > 0 ? <span className="stat-hunt-more">+{extra}</span> : null}
                    </div>
                  </div>
                  <p className="stat-hunt-meta">
                    {row.people.size} {t(locale, "hunters")}
                    <span aria-hidden> · </span>
                    {row.count}
                  </p>
                </article>
              );
            })}
          </div>
        </section>
      ) : null}
      {rares.length > 0 ? (
        <section className="stat-block">
          <p className="stat-block-title">{t(locale, "rareFinds")}</p>
          {rares.map((row) => (
            <button key={feedKey(row)} type="button" className="stat-lead" onClick={() => onOpenPerson(row.tg_id)}>
              <Avatar
                name={row.person}
                tgId={row.tg_id}
                online={isOnline(online.find((m) => m.tg_id === row.tg_id) ?? {})}
                platform={online.find((m) => m.tg_id === row.tg_id && isOnline(m))?.platform}
                size={36}
              />
              <span className="stat-lead-copy">
                <strong>{row.person}</strong>
                <p>{row.name}</p>
              </span>
              <span className="stat-lead-n">{row.rarity_percent}%</span>
            </button>
          ))}
        </section>
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


