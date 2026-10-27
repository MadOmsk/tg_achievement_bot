import { useEffect, useMemo, useState } from "react";
import { gamesApi, type GameAchievement, type GameDetails, type GameGuidesResponse } from "../../api";
import { gameArtOf, useArtTheme } from "../../app/artTheme";
import { useApp } from "../../app/context";
import { useLoad } from "../../app/useLoad";
import { achOfList, pointsOf } from "../../app/views";
import { groupLabel } from "../../core/game-utils";
import { recall, remember } from "../../core/game-cache";
import { dayLabel, num, plural } from "../../i18n";
import { AchRow } from "../../parts/AchRow";
import { PlatformTabs } from "../../parts/PlatformTabs";
import { DoneMark } from "../../parts/DoneMark";
import { Button, Empty, Segmented } from "../../ui/Controls";
import { Face } from "../../ui/Face";
import { Icon } from "../../ui/Icon";
import { Page } from "../../ui/Page";
import { Cover } from "../../ui/Pic";
import { Hero } from "../../ui/Hero";
import { WaveRing } from "../../ui/WaveRing";
import { GuideVideo } from "../../parts/GuideVideo";
import "./Game.css";

type Filter = "earned" | "left";

export function Achievements({
  platform: firstPlatform,
  titleId: firstTitle,
  name,
  cover,
  person,
  lists,
  onClose,
  layer,
}: {
  platform: string;
  titleId: string;
  name: string | null;
  cover?: string | null;
  person: { id: number; name: string } | null;
  lists?: { platform: string; title_id: string; count?: number }[];
  onClose: () => void;
  layer: string;
}) {
  const { data, tr, locale, me } = useApp();
  // A game played on several platforms has a list on each: one shown at a time.
  const [shownList, setShownList] = useState({ platform: firstPlatform, titleId: firstTitle });
  const { platform, titleId } = shownList;
  const theirs = person && person.id !== me.person_id ? person : null;
  const key = `${platform}:${titleId}:${theirs?.id ?? "me"}`;
  const list = useLoad<GameDetails>(
    `list:${key}`,
    async () => {
      const res = await gamesApi.fetchGame(data, platform, titleId, { personId: theirs?.id });
      remember("list", key, res);
      return res;
    },
    recall<GameDetails>("list", key),
  );
  const mine = useLoad<GameDetails>(theirs ? `list:${platform}:${titleId}:me` : null, () =>
    gamesApi.fetchGame(data, platform, titleId),
  );
  const [guides, setGuides] = useState<GameGuidesResponse | null>(null);
  useEffect(() => {
    let live = true;
    let timer = 0;
    const ask = (tries: number) => {
      gamesApi
        .fetchGameGuides(data, platform, titleId)
        .then((res) => {
          if (!live) return;
          setGuides(res);
          if (!res.complete && tries < 6) timer = window.setTimeout(() => ask(tries + 1), 8000);
        })
        .catch(() => undefined);
    };
    ask(0);
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [data, platform, titleId]);

  const d = list.data;
  const [filter, setFilter] = useState<Filter | null>(null);
  const earnedCount = d?.achievements.filter((a) => a.is_unlocked).length ?? 0;
  const shown: Filter = filter ?? (earnedCount > 0 ? "earned" : "left");
  const myUnlocked = useMemo(
    () => new Set((mine.data?.achievements ?? []).filter((a) => a.is_unlocked).map((a) => a.achievement_id)),
    [mine.data],
  );

  const rows = useMemo(() => {
    if (!d) return [];
    const picked = d.achievements.filter((a) => (shown === "earned" ? a.is_unlocked : !a.is_unlocked));
    if (shown === "earned") picked.sort((a, b) => (b.unlocked_at ?? "").localeCompare(a.unlocked_at ?? ""));
    return picked;
  }, [d, shown]);

  const groups = d && d.groups.length > 1 ? d.groups : null;
  const owner = theirs ?? { id: me.person_id, name: me.handle?.display ?? "" };
  const gameName = d?.name ?? name ?? "";

  const score = useMemo(() => {
    if (!d) return null;
    const got = d.achievements.filter((a) => a.is_unlocked);
    // The app's own points, earned of all the list's (`views.POINTS`).
    const worth = (a: GameAchievement) => pointsOf(a.rarity_percent, { trophy: a.trophy_type });
    const pts = got.reduce((n, a) => n + worth(a), 0);
    const allPts = d.achievements.reduce((n, a) => n + worth(a), 0);
    return { pts, allPts };
  }, [d]);

  const row = (a: GameAchievement) => {
    const ach = achOfList(a, { platform, titleId, game: gameName, icon: d?.icon_url ?? null }, owner, locale);
    const hasTip = Boolean(guides?.tips[a.achievement_id]);
    const hasVideo = Boolean(guides?.videos?.[a.achievement_id]?.length);
    return (
      <div key={a.achievement_id} className="list-row">
        <AchRow
          ach={ach}
          plain
          date={!theirs && a.is_unlocked && a.unlocked_at ? dayLabel(a.unlocked_at, locale) : null}
          extra={
            theirs || hasTip || hasVideo ? (
              <span className="list-extra">
                {theirs && (
                  <span className="compare">
                    <span className={a.is_unlocked ? "on" : ""} title={theirs.name}>
                      <Face personId={theirs.id} name={theirs.name} size={20} />
                    </span>
                    <span className={myUnlocked.has(a.achievement_id) ? "on" : ""} title={tr("you")}>
                      <Face personId={me.person_id} name={me.handle?.display ?? ""} size={20} />
                    </span>
                  </span>
                )}
                {hasVideo && <Icon name="play" size={14} />}
                {hasTip && <Icon name="news" size={14} />}
              </span>
            ) : null
          }
        />
      </div>
    );
  };

  const done = Boolean(d && d.achievements_total > 0 && d.achievements_unlocked >= d.achievements_total);
  const share = d && d.achievements_total ? Math.round((d.achievements_unlocked / d.achievements_total) * 100) : null;

  const theme = useArtTheme(gameArtOf(`${platform}:${titleId}`, gameName) ?? d?.icon_url ?? cover);
  return (
    <Page title={gameName} onBack={onClose} hero layer={layer} className="list-page" style={theme.style}>
      <Hero ground={d?.icon_url ?? cover}>
        <span className="list-ring">
          <WaveRing value={d?.achievements_unlocked ?? 0} total={d?.achievements_total ?? 0} size={184}>
            <Cover src={d?.icon_url ?? cover} className="list-cover" />
          </WaveRing>
          {done && <DoneMark size={52} className="list-done" />}
        </span>
        <p className="list-name t-title clamp-2">{gameName}</p>
        {theirs && (
          <span className="list-owner">
            <Face personId={theirs.id} name={theirs.name} size={22} />
            {theirs.name}
          </span>
        )}
        {!d && (
          <span className="list-stats" aria-hidden="true">
            <span className="list-ghost list-ghost-num" />
            <span className="list-ghost" />
            <span className="list-ghost" />
          </span>
        )}
        {d && (
          <span className={`list-stats${done ? " list-stats-done" : ""}`}>
            <b className="t-num">
              {d.achievements_unlocked}
              <small>/{d.achievements_total}</small>
            </b>
            {share != null && !done && <span className="list-pct">{`${share} %`}</span>}
            {score && score.allPts > 0 && (
              <span className="list-gs">
                {num(score.pts, locale)} / {num(score.allPts, locale)} {plural(locale, score.allPts, ["ptsOne", "ptsFew", "ptsMany"])}
              </span>
            )}
          </span>
        )}
      </Hero>
      {lists && lists.length > 1 && (
        <PlatformTabs
          className="list-plats"
          lists={lists}
          value={`${platform}:${titleId}`}
          onChange={(v) => {
            const next = lists.find((l) => `${l.platform}:${l.title_id}` === v);
            if (!next) return;
            setFilter(null);
            setShownList({ platform: next.platform, titleId: next.title_id });
          }}
        />
      )}
      {guides?.guide && (
        <div className="list-guide">
          <GuideVideo guide={guides.guide} />
        </div>
      )}
      {d && (
        <div className="list-filter">
          <Segmented
            options={[
              { value: "earned", label: `${tr("gameFilterUnlocked")} ${earnedCount}` },
              { value: "left", label: `${tr("gameFilterLocked")} ${(d?.achievements.length ?? 0) - earnedCount}` },
            ]}
            value={shown}
            onChange={setFilter}
          />
        </div>
      )}

      {!d && list.loading && (
        <div className="list-body list-skel" aria-hidden="true">
          <span className="skel list-skel-filter" />
          <div className="list-items">
            {Array.from({ length: 6 }, (_, i) => (
              <div key={i} className="list-row">
                <div className="ach-row ach-row-plain">
                  <span className="skel ach-pic-wide" />
                  <span className="ach-text">
                    <span className="skel skel-line" style={{ width: "55%" }} />
                    <span className="skel skel-line" style={{ width: "85%" }} />
                    <span className="skel skel-line" style={{ width: "40%" }} />
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      {!d && list.error ? <Empty icon="refresh" title={tr("loadFailed")} action={<Button variant="tonal" onClick={list.reload}>{tr("retry")}</Button>} /> : null}
      {d && d.achievements.length === 0 && <Empty icon="trophy" title={tr("gameEmpty")} />}
      {d && d.achievements.length > 0 && rows.length === 0 && <Empty icon="check" title={tr("emptyFilter")} />}

      <div className="list-body">
        {groups
          ? groups.map((g) => {
              const inGroup = rows.filter((a) => (a.trophy_group_id ?? "default") === g.group_id);
              if (!inGroup.length) return null;
              const all = d!.achievements.filter((a) => (a.trophy_group_id ?? "default") === g.group_id);
              return (
                <section key={g.group_id}>
                  <h2 className="list-group">
                    <span>{groupLabel(g, locale, gameName)}</span>
                    <span className="list-group-num">
                      {all.filter((a) => a.is_unlocked).length}/{all.length}
                    </span>
                  </h2>
                  <div className="list-items">{inGroup.map(row)}</div>
                </section>
              );
            })
          : rows.length > 0 && <div className="list-items">{rows.map(row)}</div>}
      </div>
    </Page>
  );
}
