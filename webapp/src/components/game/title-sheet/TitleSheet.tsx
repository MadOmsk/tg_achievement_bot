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
  TierMedals,
  asTier,
  type ScoreCupLine,
  type TierCounts,
} from "../../shared/lib";
import { COMPLETION_BADGES, PLATFORMS } from "../../shared/constants";
import { groupLabel, pickLocale, type FilterType } from "../utils";
import { GameHero } from "../game-hero/GameHero";
import { HeroPeek } from "../game-hero/HeroPeek";
import { GameAchievementRow } from "../game-achievement-row/GameAchievementRow";
import { GameTabBar } from "../game-tab-bar/GameTabBar";

// The tabs nobody sees at first are their own chunks, fetched when opened.
const HltbAbout = lazy(() =>
  import("../hltb-about/HltbAbout").then((m) => ({ default: m.HltbAbout })),
);
const PatchNotes = lazy(() =>
  import("../patch-notes/PatchNotes").then((m) => ({ default: m.PatchNotes })),
);

const GUIDES_WAIT_MS = 8000;
const GUIDES_RETRY_MS = 20000;
const GUIDES_TRIES = 4;

const groupOf = (row: GameAchievement) => row.trophy_group_id ?? "default";

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
  const [details, setDetails] = useState<GameDetails | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Whose progress is on the page: the person whose card it was opened from
  // (or yours when it was opened from your own). "Compare" adds yours beside
  // theirs, in the one list.
  const other = game.person && game.person.tg_id !== meId ? game.person : null;
  const viewed = other;
  const [compare, setCompare] = useState(false);
  const [myDetails, setMyDetails] = useState<GameDetails | null>(null);
  // Always opens on what was earned; the lock flips to what is still to earn.
  const [showEarned, setShowEarned] = useState(true);
  const showAllSecrets = initialShowSecrets;
  const [revealedIds, setRevealedIds] = useState<Set<string>>(() => new Set());
  // Achievements / "Об игре": one Swiper, endlessly looping, switched by tab
  // or by swipe — the same shape the profile's own carousels use.
  const [tabSwiper, setTabSwiper] = useState<SwiperInstance | null>(null);
  // The tab swiper sizes itself to its slide (autoHeight): a card that opens
  // inside a slide has to tell it, or the rest of the text is cut off.
  // What the Steam guides say about each achievement: a row with a tip opens.
  const [guideTips, setGuideTips] = useState<Record<string, AchievementTip>>(
    {},
  );
  const [guidesReady, setGuidesReady] = useState(false);
  useEffect(() => {
    let cancelled = false;
    setGuideTips({});
    setGuidesReady(false);
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
    return () => {
      cancelled = true;
      window.clearTimeout(limit);
      window.clearTimeout(retry);
    };
  }, [data, game.platform, game.title_id]);

  // Which achievement's tip is showing, per group of the list (a PSN game's
  // DLC is a group of its own): opening one closes the other in its group.
  const [openTips, setOpenTips] = useState<Record<string, string | null>>({});
  const toggleTip = useCallback((group: string, id: string) => {
    setOpenTips((cur) => ({ ...cur, [group]: cur[group] === id ? null : id }));
  }, []);
  const refreshTabHeight = useCallback(() => {
    tabSwiper?.updateAutoHeight(0);
  }, [tabSwiper]);
  // A tip unfolding changes the height the tab swiper sized itself to: once as
  // it starts, and once more when its animation is done.
  useEffect(() => {
    refreshTabHeight();
    const id = window.setTimeout(refreshTabHeight, 320);
    return () => window.clearTimeout(id);
  }, [openTips, refreshTabHeight]);
  // HLTB's own hours/description (#131), fetched on its own request so a
  // game's first-ever match never delays the achievements below —
  // `undefined` while that request is still out, `null` once it has
  // answered with no match.
  const [hltbInfo, setHltbInfo] = useState<GameHltb | null | undefined>(
    undefined,
  );

  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    setError(null);
    void fetchGame(data, game.platform, game.title_id, {
      tgId: viewed?.tg_id,
    })
      .then((res) => {
        if (cancelled) return;
        setDetails(res);
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
  }, [data, game.platform, game.title_id, viewed?.tg_id]);

  useEffect(() => {
    let cancelled = false;
    setHltbInfo(undefined);
    void fetchGameHltb(data, game.platform, game.title_id)
      .then((res) => {
        if (!cancelled) setHltbInfo(res.hltb);
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
  const [patches, setPatches] = useState<GamePatch[] | undefined>(undefined);
  useEffect(() => {
    let cancelled = false;
    setPatches(undefined);
    void fetchGamePatches(data, game.platform, game.title_id)
      .then((res) => {
        if (!cancelled) setPatches(res.patches);
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
          <div className="game-tab-panel feed" style={{ marginTop: 14 }}>
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
                ...(hasUpdates ? [null] : []),
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
                            open={openTips[groupOf(row)] === row.achievement_id}
                            onToggleTip={(id) => toggleTip(groupOf(row), id)}
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
                                      id: other.tg_id,
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
                      locale={locale}
                      onLayout={refreshTabHeight}
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

  return (
    <div className="game-page" data-no-pull>
      {content}
    </div>
  );
}
