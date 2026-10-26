import { Suspense, lazy, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import {
  gameApi,
  type GameCard,
  type GameDlc,
  type GameEdition,
  type GameNews,
  type GamePage as GamePageData,
  type GamePlatform,
  type GamePlayer,
  type GameRef,
} from "../../../api";
import { t, type Locale } from "../../../i18n";
import {
  Avatar,
  CoverImg,
  Icon,
  Row,
  RowsSkel,
  Sheet,
  openImage,
  tick,
  useBackHandler,
} from "../../shared/lib";
import { HandleName } from "../../shared/lib/handle-name/HandleName";
import { announceFavoritesChanged } from "../../club/favorite-games";
import { NewsPage } from "../news-page/NewsPage";
import { openUrl } from "../rich-text/RichText";
import "./GamePage.css";

// The achievements of one list: the game page that came before this one,
// kept and opened over it.
const TitleSheet = lazy(() =>
  import("../title-sheet/TitleSheet").then((m) => ({ default: m.TitleSheet })),
);

// A strip shows this many; the rest are on its own page («Все»).
const STRIP_SHOWN = 10;

const CONSOLE_SHORT: Record<string, string> = {
  series: "Series X|S",
  one: "Xbox One",
  "360": "Xbox 360",
  ps5: "PS5",
  ps4: "PS4",
  ps3: "PS3",
  vita: "PS Vita",
  steam: "Steam",
};
const PC_STORE: Record<string, string> = {
  xbox: "Xbox PC",
  egs: "Epic",
  gog: "GOG",
};

function platformName(row: { console: string; store: string }): string {
  if (row.console === "pc") return PC_STORE[row.store] ?? "PC";
  return CONSOLE_SHORT[row.console] ?? row.console;
}

function listConsole(platform: string): string {
  if (platform === "steam") return "Steam";
  if (platform === "psn") return "PlayStation";
  if (platform === "xbox_360") return "Xbox 360";
  return "Xbox";
}

function dayOf(iso: string | null | undefined, locale: Locale, withYear = true): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(locale === "en" ? "en-GB" : "ru-RU", {
    day: "numeric",
    month: "long",
    year: withYear ? "numeric" : undefined,
  });
}

function hoursOf(value: number | null): string {
  if (value == null) return "—";
  return value >= 10 ? String(Math.round(value)) : String(Math.round(value * 2) / 2);
}

function yearsOf(game: GamePageData["game"]): string {
  if (!game.year) return "";
  return game.last_year && game.last_year !== game.year
    ? `${game.year}–${game.last_year}`
    : String(game.year);
}

function nameOf(card: { name: string; name_ru: string | null }, locale: Locale): string {
  return (locale === "ru" && card.name_ru) || card.name;
}

/** How another game relates to this one, from this game's side. */
function relationLabel(kind: string, forward: boolean): Parameters<typeof t>[1] {
  if (kind === "contains") return forward ? "gpPart" : "gpCompilation";
  if (kind === "remaster_of") return forward ? "gpOriginal" : "gpRemaster";
  if (kind === "remake_of") return forward ? "gpOriginal" : "gpRemake";
  if (kind === "vr_of") return forward ? "gpOriginal" : "gpVr";
  if (kind === "enhanced_of") return forward ? "gpOriginal" : "gpEnhanced";
  return "gpRelated";
}

/** Each platform once, a PC per store, with the first store page found. */
function platformChips(platforms: GamePlatform[]): { label: string; url: string | null }[] {
  const chips: { label: string; url: string | null }[] = [];
  for (const row of platforms) {
    const label = platformName(row);
    const found = chips.find((chip) => chip.label === label);
    if (found) found.url = found.url ?? row.url;
    else chips.push({ label, url: row.url });
  }
  return chips;
}

/** Items by the year they came out, the years in order (`newest` first when
 * asked), none last. */
function byYear<T>(
  items: T[],
  yearOf: (item: T) => string | null | undefined,
  newest = false,
): [string, T[]][] {
  const groups = new Map<string, T[]>();
  for (const item of items) {
    const year = yearOf(item)?.slice(0, 4) || "";
    groups.set(year, [...(groups.get(year) ?? []), item]);
  }
  return [...groups.entries()].sort(([a], [b]) => {
    if (!a || !b) return a ? -1 : b ? 1 : 0;
    return newest ? b.localeCompare(a) : a.localeCompare(b);
  });
}

