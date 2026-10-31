import { useEffect, useState } from "react";
import { gameApi, type GameCard, type GameHltb, type GamePage as GamePageData, type GameRef } from "../../api";
import { useApp } from "../../app/context";
import { rememberGameArt, useArtTheme } from "../../app/artTheme";
import { openExternal } from "../../app/env";
import { useLoad } from "../../app/useLoad";
import { recall, remember } from "../../core/game-cache";
import { tick } from "../../core/haptic";
import { dayLabel, num, whenLabel, type TranslationKey } from "../../i18n";
import { consoleLabel } from "../../parts/platforms";
import { FAVORITES_CHANGED } from "../../parts/FollowButton";
import { DoneMark } from "../../parts/DoneMark";
import { PlatformPicker } from "../../parts/PlatformPicker";
import type { NewsItem } from "../../api";
import { Button, Chip, Empty, Section } from "../../ui/Controls";
import { Face } from "../../ui/Face";
import { Icon } from "../../ui/Icon";
import { BarAction, Page } from "../../ui/Page";
import { MediaTile } from "./MediaTile";
import { DlcRow } from "./DlcPage";
import { cleanName, tidyVideos } from "./names";
import { Cover } from "../../ui/Pic";
import type { Media } from "../../ui/Viewer";
import { Wave } from "../../ui/Wave";
import { GoMark } from "../../ui/GoMark";
import "./Game.css";

const RELATION: Record<string, [TranslationKey, TranslationKey]> = {
  remaster_of: ["gpRemaster", "gpOriginal"],
  remake_of: ["gpRemake", "gpOriginal"],
  vr_of: ["gpVr", "gpOriginal"],
  contains: ["gpPart", "gpCompilation"],
  enhanced_of: ["gpEnhanced", "gpOriginal"],
};

function refKey(ref: GameRef): string {
  // Whose progress it shows is part of the page: a game opened from two
  // people's posts is two pages.
  const who = ref.person?.person_id ?? "";
  return ref.game_id ? `g${ref.game_id}:${who}` : `${ref.platform}:${ref.title_id}:${who}`;
}

const GALLERY_SHOWN = 8;
const DLC_SHOWN = 3;

export function GamePage({ gameRef, onClose, layer }: { gameRef: GameRef; onClose: () => void; layer: string }) {
  const { data, tr, open } = useApp();
  const key = refKey(gameRef);
  const page = useLoad<GamePageData>(
    `game:${key}`,
    async () => {
      const res = await gameApi.fetchGamePage(data, {
        gameId: gameRef.game_id,
        platform: gameRef.platform,
        titleId: gameRef.title_id,
        personId: gameRef.person?.person_id,
      });
      remember("game", key, res);
      return res;
    },
    recall<GamePageData>("game", key),
  );
  const g = page.data;
  // On its way: asked again until the translation is in, the blur then goes.
  const translating = g?.translating ?? false;
  useEffect(() => {
    if (!translating) return;
    const id = window.setTimeout(page.reload, 3000);
    return () => window.clearTimeout(id);
  });
  // The head takes the gallery's newest picture (owner, 2026-10-29; the
  // server sends them newest first): a frame of the game itself, no title
  // written on it; the store's art when there is none.
  const hero = g?.screenshots[0] || g?.art.hero || g?.art.header || g?.art.poster || null;
  const art = g?.art.hero || g?.art.header || g?.art.poster;
  const theme = useArtTheme(art);
  if (g && art) {
    rememberGameArt(
      [`g${g.game.game_id}`, g.game.name, `${gameRef.platform}:${gameRef.title_id}`, ...g.lists.map((l) => `${l.platform}:${l.title_id}`)],
      art,
    );
  }
  const name = g?.game.name ?? gameRef.name ?? "";
  const ready = Boolean(g) && (theme.settled || !art);

  return (
    <Page title={name} onBack={onClose} hero layer={layer} className="game-page" style={ready ? theme.style : undefined}>
      <div className="gp-hero">
        {hero ? <img src={hero} alt="" /> : <span className={`gp-hero-empty${g ? "" : " skel"}`} />}
      </div>
      {!ready && !page.error && <GameSkeleton name={name} />}
      {!g && page.error ? (
        <Empty icon="refresh" title={tr("loadFailed")} action={<Button variant="tonal" onClick={page.reload}>{tr("retry")}</Button>} />
      ) : null}
      {g && ready && (
        <div className="gp-body">
          <GameBody g={g} setPage={page.set} open={open} />
        </div>
      )}
    </Page>
  );
}

