import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchGame,
  type FeedItem,
  type GameAchievement,
  type GameDetails,
  type GameRef,
} from "../../../api";
import { t, type Locale } from "../../../i18n";
import {
  CoverImg,
  RowsSkel,
  Icon,
  TierMedals,
  asTier,
  type ScoreCupLine,
  type TierCounts,
  Sheet,
} from "../../shared/lib";
import { UnlockCard } from "../../person";
import {
  COMPLETION_BADGES,
  PLATFORMS,
} from "../../shared/constants";
import {
  groupLabel,
  pickLocale,
  trophyBadge,
  type FilterType,
} from "../utils";
import { GameHero } from "../game-hero/GameHero";
import { GameAchievementRow } from "../game-achievement-row/GameAchievementRow";

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
  const other =
    game.person && game.person.tg_id !== meId ? game.person : null;
  const viewed = other;
  const [compare, setCompare] = useState(false);
  const [myDetails, setMyDetails] = useState<GameDetails | null>(null);
  // Always opens on what was earned; the lock flips to what is still to earn.
  const [showEarned, setShowEarned] = useState(true);
  const showAllSecrets = initialShowSecrets;
  const [revealedIds, setRevealedIds] = useState<Set<string>>(() => new Set());
  const [selectedAch, setSelectedAch] = useState<GameAchievement | null>(null);

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
      : details?.completion_percent ?? 0;
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
  const earnedLine = busy ? null : scoreLines[0];

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

  const selectedFeedItem = useMemo<FeedItem | null>(() => {
    if (!selectedAch) return null;
    return {
      tg_id: 0,
      person: "",
      name:
        pickLocale(
          locale,
          selectedAch.name_ru,
          selectedAch.name_en,
          selectedAch.achievement_id,
        ) || t(locale, "secret"),
      game: title,
      gamerscore: selectedAch.gamerscore || 0,
      rarity_percent: selectedAch.rarity_percent,
      platform: game.platform,
      unlocked_at: selectedAch.unlocked_at,
      is_secret: selectedAch.is_secret,
      title_id: game.title_id,
      achievement_id: selectedAch.achievement_id,
      // Many catalog rows carry no picture of their own: the game's stands in.
      icon_url: selectedAch.icon_url || cover,
      game_icon_url: cover,
      description: pickLocale(
        locale,
        selectedAch.description_ru,
        selectedAch.description_en,
      ),
      trophy_type: selectedAch.trophy_type,
      tier_badge: trophyBadge(selectedAch.trophy_type),
      progress: {
        unlocked,
        total,
      },
    };
  }, [
    cover,
    game.platform,
    game.title_id,
    locale,
    selectedAch,
    title,
    total,
    unlocked,
  ]);

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
              <Icon name="back" size={28} />
            </button>
            <CoverImg src={cover} kind="game" className="person-avatar" />
            <span className="person-bar-title">
              <strong>{title}</strong>
              {viewed && <small>{viewed.name}</small>}
            </span>
          </div>
          {earnedLine &&
            (game.platform === PLATFORMS.PSN ? (
              <TierMedals counts={tierCounts} />
            ) : (
              <span className="game-bar-score">
                <strong>{earnedLine.count}</strong>
                <small>{earnedLine.unit ?? t(locale, "achievements")}</small>
              </span>
            ))}
        </div>
      </header>

      <GameHero
        cover={cover}
        pct={pct}
        total={total}
        isCompleted={isCompleted}
        loading={busy}
        locale={locale}
      />

      <div className="section-head achievements-head">
        <h1 className="kicker" style={{ margin: 0 }}>
          {t(locale, "homeAchievements")}
          {total > 0 &&
            ` (${comparing ? `${myUnlockedIds.size} · ${unlocked}` : unlocked}/${total})`}
        </h1>

        <span className="game-head-actions">
        {other && (
          <button
            type="button"
            className={compare ? "game-lock-chip is-on" : "game-lock-chip"}
            aria-pressed={compare}
            aria-label={t(locale, "compare")}
            onClick={() => setCompare((on) => !on)}
          >
            <Icon name="compare" size={20} />
          </button>
        )}
        {(!busy && hasBoth && !comparing) && (
          <button
            type="button"
            className="game-lock-chip"
            aria-label={t(locale, earnedView ? "showLocked" : "showEarned")}
            onClick={() => setShowEarned((on) => !on)}
          >
            <Icon name={earnedView ? "unlock" : "lock"} size={18} />
          </button>
        )}
        </span>
      </div>

      {busy && <RowsSkel count={6} />}
      {error && (
        <p className="empty">
          {t(locale, "error")}: {error}
        </p>
      )}
      {(!busy && !error && achievements.length === 0) && (
        <p className="empty">{t(locale, "gameEmpty")}</p>
      )}

      {(!busy &&
      !error &&
      achievements.length > 0 &&
      filteredAchievements.length === 0) && (
        <p className="empty">{t(locale, "emptyFilter")}</p>
      )}

      {(!busy && details) && (
        <div className="feed">
          {byGroup.map((section, i) => (
            <section key={section.id || `group-${i}`} className="feed-day">
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
                    onSelect={setSelectedAch}
                    fallbackIcon={cover}
                    compare={
                      comparing && other
                        ? {
                            me: { id: meId, name: t(locale, "you"), has: iHave },
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
      )}

      {selectedFeedItem && (
        <Sheet
          mid
          onClose={() => setSelectedAch(null)}
          closeLabel={t(locale, "close")}
          noClose
        >
          <div className="sheet-unlock">
            <UnlockCard
              item={selectedFeedItem}
              locale={locale}
              secret={Boolean(
                selectedAch?.is_secret &&
                  !showAllSecrets &&
                  !revealedIds.has(selectedAch.achievement_id),
              )}
              author={false}
              gameInCopy
              onReveal={() =>
                selectedAch && toggleReveal(selectedAch.achievement_id)
              }
            />
          </div>
        </Sheet>
      )}
    </>
  );

  return <div className="game-page" data-no-pull>
      {content}
    </div>;
}