type ListOpen = "screens" | "news" | "dlc" | "editions" | { series: number } | null;

/**
 * A game's own page (#147, stage 5; owner, 2026-10-25/26): everything the
 * catalog knows of it — its picture, name, years, studio, score and platforms;
 * the reader's progress and who else played it; its news; the hours; its
 * story and facts; screenshots, DLC, editions, its series and related games,
 * each strip with its whole list a tap away. The achievements of a list open
 * over it (the page that came before, kept for them). A game of the series
 * opens in place; the phone's back steps back through them.
 */
export function GamePage({
  game,
  data,
  locale,
  showSecrets,
  meId,
  onClose,
}: {
  game: GameRef;
  data: string;
  locale: Locale;
  showSecrets?: boolean;
  meId: number;
  onClose: () => void;
}) {
  const [stack, setStack] = useState<GameRef[]>([game]);
  const current = stack[stack.length - 1];
  const key = current.game_id ? `g${current.game_id}` : `${current.platform}:${current.title_id}`;
  const [page, setPage] = useState<GamePageData | null>(null);
  const [failed, setFailed] = useState(false);
  const [favorite, setFavorite] = useState(false);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [achievementsOf, setAchievementsOf] = useState<GameRef | null>(null);
  const [news, setNews] = useState<GameNews | null>(null);
  const [listOpen, setListOpen] = useState<ListOpen>(null);
  const [scrolled, setScrolled] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);

  const back = () => {
    if (stack.length > 1) setStack((all) => all.slice(0, -1));
    else onClose();
  };
  useBackHandler(true, back, `gpage:${key}:${stack.length}`);

  useEffect(() => {
    let cancelled = false;
    setPage(null);
    setFailed(false);
    setAboutOpen(false);
    setListOpen(null);
    scroller.current?.scrollTo(0, 0);
    gameApi
      .fetchGamePage(data, {
        gameId: current.game_id,
        platform: current.platform,
        titleId: current.title_id,
        personId: current.person?.person_id,
      })
      .then((answer) => {
        if (cancelled) return;
        setPage(answer);
        setFavorite(answer.favorite);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [data, key, current]);

  const toggleFavorite = () => {
    if (!page) return;
    const next = !favorite;
    setFavorite(next);
    tick();
    gameApi
      .setFavorite(data, page.game.game_id, next)
      .then(announceFavoritesChanged)
      .catch(() => setFavorite(!next));
  };

  const openGameCard = (card: GameCard) => {
    if (page && card.game_id === page.game.game_id) return;
    setListOpen(null);
    setStack((all) => [...all, { game_id: card.game_id, platform: "", title_id: "", name: card.name }]);
  };

  const openAchievements = (platform: string, titleId: string, person?: GamePlayer | null) => {
    setAchievementsOf({
      platform,
      title_id: titleId,
      name: page?.game.name,
      icon_url: page?.art.poster,
      person:
        person && person.person_id !== meId
          ? { person_id: person.person_id, name: person.name }
          : (current.person ?? null),
    });
  };

  const title = page ? nameOf(page.game, locale) : (current.name ?? "");
  const hero = page?.art.hero ?? page?.art.header ?? null;
  const seriesOpen =
    listOpen && typeof listOpen === "object"
      ? page?.series.find((one) => one.series_id === listOpen.series)
      : undefined;

  return (
    <div
      className="gpage"
      ref={scroller}
      data-no-pull
      onScroll={(event) => setScrolled(event.currentTarget.scrollTop > 220)}
    >
      <header className={scrolled ? "gp-bar is-solid" : "gp-bar"}>
        <button type="button" className="gp-round" onClick={back} aria-label={t(locale, "back")}>
          <Icon name="back" size={22} />
        </button>
        <strong className="gp-bar-title">{scrolled ? title : ""}</strong>
        {page && (
          <button
            type="button"
            className={["gp-round", "gp-fav", favorite ? "is-on" : "", scrolled ? "is-bare" : ""]
              .filter(Boolean)
              .join(" ")}
            onClick={toggleFavorite}
            aria-pressed={favorite}
            aria-label={t(locale, favorite ? "gpFavorited" : "gpFavorite")}
          >
            <Icon name="heart" size={20} filled={favorite} />
            {!scrolled && <span>{t(locale, favorite ? "gpFavorited" : "gpFavorite")}</span>}
          </button>
        )}
      </header>

      <div className="gp-hero">
        {hero && <img src={hero} alt="" onClick={() => openImage(hero)} />}
      </div>

      <div className="gp-ident">
        <CoverImg src={page?.art.poster ?? current.icon_url ?? null} kind="game" className="gp-poster" />
        <div className="gp-ident-copy">
          <h1>{title}</h1>
          {page && (
            <p className="gp-meta">
              {[yearsOf(page.game), page.game.developer].filter(Boolean).join(" · ")}
            </p>
          )}
          {page && (
            <div className="gp-chips">
              {page.hltb?.score ? (
                <span className="gp-chip is-score">★ {page.hltb.score}</span>
              ) : null}
              {platformChips(page.platforms).map((chip) =>
                chip.url ? (
                  <button
                    key={chip.label}
                    type="button"
                    className="gp-chip is-link"
                    onClick={() => openUrl(chip.url!)}
                  >
                    {chip.label}
                  </button>
                ) : (
                  <span key={chip.label} className="gp-chip">
                    {chip.label}
                  </span>
                ),
              )}
              {page.hltb?.rating && <span className="gp-chip">{page.hltb.rating}</span>}
            </div>
          )}
        </div>
      </div>

      {failed && <p className="empty gp-pad">{t(locale, "error")}</p>}
      {!page && !failed && (
        <div className="gp-pad">
          <RowsSkel />
        </div>
      )}

      {page && (
        <>
          <Progress page={page} locale={locale} onOpen={openAchievements} />

          {page.news.length > 0 && (
            <section className="gp-section">
              <SectionHead
                title={t(locale, "gpNews")}
                locale={locale}
                onAll={page.news.length > 1 ? () => setListOpen("news") : undefined}
              />
              <NewsRow post={page.news[0]} locale={locale} onOpen={setNews} />
            </section>
          )}

          {page.hltb && (page.hltb.main || page.hltb.extra || page.hltb.completionist) && (
            <section className="gp-section">
              <SectionHead
                title={t(locale, "gpHours")}
                locale={locale}
                link={{ label: "HowLongToBeat", onClick: () => openUrl(page.hltb!.url) }}
              />
              <div className="gp-hours">
                {(
                  [
                    ["gpMain", page.hltb.main],
                    ["gpExtra", page.hltb.extra],
                    ["gpFull", page.hltb.completionist],
                  ] as const
                ).map(([label, value]) => (
                  <div key={label}>
                    <p>{t(locale, label)}</p>
                    <strong>
                      {hoursOf(value)}
                      {value != null && <em>{t(locale, "gpHoursUnit")}</em>}
                    </strong>
                  </div>
                ))}
              </div>
            </section>
          )}

          <section className="gp-section">
            <SectionHead title={t(locale, "gpAbout")} locale={locale} />
            {page.description && (
              <>
                <p
                  className={aboutOpen ? "gp-desc is-open" : "gp-desc"}
                  lang={page.description.lang}
                >
                  {page.description.text}
                </p>
                {page.description.text.length > 280 && (
                  <button type="button" className="gp-more" onClick={() => setAboutOpen((v) => !v)}>
                    {t(locale, aboutOpen ? "gpReadLess" : "gpReadMore")}
                  </button>
                )}
              </>
            )}
            <Facts page={page} locale={locale} />
          </section>

          {page.screenshots.length > 0 && (
            <section className="gp-section">
              <SectionHead
                title={t(locale, "gpScreens")}
                count={page.screenshots.length}
                locale={locale}
                onAll={page.screenshots.length > 2 ? () => setListOpen("screens") : undefined}
              />
              <div className="gp-strip">
                {page.screenshots.slice(0, STRIP_SHOWN).map((shot) => (
                  <button
                    key={shot}
                    type="button"
                    className="gp-shot"
                    onClick={() => openImage(shot, page.screenshots)}
                  >
                    <img src={shot} alt="" loading="lazy" />
                  </button>
                ))}
              </div>
            </section>
          )}

          {page.dlcs.length > 0 && (
            <section className="gp-section">
              <SectionHead
                title={t(locale, "gpDlc")}
                count={page.dlcs.length}
                locale={locale}
                onAll={page.dlcs.length > 2 ? () => setListOpen("dlc") : undefined}
              />
              <div className="gp-strip">
                {page.dlcs.slice(0, STRIP_SHOWN).map((dlc) => (
                  <DlcTile key={dlc.name} dlc={dlc} fallback={hero} locale={locale} />
                ))}
              </div>
            </section>
          )}

          {page.editions.length > 0 && (
            <section className="gp-section">
              <SectionHead
                title={t(locale, "gpEditions")}
                count={page.editions.length}
                locale={locale}
                onAll={page.editions.length > 3 ? () => setListOpen("editions") : undefined}
              />
              <div className="gp-strip">
                {page.editions.slice(0, STRIP_SHOWN).map((edition) => (
                  <EditionTile key={edition.name} edition={edition} fallback={page.art.poster} />
                ))}
              </div>
            </section>
          )}

          {page.series.map((series) =>
            series.games.length > 1 ? (
              <section key={series.series_id} className="gp-section">
                <SectionHead
                  title={`${t(locale, "gpSeries")} «${series.name}»`}
                  count={series.games.length}
                  locale={locale}
                  onAll={
                    series.games.length > 3
                      ? () => setListOpen({ series: series.series_id })
                      : undefined
                  }
                />
                <div className="gp-strip">
                  {series.games.slice(0, STRIP_SHOWN).map((card) => (
                    <GameTile
                      key={card.game_id}
                      card={card}
                      locale={locale}
                      on={card.game_id === page.game.game_id}
                      onOpen={openGameCard}
                    />
                  ))}
                </div>
              </section>
            ) : null,
          )}

          {page.related.length > 0 && (
            <section className="gp-section">
              <SectionHead title={t(locale, "gpRelated")} locale={locale} />
              <div className="gp-strip">
                {page.related.map((row) => (
                  <GameTile
                    key={`${row.kind}:${row.game.game_id}`}
                    card={row.game}
                    locale={locale}
                    caption={t(locale, relationLabel(row.kind, row.forward))}
                    onOpen={openGameCard}
                  />
                ))}
              </div>
            </section>
          )}
        </>
      )}

      {page && listOpen === "screens" && (
        <Sheet title={t(locale, "gpScreens")} onClose={() => setListOpen(null)}>
          <div className="gp-shots-grid">
            {page.screenshots.map((shot) => (
              <button
                key={shot}
                type="button"
                className="gp-shot"
                onClick={() => openImage(shot, page.screenshots)}
              >
                <img src={shot} alt="" loading="lazy" />
              </button>
            ))}
          </div>
        </Sheet>
      )}
      {page && listOpen === "news" && (
        <Sheet title={t(locale, "gpNews")} onClose={() => setListOpen(null)}>
          {page.news.map((post) => (
            <NewsRow key={`${post.appid}:${post.gid}`} post={post} locale={locale} onOpen={setNews} />
          ))}
        </Sheet>
      )}
      {page && listOpen === "dlc" && (
        <Sheet title={t(locale, "gpDlc")} onClose={() => setListOpen(null)}>
          {byYear(page.dlcs, (dlc) => dlc.release_date).map(([year, dlcs]) => (
            <YearGroup key={year} year={year}>
              {dlcs.map((dlc) => (
                <Row
                  key={dlc.name}
                  lead={<CoverImg src={dlc.image ?? hero} kind="game" className="rows-art gp-row-wide" />}
                  title={dlc.name}
                  subtitle={dlc.hours ? `${hoursOf(dlc.hours)} ${t(locale, "gpHoursUnit")}` : undefined}
                />
              ))}
            </YearGroup>
          ))}
        </Sheet>
      )}
      {page && listOpen === "editions" && (
        <Sheet title={t(locale, "gpEditions")} onClose={() => setListOpen(null)}>
          {page.editions.map((edition) => (
            <Row
              key={edition.name}
              lead={
                <CoverImg
                  src={edition.cover ?? page.art.poster}
                  kind="game"
                  className="rows-art is-cover"
                />
              }
              title={edition.name}
            />
          ))}
        </Sheet>
      )}
      {page && seriesOpen && (
        <Sheet title={seriesOpen.name} onClose={() => setListOpen(null)}>
          {byYear(seriesOpen.games, (card) => (card.year ? String(card.year) : null), true).map(
            ([year, cards]) => (
              <YearGroup key={year} year={year}>
                {cards.map((card) => (
                  <Row
                    key={card.game_id}
                    lead={<CoverImg src={card.poster} kind="game" className="rows-art is-cover" />}
                    title={nameOf(card, locale)}
                    onClick={card.game_id === page.game.game_id ? undefined : () => openGameCard(card)}
                  />
                ))}
              </YearGroup>
            ),
          )}
        </Sheet>
      )}

      {achievementsOf &&
        createPortal(
          <Suspense fallback={null}>
            <TitleSheet
              game={achievementsOf}
              data={data}
              locale={locale}
              showSecrets={showSecrets}
              meId={meId}
              onClose={() => setAchievementsOf(null)}
            />
          </Suspense>,
          document.body,
        )}
      {news && page && (
        <NewsPage
          post={news}
          locale={locale}
          game={{ name: title, icon_url: page.art.poster }}
          onClose={() => setNews(null)}
        />
      )}
    </div>
  );
}

function SectionHead({
  title,
  count,
  locale,
  onAll,
  link,
}: {
  title: string;
  count?: number;
  locale: Locale;
  /** The whole list, on a page of its own. */
  onAll?: () => void;
  link?: { label: string; onClick: () => void };
}) {
  return (
    <h2 className="gp-head">
      <span>
        {title}
        {count != null && <small>{count}</small>}
      </span>
      {onAll && (
        <button type="button" className="see-all" onClick={onAll}>
          <span>{t(locale, "gpAll")}</span>
          <Icon name="forward" size={16} />
        </button>
      )}
      {link && (
        <button type="button" className="see-all" onClick={link.onClick}>
          <span>{link.label}</span>
        </button>
      )}
    </h2>
  );
}

function YearGroup({ year, children }: { year: string; children: ReactNode }) {
  return (
    <div className="gp-year">
      {year && <p className="feed-day-label">{year}</p>}
      {children}
    </div>
  );
}

function NewsRow({
  post,
  locale,
  onOpen,
}: {
  post: GameNews;
  locale: Locale;
  onOpen: (post: GameNews) => void;
}) {
  return (
    <button type="button" className="gp-news-row" onClick={() => onOpen(post)}>
      <span className={post.kind === "patch" ? "gp-kind is-patch" : "gp-kind"}>
        {t(locale, post.kind === "patch" ? "newsPatch" : "newsPost")}
      </span>
      <strong>{post.title}</strong>
      <time>{dayOf(post.date, locale, false)}</time>
    </button>
  );
}

function Facts({ page, locale }: { page: GamePageData; locale: Locale }) {
  const days = page.platforms.map((row) => row.release_date).filter(Boolean) as string[];
  const released = days.length ? [...days].sort()[0] : null;
  const rows: [Parameters<typeof t>[1], string][] = [];
  if (released) rows.push(["gpReleased", dayOf(released, locale)]);
  if (page.game.developer)
    rows.push([
      "gpDeveloper",
      page.game.developer + (page.game.more_developers ? ` ${t(locale, "gpAndOthers")}` : ""),
    ]);
  if (page.game.publisher)
    rows.push([
      "gpPublisher",
      page.game.publisher + (page.game.more_publishers ? ` ${t(locale, "gpAndOthers")}` : ""),
    ]);
  if (page.genres.length) rows.push(["gpGenre", page.genres.join(", ")]);
  if (!rows.length) return null;
  return (
    <div className="gp-facts">
      {rows.map(([label, value]) => (
        <div key={label}>
          <span>{t(locale, label)}</span>
          <b>{value}</b>
        </div>
      ))}
    </div>
  );
}

/** The reader's progress (or that of the person it was opened from) as the
 * profile draws a game's — a count and a bar —, the way into the
 * achievements, and the faces of whoever else here played it. */
function Progress({
  page,
  locale,
  onOpen,
}: {
  page: GamePageData;
  locale: Locale;
  onOpen: (platform: string, titleId: string, person?: GamePlayer | null) => void;
}) {
  const mine = page.progress;
  const firstList = page.lists[0];
  if (!mine && !firstList && page.players.length === 0) return null;
  const total = mine?.total ?? null;
  const pct = mine && total ? Math.min(100, Math.round((100 * mine.count) / total)) : null;
  const done = pct === 100;
  const open = () => {
    if (mine) onOpen(mine.platform, mine.title_id, mine);
    else if (firstList) onOpen(firstList.platform, firstList.title_id);
  };
  return (
    <section className="gp-section">
      <SectionHead
        title={t(locale, page.viewed_is_me ? "gpProgressMine" : "gpProgressTheirs")}
        locale={locale}
      />
      <div className="gp-card">
        <button
          type="button"
          className={done ? "gp-mine is-done" : "gp-mine"}
          onClick={open}
          disabled={!mine && !firstList}
        >
          <span className="gp-mine-copy">
            <span className="gp-mine-line">
              <strong>
                {mine
                  ? total
                    ? `${mine.count} ${t(locale, "gpOf")} ${total}`
                    : String(mine.count)
                  : t(locale, "gpNotPlayed")}
              </strong>
              {pct != null && <b>{pct}%</b>}
            </span>
            {mine && total ? (
              <span className="played-bar" aria-hidden>
                <span className="played-bar-fill" style={{ width: `${pct}%` }} />
              </span>
            ) : null}
            <span className="gp-mine-sub">
              {mine
                ? [
                    listConsole(mine.platform),
                    mine.last ? `${t(locale, "gpLast")} ${dayOf(mine.last, locale)}` : null,
                  ]
                    .filter(Boolean)
                    .join(" · ")
                : t(locale, "gpAchievements")}
            </span>
          </span>
          <Icon name="forward" size={18} />
        </button>
        {page.players.length > 0 && (
          <div className="gp-faces">
            {page.players.map((player) => (
              <button
                key={player.person_id}
                type="button"
                className="gp-face"
                onClick={() => onOpen(player.platform, player.title_id, player)}
              >
                <Avatar name={player.name} personId={player.person_id} size={44} />
                <span className="gp-face-name">
                  <HandleName text={player.name} />
                </span>
                <span>{player.total ? `${player.count}/${player.total}` : player.count}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function GameTile({
  card,
  locale,
  on,
  caption,
  onOpen,
}: {
  card: GameCard;
  locale: Locale;
  on?: boolean;
  caption?: string;
  onOpen: (card: GameCard) => void;
}) {
  return (
    <button type="button" className={on ? "gp-tile is-on" : "gp-tile"} onClick={() => onOpen(card)}>
      <CoverImg src={card.poster} kind="game" className="gp-tile-art" />
      {caption && <small>{caption}</small>}
      <strong>{nameOf(card, locale)}</strong>
      {card.year && <span>{card.year}</span>}
    </button>
  );
}

function DlcTile({ dlc, fallback, locale }: { dlc: GameDlc; fallback: string | null; locale: Locale }) {
  return (
    <div className="gp-dlc">
      <CoverImg src={dlc.image ?? fallback} kind="game" className="gp-dlc-art" />
      <strong>{dlc.name}</strong>
      <span>
        {[
          dlc.release_date?.slice(0, 4),
          dlc.hours ? `${hoursOf(dlc.hours)} ${t(locale, "gpHoursUnit")}` : null,
        ]
          .filter(Boolean)
          .join(" · ")}
      </span>
    </div>
  );
}

function EditionTile({ edition, fallback }: { edition: GameEdition; fallback: string | null }) {
  return (
    <div className="gp-edition">
      <CoverImg src={edition.cover ?? fallback} kind="game" className="gp-edition-art" />
      <strong>{edition.name}</strong>
    </div>
  );
}