/** The page's own shape while it loads: the head with what the tap already
 * knew (the name, the cover), then the chips, the progress card and a list. */
// The poster stays a placeholder until the page answers: the feed's icon of
// the list is often another picture, and it would be swapped a moment later.
function GameSkeleton({ name }: { name: string }) {
  return (
    <div className="gp-skel" aria-hidden="true">
      <div className="gp-head">
        <span className="gp-poster skel" />
        <div className="gp-titles">
          {name ? <h1 className="gp-title clamp-3">{name}</h1> : <span className="skel skel-line" style={{ width: "80%", height: 22 }} />}
          <span className="skel skel-line gp-sub" style={{ width: "70%" }} />
          <div className="gp-chips gp-head-chips">
            {[74, 52, 64, 58].map((w) => (
              <span key={w} className="skel gp-skel-head-chip" style={{ width: w }} />
            ))}
          </div>
        </div>
      </div>
      <div className="gp-chips">
        {[110, 90].map((w) => (
          <span key={w} className="skel gp-skel-chip" style={{ width: w }} />
        ))}
      </div>
      <div className="gp-progress gp-skel-card">
        <span className="skel skel-line" style={{ width: 110 }} />
        <span className="gp-skel-row">
          <span className="skel gp-skel-num" />
          <span className="skel gp-skel-pct" />
        </span>
        <span className="skel gp-skel-wave" />
        <span className="skel skel-line" style={{ width: 140 }} />
      </div>
      <div className="gp-skel-list">
        <span className="skel skel-line" style={{ width: 120, height: 18 }} />
        {[0, 1, 2].map((i) => (
          <span key={i} className="skel gp-skel-item" />
        ))}
      </div>
    </div>
  );
}

function years(g: GamePageData["game"]): string {
  if (!g.year) return "";
  return g.last_year && g.last_year !== g.year ? `${g.year}–${g.last_year}` : String(g.year);
}

