import {
  Suspense,
  lazy,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import { EffectFade } from "swiper/modules";
import { Swiper, SwiperSlide } from "swiper/react";
import type { Swiper as SwiperInstance } from "swiper/types";
import "swiper/css";
import "swiper/css/effect-fade";
import {
  fetchGameGuides,
  fetchGame,
  fetchGameHltb,
  fetchGamePatches,
  type GameAchievement,
  type GameDetails,
  type AchievementTip,
  type GameHltb,
  type GamePatch,
  type GameRef,
} from "../../../api";
import { t, type Locale } from "../../../i18n";
import {
  RowsSkel,
  Icon,
  Dropdown,
  DropdownArrow,
  TierMedals,
  asTier,
  useBackHandler,
  type ScoreCupLine,
  type TierCounts,
} from "../../shared/lib";
import { COMPLETION_BADGES, PLATFORMS } from "../../shared/constants";
import { groupLabel, pickLocale, type FilterType } from "../utils";
import { GameHero } from "../game-hero/GameHero";
import { HeroPeek } from "../game-hero/HeroPeek";
import { GameAchievementRow } from "../game-achievement-row/GameAchievementRow";
import { AchievementPage } from "../achievement-page/AchievementPage";
import { GameTabBar } from "../game-tab-bar/GameTabBar";
import type { PostFilter } from "../patch-notes/PatchNotes";
import { recall, remember } from "../game-cache";

// The tabs nobody sees at first are their own chunks, fetched when opened.
const HltbAbout = lazy(() =>
  import("../hltb-about/HltbAbout").then((m) => ({ default: m.HltbAbout })),
);
const FILTER_LABEL = {
  all: "postsAll",
  news: "postsNews",
  patch: "postsPatches",
} as const;

const PatchNotes = lazy(() =>
  import("../patch-notes/PatchNotes").then((m) => ({ default: m.PatchNotes })),
);

const GUIDES_WAIT_MS = 8000;
const GUIDES_RETRY_MS = 20000;
const GUIDES_TRIES = 4;
const GUIDES_REFRESH_MS = 30000;

export function TitleSheet({
  game,
  data,
  locale,
  showSecrets: initialShowSecrets = false,
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
  // The phone's "back" leaves the game page.
  useBackHandler(true, onClose, `${game.platform}:${game.title_id}`);
  // Whose progress is on the page: the person whose card it was opened from
  // (or yours when it was opened from your own). "Compare" adds yours beside
  // theirs, in the one list.
  // Asked for: by person id, or by the Telegram id an old post's button carries.
  const asked =
    game.person && (game.person.person_id ?? null) !== meId ? game.person : null;
  // What the page showed the last time this game was open: drawn at once, the
  // fresh answers replace it when they arrive.
  const gameKey = `${game.platform}:${game.title_id}`;
  const detailsKey = `${gameKey}:${
    asked?.person_id ?? (asked?.tg_id != null ? `tg${asked.tg_id}` : "me")
  }`;
  const seenDetails = recall<GameDetails>("details", detailsKey);
  const [details, setDetails] = useState<GameDetails | null>(
    seenDetails ?? null,
  );
  const [busy, setBusy] = useState(seenDetails === undefined);
  const [error, setError] = useState<string | null>(null);
  const [compare, setCompare] = useState(false);
  const [myDetails, setMyDetails] = useState<GameDetails | null>(null);
  // Always opens on what was earned; the lock flips to what is still to earn.
  const [showEarned, setShowEarned] = useState(true);
  const [postFilter, setPostFilter] = useState<PostFilter>("all");
  const showAllSecrets = initialShowSecrets;
  const [revealedIds, setRevealedIds] = useState<Set<string>>(() => new Set());
  // Achievements / "Об игре": one Swiper, endlessly looping, switched by tab
  // or by swipe — the same shape the profile's own carousels use.
  const [tabSwiper, setTabSwiper] = useState<SwiperInstance | null>(null);
  // The tab swiper sizes itself to its slide (autoHeight): a card that opens
  // inside a slide has to tell it, or the rest of the text is cut off.
  // What the Steam guides say about each achievement: a row with a tip opens.
  const seenTips = recall<Record<string, AchievementTip>>("tips", gameKey);
  const [guideTips, setGuideTips] = useState<Record<string, AchievementTip>>(
    seenTips ?? {},
  );
  const [guidesReady, setGuidesReady] = useState(seenTips !== undefined);
  useEffect(() => {
    let cancelled = false;
    const known = recall<Record<string, AchievementTip>>("tips", gameKey);
    setGuideTips(known ?? {});
    setGuidesReady(known !== undefined);
    // The first look at a game reads several guides and can take a while: the
    // page waits for it, but not past a limit — the tips still land when they
    // arrive, they just are not part of the first picture then.
    const limit = window.setTimeout(() => {
      if (!cancelled) setGuidesReady(true);
    }, GUIDES_WAIT_MS);
    // Steam holds guides back when asked too often; an incomplete answer is
    // asked again a little later, a few times, and the tips fill in.
    let tries = 0;
    let retry = 0;
    const ask = () => {
      tries += 1;
      void fetchGameGuides(data, game.platform, game.title_id)
        .then((res) => {
          if (cancelled) return;
          setGuideTips(res.tips ?? {});
          if (res.complete) remember("tips", gameKey, res.tips ?? {});
          if (!res.complete && tries < GUIDES_TRIES) {
            retry = window.setTimeout(ask, GUIDES_RETRY_MS);
          }
        })
        .catch(() => {
          if (!cancelled) setGuideTips({});
        })
        .finally(() => {
          window.clearTimeout(limit);
          if (!cancelled) setGuidesReady(true);
        });
    };
    ask();
    // Coming back to the app after a while asks again: what the guides held
    // when the page opened is not what they hold now.
    let askedAt = Date.now();
    const onVisible = () => {
      if (document.visibilityState !== "visible") return;
      if (Date.now() - askedAt < GUIDES_REFRESH_MS) return;
      askedAt = Date.now();
      window.clearTimeout(retry);
      tries = 0;
      ask();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisible);
      window.clearTimeout(limit);
      window.clearTimeout(retry);
    };
  }, [data, game.platform, game.title_id, gameKey]);

  // The achievement whose own page is open (AchievementPage), if any.
  const [openAchievement, setOpenAchievement] = useState<string | null>(null);
  const [tabEpoch, setTabEpoch] = useState(0);
  const collapseAll = useCallback(() => {
    setTabEpoch((n) => n + 1);
  }, []);
  const refreshTabHeight = useCallback(() => {
    tabSwiper?.updateAutoHeight(0);
  }, [tabSwiper]);
  // HLTB's own hours/description (#131), fetched on its own request so a
  // game's first-ever match never delays the achievements below —
  // `undefined` while that request is still out, `null` once it has
  // answered with no match.
  const [hltbInfo, setHltbInfo] = useState<GameHltb | null | undefined>(
    recall<GameHltb | null>("hltb", gameKey),
  );

  useEffect(() => {
    let cancelled = false;
    const known = recall<GameDetails>("details", detailsKey);
    setDetails(known ?? null);
    setBusy(known === undefined);
    setError(null);
    void fetchGame(data, game.platform, game.title_id, {
      personId: asked?.person_id,
      tgId: asked?.tg_id,
    })
      .then((res) => {
        if (cancelled) return;
        setDetails(res);
        remember("details", detailsKey, res);
        setBusy(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(String(err));
        setBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [data, game.platform, game.title_id, asked?.person_id, asked?.tg_id, detailsKey]);

  useEffect(() => {
    let cancelled = false;
    setHltbInfo(recall<GameHltb | null>("hltb", gameKey));
    void fetchGameHltb(data, game.platform, game.title_id)
      .then((res) => {
        if (cancelled) return;
        setHltbInfo(res.hltb);
        remember("hltb", gameKey, res.hltb);
      })
      .catch(() => {
        // Best-effort, same as the endpoint itself: a game simply keeps
        // showing no "Об игре" tab rather than an error over its achievements.
        if (!cancelled) setHltbInfo(null);
      });
    return () => {
      cancelled = true;
    };
  }, [data, game.platform, game.title_id]);

  // The updates tab's number needs them before the tab is opened.
  const [patches, setPatches] = useState<GamePatch[] | undefined>(
    recall<GamePatch[]>("patches", gameKey),
  );
  useEffect(() => {
    let cancelled = false;
    setPatches(recall<GamePatch[]>("patches", gameKey));
    void fetchGamePatches(data, game.platform, game.title_id)
      .then((res) => {
        if (cancelled) return;
        setPatches(res.patches);
        remember("patches", gameKey, res.patches);
      })
      .catch(() => {
        if (!cancelled) setPatches([]);
      });
    return () => {
      cancelled = true;
    };
  }, [data, game.platform, game.title_id]);

  useEffect(() => {
    if (!compare || myDetails) return;
    let cancelled = false;
    void fetchGame(data, game.platform, game.title_id)
      .then((res) => {
        if (!cancelled) setMyDetails(res);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setCompare(false);
        setError(String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [compare, myDetails, data, game.platform, game.title_id]);

  const title = useMemo<string>(() => {
    return (
      pickLocale(
        locale,
        details?.name_ru,
        details?.name_en,
        details?.name || game.name,
      ) ||
      game.name ||
      ""
    );
  }, [details, game.name, locale]);

  // The picture of the card the page was opened from wins over the one in the
  // details: it is the one already on screen and known to load, and the
  // header must not change (or lose it) when the details arrive.
  const cover = game.cover || game.icon_url || details?.icon_url || null;
  const achievements = useMemo(() => details?.achievements ?? [], [details]);
  const unlocked =
    details?.achievements_unlocked ??
    achievements.filter((a) => a.is_unlocked).length;
  const total = details?.achievements_total ?? achievements.length;
  const pct =
    total > 0
      ? Math.round((unlocked / total) * 100)
      : (details?.completion_percent ?? 0);
  const isCompleted = total > 0 && unlocked >= total;

  const scoreLines = useMemo<ScoreCupLine[]>(() => {
    const isXbox = game.platform.startsWith(PLATFORMS.XBOX);
    const isPsn = game.platform === PLATFORMS.PSN;
    const isSteam = game.platform === PLATFORMS.STEAM;

    let earnedGs = 0;
    let totalGs = 0;
    let bronze = 0;
    let silver = 0;
    let gold = 0;
    let platinum = 0;

    for (const ach of achievements) {
      if (ach.gamerscore != null) {
        totalGs += ach.gamerscore;
        if (ach.is_unlocked) earnedGs += ach.gamerscore;
      }
      if (ach.trophy_type) {
        const tt = ach.trophy_type.toLowerCase();
        if (tt === "bronze" && ach.is_unlocked) bronze++;
        else if (tt === "silver" && ach.is_unlocked) silver++;
        else if (tt === "gold" && ach.is_unlocked) gold++;
        else if (tt === "platinum" && ach.is_unlocked) platinum++;
      }
    }

    const tiers = isPsn ? { bronze, silver, gold, platinum } : null;

    const extra = isXbox
      ? isCompleted
        ? `${COMPLETION_BADGES.XBOX} ${t(locale, "gameDone")}`
        : `${unlocked}/${total} (${pct}%)`
      : isSteam
        ? isCompleted
          ? `${COMPLETION_BADGES.STEAM} ${t(locale, "gameDone")}`
          : `${unlocked}/${total} (${pct}%)`
        : isCompleted
          ? `${COMPLETION_BADGES.PSN} ${t(locale, "gameDone")}`
          : `${unlocked}/${total} (${pct}%)`;

    return [
      {
        platform: game.platform,
        count: isXbox && totalGs > 0 ? earnedGs : unlocked,
        unit: isXbox && totalGs > 0 ? "G" : null,
        extra,
        tiers,
      },
    ];
  }, [achievements, game.platform, isCompleted, locale, pct, total, unlocked]);

  // PSN: how many trophies of each tier the person has earned in this game.
  const tierCounts = useMemo<TierCounts>(() => {
    const counts: TierCounts = { bronze: 0, silver: 0, gold: 0, platinum: 0 };
    for (const ach of achievements) {
      const tier = asTier(ach.trophy_type);
      if (tier && ach.is_unlocked) counts[tier] += 1;
    }
    return counts;
  }, [achievements]);

  // What was earned here, written in the bar itself (no tap, no drawer).
  // The page is ready when its achievements, guides and updates are all known.
  const loading = busy || !guidesReady || patches === undefined;
  // A game with no updates has no tab for them.
  const hasUpdates = patches !== undefined && patches.length > 0;
  const earnedLine = loading ? null : scoreLines[0];

  const toggleReveal = useCallback((achId: string) => {
    setRevealedIds((prev) => {
      const next = new Set(prev);
      if (next.has(achId)) next.delete(achId);
      else next.add(achId);
      return next;
    });
  }, []);

  const groups = details?.groups ?? [];
  const showGroups = groups.length > 1;

  // Compare: yours, by achievement id.
  const myUnlockedIds = useMemo(
    () =>
      new Set(
        (myDetails?.achievements ?? [])
          .filter((a) => a.is_unlocked)
          .map((a) => a.achievement_id),
      ),
    [myDetails],
  );
  // Whose progress it is, as the answer names them (an old link knew only a
  // Telegram id, and a link's own name is empty); null when it is one's own.
  const other: { person_id: number; name: string } | null =
    details?.viewed ??
    (asked?.person_id != null && asked.person_id !== meId
      ? { person_id: asked.person_id, name: asked.name }
      : null);
  const viewed = other;
  const comparing = compare && Boolean(myDetails) && Boolean(other);

  // With nothing earned (or everything earned) there is only one list to show:
  // the one that has achievements in it, and no lock to flip to an empty one.
  const earnedCount = achievements.filter((a) => a.is_unlocked).length;
  const hasBoth = earnedCount > 0 && earnedCount < achievements.length;
  const earnedView = hasBoth ? showEarned : earnedCount > 0;
  const filter: FilterType = earnedView ? "unlocked" : "locked";

  const filteredAchievements = useMemo(() => {
    const rows = achievements.filter((ach) => {
      if (comparing) return true;
      if (filter === "unlocked") return ach.is_unlocked;
      if (filter === "locked") return !ach.is_unlocked;
      return true;
    });
    // What was earned reads newest first (undated ones last); what is still to
    // earn keeps the game's own order. Comparing: theirs earned first, likewise.
    const at = (ach: GameAchievement) =>
      ach.unlocked_at ? Date.parse(ach.unlocked_at) || 0 : 0;
    if (comparing) {
      return [...rows].sort(
        (a, b) =>
          Number(b.is_unlocked) - Number(a.is_unlocked) ||
          (a.is_unlocked && b.is_unlocked ? at(b) - at(a) : 0),
      );
    }
    if (filter === "unlocked") return [...rows].sort((a, b) => at(b) - at(a));
    return rows;
  }, [achievements, filter, comparing]);

  const byGroup = useMemo(() => {
    const rows = filteredAchievements;
    if (!showGroups) return [{ id: "", label: "", rows }];

    const order = groups.map((g) => g.group_id);
    const map = new Map<string, GameAchievement[]>();
    for (const id of order) map.set(id, []);
    const orphan: GameAchievement[] = [];

    for (const row of rows) {
      const gid = row.trophy_group_id || "default";
      const bucket = map.get(gid);
      if (bucket) bucket.push(row);
      else orphan.push(row);
    }

    const sections = order.map((id) => {
      const g = groups.find((x) => x.group_id === id)!;
      return {
        id,
        label: groupLabel(g, locale, title),
        rows: map.get(id) ?? [],
      };
    });

    if (orphan.length) {
      sections.push({
        id: "_",
        label: t(locale, "otherGroup"),
        rows: orphan,
      });
    }

    return sections.filter((s) => s.rows.length > 0);
  }, [filteredAchievements, groups, locale, showGroups, title]);

  const content = (
    <>
      <header className="account-bar person-bar">
        <div className="account-top">
          <div className="account-who">
            <button
              type="button"
              className="person-back"
              onClick={onClose}
              aria-label={t(locale, "back")}
            >
              <Icon name="back" size={26} />
            </button>
            <span className="person-bar-title">
              <strong>{title}</strong>
              {viewed?.name && <small>{viewed.name}</small>}
            </span>
          </div>
          {earnedLine &&
            (game.platform === PLATFORMS.PSN ? (
              <TierMedals counts={tierCounts} discSize={18} numbersInside />
            ) : (
              <span className="game-bar-score">
                <strong>{earnedLine.count}</strong>
                <small>{earnedLine.unit ?? t(locale, "achievements")}</small>
              </span>
            ))}
        </div>
      </header>

      <HeroPeek>
        {(open) => (
          <GameHero
            cover={cover}
            pct={pct}
            total={total}
            isCompleted={isCompleted}
            loading={loading}
            locale={locale}
            compact={!open}
          />
        )}
      </HeroPeek>

      {loading ? (
        <>
          <div className="game-tabs-row">
            <div className="game-tabs">
              <div className="game-tabs-track">
                <span
                  className="skel line"
                  style={{ width: 118, height: 15 }}
                />
                <span className="skel line" style={{ width: 84, height: 15 }} />
              </div>
            </div>
          </div>
          <div className="game-tab-panel feed">
            <RowsSkel count={6} />
          </div>
        </>
      ) : (
        <>
          {tabSwiper && (
            <GameTabBar
              swiper={tabSwiper}
              labels={[
                total > 0
                  ? `${t(locale, "homeAchievements")} (${comparing ? `${myUnlockedIds.size} · ${unlocked}` : unlocked}/${total})`
                  : t(locale, "homeAchievements"),
                ...(hasUpdates
                  ? [`${t(locale, "patchesTab")} (${patches.length})`]
                  : []),
                t(locale, "aboutGame"),
              ]}
              actions={[
                (other || (hasBoth && !comparing)) && (
                  <div className="game-tab-actions">
                    {other && (
                      <button
                        type="button"
                        className={
                          compare ? "game-lock-chip is-on" : "game-lock-chip"
                        }
                        aria-pressed={compare}
                        aria-label={t(locale, "compare")}
                        onClick={() => setCompare((on) => !on)}
                      >
                        <Icon name="compare" size={22} />
                      </button>
                    )}
                    {hasBoth && !comparing && (
                      <button
                        type="button"
                        className="game-lock-chip"
                        aria-label={t(
                          locale,
                          earnedView ? "showLocked" : "showEarned",
                        )}
                        onClick={() => setShowEarned((on) => !on)}
                      >
                        <Icon name={earnedView ? "unlock" : "lock"} size={20} />
                      </button>
                    )}
                  </div>
                ),
                ...(hasUpdates
                  ? [
                      <Dropdown<PostFilter>
                        key="posts-filter"
                        className="dd-trigger posts-filter"
                        value={postFilter}
                        options={(["all", "news", "patch"] as PostFilter[]).map((value) => ({
                          value,
                          label: t(locale, FILTER_LABEL[value]),
                        }))}
                        onChange={setPostFilter}
                        trigger={
                          <>
                            {t(locale, FILTER_LABEL[postFilter])}
                            <DropdownArrow />
                          </>
                        }
                      />,
                    ]
                  : []),
                null,
              ]}
            />
          )}
          <Swiper
            key={hasUpdates ? "with-updates" : "no-updates"}
            className="game-tab-swiper"
            modules={[EffectFade]}
            effect="fade"
            fadeEffect={{ crossFade: true }}
            loop
            autoHeight
            speed={320}
            threshold={24}
            onSlideChangeTransitionEnd={collapseAll}
            touchAngle={35}
            onSwiper={setTabSwiper}
          >
            <SwiperSlide>
              <div className="game-tab-panel">
                {error && (
                  <p className="empty">
                    {t(locale, "error")}: {error}
                  </p>
                )}
                {!error && achievements.length === 0 && (
                  <p className="empty">{t(locale, "gameEmpty")}</p>
                )}
                {!error &&
                  achievements.length > 0 &&
                  filteredAchievements.length === 0 && (
                    <p className="empty">{t(locale, "emptyFilter")}</p>
                  )}
                <div className="feed">
                  {byGroup.map((section, i) => (
                    <section
                      key={section.id || `group-${i}`}
                      className="feed-day"
                    >
                      {section.label && (
                        <p className="feed-day-label">{section.label}</p>
                      )}
                      {section.rows.map((row) => {
                        const iHave = myUnlockedIds.has(row.achievement_id);
                        // A secret stays hidden until the "show secrets" setting or a
                        // tap on it says otherwise — earned or not.
                        const isRevealed =
                          showAllSecrets || revealedIds.has(row.achievement_id);
                        return (
                          <GameAchievementRow
                            key={row.achievement_id}
                            row={row}
                            isRevealed={isRevealed}
                            locale={locale}
                            onToggleReveal={toggleReveal}
                            tip={guideTips[row.achievement_id]}
                            onOpen={setOpenAchievement}
                            fallbackIcon={cover}
                            compare={
                              comparing && other
                                ? {
                                    me: {
                                      id: meId,
                                      name: t(locale, "you"),
                                      has: iHave,
                                    },
                                    them: {
                                      id: other.person_id,
                                      name: other.name,
                                      has: row.is_unlocked,
                                    },
                                  }
                                : undefined
                            }
                          />
                        );
                      })}
                    </section>
                  ))}
                </div>
              </div>
            </SwiperSlide>
            {hasUpdates && (
              <SwiperSlide>
                <div className="game-tab-panel">
                  <Suspense fallback={null}>
                    <PatchNotes
                      patches={patches}
                      filter={postFilter}
                      locale={locale}
                      collapseKey={tabEpoch}
                      onLayout={refreshTabHeight}
                      game={{ name: title, icon_url: game.icon_url ?? details?.icon_url ?? null }}
                    />
                  </Suspense>
                </div>
              </SwiperSlide>
            )}
            <SwiperSlide>
              <div className="game-tab-panel">
                {hltbInfo ? (
                  <Suspense fallback={null}>
                    <HltbAbout hltb={hltbInfo} locale={locale} />
                  </Suspense>
                ) : hltbInfo === null ? (
                  <p className="empty">{t(locale, "aboutEmpty")}</p>
                ) : (
                  // Still out on its own request (#131) — the achievements tab
                  // never waited on this, so it just fills in once it answers.
                  <>
                    {[0, 1, 2, 3, 4].map((i) => (
                      <div key={i} className="about-game-fact">
                        <span className="skel line" style={{ width: 70 }} />
                        <span className="skel line" style={{ width: 120 }} />
                      </div>
                    ))}
                    <span
                      className="skel line"
                      style={{ width: "92%", marginTop: 26 }}
                    />
                    <span
                      className="skel line"
                      style={{ width: "80%", marginTop: 6 }}
                    />
                  </>
                )}
              </div>
            </SwiperSlide>
          </Swiper>
        </>
      )}
    </>
  );

  const shownAchievement = openAchievement
    ? achievements.find((ach) => ach.achievement_id === openAchievement)
    : undefined;

  return (
    <div className="game-page" data-no-pull>
      {content}
      {shownAchievement && (
        <AchievementPage
          row={shownAchievement}
          tip={guideTips[shownAchievement.achievement_id]}
          game={title}
          fallbackIcon={cover}
          locale={locale}
          onClose={() => setOpenAchievement(null)}
        />
      )}
    </div>
  );
}
