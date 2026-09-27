import { useState, type ReactNode } from "react";
import type {
  FeedItem,
  OnlineMember,
  SummaryGame,
  SummaryMember,
} from "../../../api";
import { t, type Locale } from "../../../i18n";
import {
  Avatar,
  CoverImg,
  GlassWait,
  Icon,
  Row,
  RowsSection,
  Sheet,
  isOnline,
  useOpenGame,
} from "../../shared/lib";
import { UI_CONFIG } from "../../shared/constants";
import { UnlockCard, feedKey } from "../../person";
import { AchievementRows } from "../achievement-rows/AchievementRows";
import { GamesSheet } from "../games-sheet/GamesSheet";
import {
  countByPerson,
  pickCount,
  rareFinders,
  sumCounts,
  sumMap,
  type RareFinder,
} from "../utils";
import "./ClubStats.css";

const { GAMES_PREVIEW, RARE_FIND_PERCENT, DAY_MS } = UI_CONFIG.STATS;

type Period = "day" | "month";

interface Hunt {
  key: string;
  name: string;
  platform: string;
  cover: string | null;
  people: Map<number, string>;
  items: FeedItem[];
}

export function ClubStats({
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
  const openGame = useOpenGame();
  const [gamesOpen, setGamesOpen] = useState(false);
  const [board, setBoard] = useState<Period>("day");
  const [rareOpen, setRareOpen] = useState<RareFinder | null>(null);
  const [huntOpen, setHuntOpen] = useState<Hunt | null>(null);
  const [item, setItem] = useState<FeedItem | null>(null);

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
  const dayFromFeed = countByPerson(feed, Date.now() - DAY_MS);
  const monthFromFeed = countByPerson(feed);
  const mineDay = pickCount(day, me, dayFromFeed);
  const mineMonth = pickCount(month, me, monthFromFeed);
  const clubDay = sumCounts(day) || sumMap(dayFromFeed);
  const clubMonth = sumCounts(month) || sumMap(monthFromFeed);

  const together = new Map<string, Hunt>();
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
    );
  const finders = rareFinders(feed, RARE_FIND_PERCENT);
  const boardRows = board === "day" ? day : month;

  const periodSwitch = (
    value: Period,
    onChange: (next: Period) => void,
    label: string,
  ) => (
    <div className="segment" role="tablist" aria-label={label}>
      {(["day", "month"] as const).map((period) => (
        <button
          key={period}
          type="button"
          role="tab"
          aria-selected={value === period}
          className={value === period ? "is-on" : undefined}
          onClick={() => onChange(period)}
        >
          {t(locale, period === "day" ? "boardDay" : "boardMonth")}
        </button>
      ))}
    </div>
  );

  const faceOf = (tgId: number, name: string, size: number) => (
    <Avatar
      name={name}
      tgId={tgId}
      online={isOnline(online.find((m) => m.tg_id === tgId) ?? {})}
      platform={online.find((m) => m.tg_id === tgId && isOnline(m))?.platform}
      size={size}
    />
  );

  return (
    <>
      <header className="page-head is-split">
        <h1>{t(locale, "stats")}</h1>
        {monthChip}
      </header>
      {busy && <GlassWait />}
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

      {games.length > 0 && (
        <section className="rows-section stat-games-block">
          <div className="rows-head">
            <h3 className="rows-title">{t(locale, "monthGames")}</h3>
            <button
              type="button"
              className="see-all"
              onClick={() => setGamesOpen(true)}
            >
              <span>{t(locale, "seeAll")}</span>
              <Icon name="forward" size={16} />
            </button>
          </div>
          <div className="stat-games">
            {games.slice(0, GAMES_PREVIEW).map((g) => (
              <button
                key={`${g.platform}:${g.title_id}`}
                type="button"
                className="stat-game-tile"
                onClick={() =>
                  openGame?.({
                    platform: g.platform,
                    title_id: g.title_id,
                    name: g.name,
                    icon_url: g.icon_url,
                  })
                }
              >
                <CoverImg src={g.icon_url} kind="game" className="stat-game-art" />
                <strong>{g.name || "—"}</strong>
                <p>{g.count}</p>
              </button>
            ))}
          </div>
        </section>
      )}
      {gamesOpen && (
        <GamesSheet
          games={games}
          locale={locale}
          onClose={() => setGamesOpen(false)}
        />
      )}

      {(day.length > 0 || month.length > 0) && (
        <RowsSection
          className="is-stat"
          title={t(locale, "leaders")}
          action={periodSwitch(board, setBoard, t(locale, "leaders"))}
        >
          {boardRows.length > 0 ? (
            boardRows.map((row, i) => (
              <Row
                key={row.tg_id}
                className="is-stat"
                lead={
                  <>
                    <span className="rows-rank">{i + 1}</span>
                    {faceOf(row.tg_id, row.name, 40)}
                  </>
                }
                title={row.name}
                trailing={
                  board === "month" && row.rare
                    ? `${row.count} · 💎${row.rare}`
                    : row.count
                }
                chevron={false}
                onClick={() => onOpenPerson(row.tg_id)}
              />
            ))
          ) : (
            <p className="empty">{t(locale, "emptySummary")}</p>
          )}
        </RowsSection>
      )}

      {finders.length > 0 && (
        <RowsSection className="is-stat" title={t(locale, "rareFinds")}>
          {finders.map((finder) => (
            <Row
              key={finder.tgId}
              className="is-stat"
              lead={faceOf(finder.tgId, finder.name, 40)}
              title={finder.name}
              subtitle={`${t(locale, "rarerThan")} ${RARE_FIND_PERCENT}%`}
              trailing={finder.items.length}
              onClick={() => setRareOpen(finder)}
            />
          ))}
        </RowsSection>
      )}

      {hunts.length > 0 && (
        <RowsSection className="is-stat" title={t(locale, "huntTogether")}>
          {hunts.map((hunt) => (
            <Row
              key={hunt.key}
              className="is-stat"
              lead={
                <CoverImg src={hunt.cover} kind="game" className="rows-art" />
              }
              title={hunt.name}
              subtitle={`${hunt.items.length} ${t(locale, "achievements")}`}
              trailing={hunt.people.size}
              onClick={() => setHuntOpen(hunt)}
            />
          ))}
        </RowsSection>
      )}

      {rareOpen && (
        <Sheet
          mid
          onClose={() => setRareOpen(null)}
          closeLabel={t(locale, "close")}
          noClose
        >
          <div className="sheet-content score-sheet picker-sheet stats-sheet">
            <h2>{`${t(locale, "rareFinds")} - ${rareOpen.name}`}</h2>
            <div className="stats-sheet-list">
              <AchievementRows
                items={rareOpen.items}
                revealed={revealed}
                showSecrets={showSecrets}
                detailed
                onOpen={setItem}
              />
            </div>
          </div>
        </Sheet>
      )}

      {huntOpen && (
        <Sheet
          mid
          onClose={() => setHuntOpen(null)}
          closeLabel={t(locale, "close")}
          noClose
        >
          <div className="sheet-content score-sheet picker-sheet stats-sheet">
            <h2>{`${t(locale, "huntTogether")} - ${huntOpen.name}`}</h2>
            <div className="stats-sheet-list">
              <AchievementRows
                items={huntOpen.items}
                revealed={revealed}
                showSecrets={showSecrets}
                detailed
                onOpen={setItem}
              />
            </div>
          </div>
        </Sheet>
      )}

      {item && (
        <Sheet
          mid
          onClose={() => setItem(null)}
          closeLabel={t(locale, "close")}
          noClose
        >
          <div className="sheet-unlock">
            <UnlockCard
              item={item}
              locale={locale}
              secret={Boolean(
                item.is_secret && !showSecrets && !revealed.has(feedKey(item)),
              )}
              author
              gameInCopy
              onOpenPerson={onOpenPerson}
              onReveal={onReveal}
            />
          </div>
        </Sheet>
      )}
    </>
  );
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