function GameBody({
  g,
  setPage,
  open,
}: {
  g: GamePageData;
  setPage: (p: GamePageData) => void;
  open: ReturnType<typeof useApp>["open"];
}) {
  const { data, tr, locale, me, toast } = useApp();
  const [story, setStory] = useState(false);
  const [allNews, setAllNews] = useState(false);
  const [fav, setFav] = useState({ on: g.favorite, count: g.favorites });
  const [busy, setBusy] = useState(false);
  const [pickedList, setPickedList] = useState<string | null>(null);
  const videos = tidyVideos(g.videos ?? [], [g.game.name, g.game.name_ru, ...g.lists.map((l) => l.name)]);
  const gallery: Media[] = [...videos, ...g.screenshots];

  const studio = [
    g.game.developer && `${g.game.developer}${g.game.more_developers ? ` ${tr("gpAndOthers")}` : ""}`,
    g.game.publisher && g.game.publisher !== g.game.developer && g.game.publisher,
  ]
    .filter(Boolean)
    .join(" · ");
  // A game played on several platforms: one list's progress at a time, the
  // most earned first (two lists are never summed).
  // A game played on several platforms: one list at a time, the most earned
  // first (two lists are never summed).
  const lead = g.progress;
  const played = lead?.lists ?? [];
  const picked = played.find((l) => `${l.platform}:${l.title_id}` === pickedList);
  const progress = lead && picked ? { ...lead, ...picked } : lead;
  const done = Boolean(progress?.total && progress.count >= progress.total);
  const list = progress
    ? { platform: progress.platform, title_id: progress.title_id, name: g.game.name, total: progress.total, icon_url: null }
    : g.lists[0];
  const whose = progress && !g.viewed_is_me ? { id: progress.person_id, name: progress.name } : null;
  const released = g.platforms.map((p) => p.release_date).filter(Boolean).sort()[0] ?? null;
  // The newest first (owner, 2026-10-29): what came out last is what is asked about.
  const dlcs = [...g.dlcs].sort((a, b) => (b.release_date ?? "").localeCompare(a.release_date ?? ""));
  const editions = [...g.editions].sort((a, b) => a.name.length - b.name.length);
  // What an add-on's name opens with and is no part of its own: the game's names.
  const gameNames = [g.game.name, g.game.name_ru, ...g.lists.map((l) => l.name)];

  const openList = (personId?: number, personName?: string) => {
    if (!list) return;
    open({
      kind: "achievements",
      platform: list.platform,
      titleId: list.title_id,
      name: g.game.name,
      cover: g.art.poster,
      person: personId ? { id: personId, name: personName ?? "" } : whose,
      lists: played.length > 1 ? played : undefined,
    });
  };

  const toggleFav = async () => {
    setBusy(true);
    try {
      const res = await gameApi.setFavorite(data, g.game.game_id, !fav.on);
      setFav({ on: res.favorite, count: res.favorites });
      setPage({ ...g, favorite: res.favorite, favorites: res.favorites });
      window.dispatchEvent(new Event(FAVORITES_CHANGED));
    } catch {
      toast(tr("somethingWrong"), "error");
    } finally {
      setBusy(false);
    }
  };

  const openGame = (card: GameCard) => {
    tick();
    open({ kind: "game", ref: { game_id: card.game_id, platform: "", title_id: "", name: card.name } });
  };

  const others = g.players.filter((p) => p.person_id !== (progress?.person_id ?? me.person_id));
  // The heart lives in the page's bar, opposite the way back, over the art
  // and after it alike (owner, 2026-10-27).
  const heart = (
    <button
      type="button"
      className={`gp-fav${fav.on ? " gp-fav-on" : ""}`}
      aria-label={fav.on ? tr("gpFavorited") : tr("gpFavorite")}
      aria-pressed={fav.on}
      disabled={busy}
      onClick={() => void toggleFav()}
    >
      <span className="gp-fav-shape shape-cookie9">
        <Icon name="heart" size={20} filled={fav.on} />
      </span>
      {/* How many keep it: the number beside the heart. */}
      {fav.count > 0 && <b className="gp-fav-count t-num">{fav.count}</b>}
    </button>
  );
  return (
    <>
      <BarAction>{heart}</BarAction>
      <div className="gp-head">
        <Cover src={g.art.poster} className="gp-poster" />
        <div className="gp-titles">
          <h1 className="gp-title clamp-3">{locale === "ru" && g.game.name_ru ? g.game.name_ru : g.game.name}</h1>
          <p className="gp-sub clamp-1">{[years(g.game), studio].filter(Boolean).join(" · ")}</p>
          {(g.genres.length > 0 || g.hltb?.coop || g.hltb?.multi) && (
            <div className="gp-chips gp-head-chips">
              {g.genres.map((genre) => (
                <Chip key={genre}>{genre}</Chip>
              ))}
              {g.hltb?.coop && <Chip>{tr("gpCoop")}</Chip>}
              {g.hltb?.multi && <Chip>{tr("gpMulti")}</Chip>}
            </div>
          )}
        </div>
      </div>

      <div className="gp-chips">
        {g.platforms.map((p) => (
          <Chip
            key={`${p.console}:${p.store}`}
            tone="tonal"
            icon={p.url ? "external" : undefined}
            onClick={p.url ? () => openExternal(p.url!) : undefined}
          >
            {consoleLabel(p.console, p.store)}
          </Chip>
        ))}
      </div>

      {!progress && (
        <div className="gp-actions">
          {list ? (
            <Button variant="tonal" className="gp-main" icon="trophy" onClick={() => openList()}>
              {tr("gpGameAchievements")}
            </Button>
          ) : (
            <span className="gp-main gp-none">{tr("gpNotPlayed")}</span>
          )}
        </div>
      )}

      {progress && (
        <section className={`gp-progress${done ? " gp-progress-done" : ""}`}>
          {(!done || played.length > 1) && (
            <div className="gp-progress-head">
              {!done && <span className="gp-progress-label">{whose ? whose.name : tr("gpProgressMine")}</span>}
              {played.length > 1 && (
                <PlatformPicker
                  className="gp-progress-plat"
                  lists={played}
                  value={`${progress!.platform}:${progress!.title_id}`}
                  onChange={setPickedList}
                />
              )}
              {!done && (
                <button type="button" className="gp-progress-go" aria-label={tr("gpGameAchievements")} onClick={() => openList()}>
                  <GoMark />
                </button>
              )}
            </div>
          )}
          {done ? (
            <button type="button" className="gp-progress-main" onClick={() => openList()}>
              <DoneMark size={56} className="gp-done-mark" />
              <span className="gp-progress-row gp-done-row">
                <span className="gp-progress-num">
                  {progress.count}
                  <small>/{progress.total}</small>
                </span>
                <span className="gp-done-text">
                  <b>{tr("gameCompleted")}</b>
                  {progress.last && (
                    <span className="gp-progress-last">
                      {tr("gpLast")} {dayLabel(progress.last, locale).toLowerCase()}
                    </span>
                  )}
                </span>
              </span>
              <Wave value={progress.count} total={progress.total || progress.count} />
            </button>
          ) : (
          <button type="button" className="gp-progress-main" onClick={() => openList()}>
            <span className="gp-progress-row">
              <span className="gp-progress-num">
                {progress.count}
                {progress.total ? <small>/{progress.total}</small> : null}
              </span>
              {progress.total ? (
                <span className="gp-progress-pct t-num">{Math.round((progress.count / progress.total) * 100)} %</span>
              ) : null}
            </span>
            {progress.total ? <Wave value={progress.count} total={progress.total} /> : null}
            {progress.last && (
              <span className="gp-progress-last">
                {tr("gpLast")} {dayLabel(progress.last, locale).toLowerCase()}
              </span>
            )}
          </button>
          )}
          {others.length > 0 && (
            <div className="gp-progress-others">
              <span className="gp-progress-others-label">{tr("gpAlsoPlaying")}</span>
              <div className="gp-others rail">
                {others.map((p) => (
                  <button
                    key={p.person_id}
                    type="button"
                    className="gp-other"
                    onClick={() => {
                      tick();
                      open({
                        kind: "achievements",
                        platform: p.platform,
                        titleId: p.title_id,
                        name: g.game.name,
                        cover: g.art.poster,
                        person: { id: p.person_id, name: p.name },
                        lists: (p.lists?.length ?? 0) > 1 ? p.lists : undefined,
                      });
                    }}
                  >
                    <Face personId={p.person_id} name={p.name} size={32} />
                    <span className="gp-other-text">
                      <span className="clamp-1">{p.name}</span>
                      <b className="t-num">{p.count}</b>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      {g.hltb && <HltbSection hltb={g.hltb} />}

      {(g.description || released) && (
        <Section title={tr("gpAbout")}>
          {g.description && (
            <>
              <p className={`gp-story${story ? "" : " clamp-3"}${g.translating ? " translating" : ""}`}>
                {g.description.text}
              </p>
              {g.description.text.length > 180 && (
                <button type="button" className="gp-more" onClick={() => setStory((v) => !v)}>
                  {story ? tr("gpReadLess") : tr("gpReadMore")}
                </button>
              )}
            </>
          )}
          {released && (
            <p className="gp-released">
              {tr("gpReleased")}: {new Date(released).toLocaleDateString(locale === "en" ? "en-GB" : "ru-RU", { day: "numeric", month: "long", year: "numeric" })}
            </p>
          )}
        </Section>
      )}

      {gallery.length > 0 && (
        <Section
          title={tr("gpGallery")}
          action={
            gallery.length > GALLERY_SHOWN ? (
              <button
                type="button"
                className="link-btn"
                onClick={() => open({ kind: "gallery", game: g.game.name, cover: g.art.poster ?? null, videos, screenshots: g.screenshots })}
              >
                {tr("gpAll")} {gallery.length}
              </button>
            ) : null
          }
        >
          <div className="gp-shots rail">
            {gallery.slice(0, GALLERY_SHOWN).map((m, i) => (
              <MediaTile key={typeof m === "string" ? m : (m.hls ?? m.mp4 ?? i)} media={m} list={gallery} />
            ))}
          </div>
        </Section>
      )}

      {g.news.length > 0 && (
        <Section
          title={tr("gpNews")}
          action={
            g.news.length > 3 ? (
              <button type="button" className="link-btn" onClick={() => setAllNews((v) => !v)}>
                {allNews ? tr("gpReadLess") : `${tr("gpAll")} ${g.news.length}`}
              </button>
            ) : null
          }
        >
          <div className="group">
            <div className="group-items">
              {(allNews ? g.news : g.news.slice(0, 3)).map((n) => (
                <NewsRow
                  key={n.gid}
                  item={{
                    ...n,
                    excerpt: "",
                    game: {
                      platform: list?.platform ?? "",
                      title_id: list?.title_id ?? "",
                      name: g.game.name,
                      icon_url: g.art.poster,
                      hero: g.art.hero || g.art.header,
                    },
                  }}
                />
              ))}
            </div>
          </div>
        </Section>
      )}

      {dlcs.length > 0 && (
        <Section
          title={tr("gpDlc")}
          action={
            dlcs.length > DLC_SHOWN ? (
              <button
                type="button"
                className="link-btn"
                onClick={() => open({ kind: "dlcs", game: g.game.name, gameNames, cover: g.art.poster ?? null, dlcs })}
              >
                {tr("gpAll")} {num(dlcs.length, locale)}
              </button>
            ) : null
          }
        >
          <div className="group">
            <div className="group-items">
              {dlcs.slice(0, DLC_SHOWN).map((d, i) => (
                <DlcRow key={`${d.name}:${i}`} dlc={d} game={g.game.name} gameNames={gameNames} cover={g.art.poster ?? null} />
              ))}
            </div>
          </div>
        </Section>
      )}

      {editions.length > 1 && (
        <Section title={tr("gpEditions")}>
          <div className="rail">
            {editions.map((e) => (
              <button
                key={`${e.store}:${e.name}`}
                type="button"
                className="gp-edition"
                onClick={() => {
                  tick();
                  open({ kind: "edition", game: g.game.name, cover: g.art.poster ?? null, edition: e, gameNames, dlcs });
                }}
              >
                <Cover src={e.cover || g.art.poster} className="gp-edition-cover" />
                <span className="clamp-2">{cleanName(e.name)}</span>
              </button>
            ))}
          </div>
        </Section>
      )}

      {g.series.map((s) => (
        <Section key={s.series_id} title={`${tr("gpSeries")} ${s.name}`}>
          <div className="rail">
            {[...s.games]
              .sort((a, b) => (b.year ?? 0) - (a.year ?? 0))
              .map((card) => {
                const current = card.game_id === g.game.game_id;
                return (
                  <button
                    key={card.game_id}
                    type="button"
                    className={`gp-card${current ? " gp-card-current" : ""}`}
                    disabled={current}
                    onClick={() => openGame(card)}
                  >
                    <Cover src={card.poster || card.hero} className="gp-card-cover" />
                    {card.year && <span className="gp-card-year">{card.year}</span>}
                    <span className="gp-card-name clamp-2">{current ? tr("gpThisGame") : cleanName(card.name ?? "")}</span>
                  </button>
                );
              })}
          </div>
        </Section>
      ))}

      {g.related.length > 0 && (
        <Section title={tr("gpRelated")}>
          <div className="rail">
            {g.related.map((r) => {
              const words = RELATION[r.kind];
              const label = words ? tr(r.forward ? words[1] : words[0]) : r.kind;
              return (
                <button key={`${r.kind}:${r.game.game_id}`} type="button" className="gp-card" onClick={() => openGame(r.game)}>
                  <Cover src={r.game.poster || r.game.hero} className="gp-card-cover" />
                  {r.game.year && <span className="gp-card-year">{r.game.year}</span>}
                  <span className="gp-card-name clamp-2">{cleanName(r.game.name ?? "")}</span>
                  <span className="gp-card-rel">{label}</span>
                </button>
              );
            })}
          </div>
        </Section>
      )}
      <div style={{ height: 24 }} aria-hidden="true" />
    </>
  );
}

/** A developer's post as a row of the game's news: its picture (or its
 * kind's mark), its kind over its title, its day on the right. */
function NewsRow({ item }: { item: NewsItem }) {
  const { tr, locale, open } = useApp();
  const patch = item.kind === "patch";
  return (
    <button
      type="button"
      className="row row-tap gp-news-row"
      onClick={() => {
        tick();
        open({ kind: "news", appid: item.appid, gid: item.gid, item, game: item.game });
      }}
    >
      {item.image ? (
        <Cover src={item.image} className="gp-news-pic" />
      ) : (
        <span className={`gp-news-pic gp-news-mark ${patch ? "kind-patch" : "kind-news"}`}>
          <Icon name={patch ? "patch" : "news"} size={18} />
        </span>
      )}
      <span className="row-text">
        <b className={`gp-news-kind ${patch ? "gp-news-patch" : "gp-news-post"}`}>{patch ? tr("newsPatch") : tr("newsPost")}</b>
        <span className="gp-dlc-name">{item.title}</span>
      </span>
      <span className="gp-news-day t-meta">{whenLabel(item.date, locale, true)}</span>
    </button>
  );
}

/** HowLongToBeat's hours, its score and its age rating, as a game and an
 * add-on show them. */
export function HltbSection({ hltb }: { hltb: GameHltb }) {
  const { tr, locale } = useApp();
  return (
    <Section
      title={tr("gpHours")}
      action={
        <button type="button" className="link-btn" onClick={() => openExternal(hltb.url)}>
          HLTB ↗
        </button>
      }
    >
      <div className="gp-hltb">
        {(
          [
            [hltb.main, "gpMain"],
            [hltb.extra, "gpExtra"],
            [hltb.completionist, "gpFull"],
          ] as const
        ).map(([h, label]) => (
          <div key={label}>
            <b className="t-num">
              {h ? h.toLocaleString(locale === "en" ? "en-US" : "ru-RU", { maximumFractionDigits: 1 }) : "–"}
              <small> {tr("gpHoursUnit")}</small>
            </b>
            <span>{tr(label)}</span>
          </div>
        ))}
      </div>
      {(hltb.score || hltb.rating) && (
        <div className="gp-badges">
          {hltb.score ? (
            <span className="gp-badge">
              <span className="gp-badge-shape shape-cookie9">{hltb.score}</span>
              {tr("hltbScore")}
            </span>
          ) : null}
          {hltb.rating ? (
            <span className="gp-badge">
              <span className="gp-badge-shape gp-badge-2 shape-cookie9">{hltb.rating}</span>
              {tr("ageRating")}
            </span>
          ) : null}
        </div>
      )}
    </Section>
  );
}
