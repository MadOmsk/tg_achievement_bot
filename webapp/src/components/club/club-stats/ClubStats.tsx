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
  Dropdown,
  DropdownArrow,
  Icon,
  Row,
  RowsSection,
  Sheet,
  StatsSkel,
  isOnline,
  useOpenGame,
} from "../../shared/lib";
import { UI_CONFIG } from "../../shared/constants";
import { FeedRow, UnlockCard, feedKey, veiled } from "../../person";
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

type Period = "day" | "month" | "year";

/** One row per achievement of a hunt, with everybody who earned it (owner,
 * 2026-10-07: the same achievement once, its people on it), the most shared
 * first, then the newest. */
function huntRows(items: FeedItem[]): { row: FeedItem; people: { id: number; name: string }[] }[] {
  const byAchievement = new Map<string, { row: FeedItem; people: { id: number; name: string }[] }>();
  for (const row of items) {
    const key = `${row.platform}:${row.title_id}:${row.achievement_id}`;
    const entry = byAchievement.get(key) ?? { row, people: [] };
    if (!entry.people.some((who) => who.id === row.person_id)) {
      entry.people.push({ id: row.person_id, name: row.person });
    }
    byAchievement.set(key, entry);
  }
  return [...byAchievement.values()].sort(
    (a, b) =>
      b.people.length - a.people.length ||
      (b.row.unlocked_at ?? "").localeCompare(a.row.unlocked_at ?? ""),
  );
}

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
  year,
  games,
  feed,
  online,
  monthChip,
  busy,
  revealed,
  showSecrets,
  onReveal,
  onOpenPerson,
  hideHeader,
}: {
  meId: number;
  locale: Locale;
  day: SummaryMember[];
  month: SummaryMember[];
  /** The year of the month shown, up to that month's end. */
  year?: { year: number; rows: SummaryMember[] } | null;
  games: SummaryGame[];
  monthLabel: string;
  feed: FeedItem[];
  online: OnlineMember[];
  monthChip: ReactNode;
  busy: boolean;
  revealed: Set<string>;
  showSecrets?: boolean;
  onReveal: (key: string) => void;
  onOpenPerson: (personId: number) => void;
  hideHeader?: boolean;
}) {
  const openGame = useOpenGame();
  const [gamesOpen, setGamesOpen] = useState(false);
  const [board, setBoard] = useState<Period>("day");
  const [rareOpen, setRareOpen] = useState<RareFinder | null>(null);
  const [huntOpen, setHuntOpen] = useState<Hunt | null>(null);
  const [item, setItem] = useState<FeedItem | null>(null);

  if (busy) {
    return (
      <>
        {!hideHeader && (
          <header className="page-head is-split">
            <h1>{t(locale, "stats")}</h1>
            {monthChip}
          </header>
        )}
        <StatsSkel head={false} />
      </>
    );
  }

  if (day.length === 0 && month.length === 0 && feed.length === 0) {
    return (
      <>
        {!hideHeader && (
          <header className="page-head is-split">
            <h1>{t(locale, "stats")}</h1>
            {monthChip}
          </header>
        )}
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
    cur.people.set(row.person_id, row.person);
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
  const yearRows = year?.rows ?? [];
  const boardRows = board === "day" ? day : board === "month" ? month : yearRows;
  const periodLabel = (period: Period) =>
    period === "day" ? t(locale, "boardDay") : period === "month" ? t(locale, "boardMonth") : t(locale, "boardYear");

  const periodSwitch = (
    value: Period,
    onChange: (next: Period) => void,
    label: string,
  ) => (
    // A dropdown, as every pick in the app (owner, 2026-10-07), not a toggle.
    <Dropdown
      className="dd-trigger period-pick"
      value={value}
      options={((year ? ["day", "month", "year"] : ["day", "month"]) as Period[]).map((period) => ({
        value: period,
        label: periodLabel(period),
      }))}
      onChange={onChange}
      label={label}
      trigger={
        <>
          {periodLabel(value)}
          <DropdownArrow />
        </>
      }
    />
  );

  const faceOf = (personId: number, name: string, size: number) => (
    <Avatar
      name={name}
      personId={personId}
      online={isOnline(online.find((m) => m.person_id === personId) ?? {})}
      platform={online.find((m) => m.person_id === personId && isOnline(m))?.platform}
      size={size}
    />
  );

  return (
    <>
      {!hideHeader && (
        <header className="page-head is-split">
          <h1>{t(locale, "stats")}</h1>
          {monthChip}
        </header>
      )}
      <section className="stat-hero">
        <StatTile
          label={t(locale, "today")}
          club={clubDay}
          mine={mineDay}
          hint={t(locale, "youShare")}
        />
        <StatTile
          label={t(locale, "thisMonth")}
          club={clubMonth}
          mine={mineMonth}
          hint={t(locale, "youShare")}
        />
        {year && yearRows.length > 0 && (
          <StatTile
            label={t(locale, "thisYear")}
            club={sumCounts(yearRows)}
            mine={pickCount(yearRows, me, new Map())}
            hint={t(locale, "youShare")}
          />
        )}
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
                key={row.person_id}
                className="is-stat"
                lead={
                  <>
                    <span className="rows-rank">{i + 1}</span>
                    {faceOf(row.person_id, row.name, 40)}
                  </>
                }
                title={row.name}
                trailing={
                  board !== "day" && row.rare
                    ? `${row.count} · 💎${row.rare}`
                    : row.count
                }
                chevron={false}
                onClick={() => onOpenPerson(row.person_id)}
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
              key={finder.personId}
              className="is-stat"
              lead={faceOf(finder.personId, finder.name, 40)}
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
              subtitle={`${huntRows(hunt.items).length} ${t(locale, "achievements")}`}
              trailing={hunt.people.size}
              onClick={() => setHuntOpen(hunt)}
            />
          ))}
        </RowsSection>
      )}

      {rareOpen && (
        <Sheet mid onClose={() => setRareOpen(null)} title={`${t(locale, "rareFinds")} · ${rareOpen.name}`}>
          <div className="sheet-content score-sheet picker-sheet stats-sheet">
            <div className="stats-sheet-list">
              <AchievementRows
                items={rareOpen.items}
                revealed={revealed}
                showSecrets={showSecrets}
                detailed
                onOpen={setItem}
                onReveal={onReveal}
              />
            </div>
          </div>
        </Sheet>
      )}

      {huntOpen && (
        <Sheet mid onClose={() => setHuntOpen(null)} title={t(locale, "huntTogether")}>
          <div className="sheet-content stats-sheet hunt-page">
            <p className="hunt-page-lead">{huntOpen.name}</p>
            <div className="feed-day hunt-list">
              {huntRows(huntOpen.items).map(({ row, people }) => (
                <FeedRow
                  key={feedKey(row)}
                  row={row}
                  secret={veiled(row, feedKey(row), revealed, showSecrets)}
                  people={people}
                  onOpen={setItem}
                  onToggleReveal={onReveal}
                />
              ))}
            </div>
          </div>
        </Sheet>
      )}

      {item && (
        <Sheet mid onClose={() => setItem(null)} title={item.game ?? undefined}>
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
        {pct}% <span>{hint}</span>
      </small>
    </div>
  );
}
