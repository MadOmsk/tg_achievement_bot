import { useEffect, useMemo, useState } from "react";
import { clubApi, gameApi, type OnlineMember } from "../../api";
import { gameLines, MonthGames } from "../../parts/MonthGames";
import { InstallCard } from "../../parts/InstallCard";
import { FAVORITES_CHANGED } from "../../parts/FollowButton";
import { peopleApi } from "../../api/people/peopleApi";
import { useApp } from "../../app/context";
import { useLoad } from "../../app/useLoad";
import { achOfFeed } from "../../app/views";
import { cachedHome, rememberHome } from "../../core/home-cache";
import { currentMonth, formatMonth } from "../../core/people-utils";
import { capital, monthName, recentMonths } from "../../parts/Months";
import { Button, Empty, IconButton } from "../../ui/Controls";
import { Face, type Presence } from "../../ui/Face";
import { tick } from "../../core/haptic";
import { FavoriteGames } from "../../parts/FavoriteGames";
import { MonthHero } from "../../parts/MonthHero";
import { AchTile } from "../../parts/AchTile";
import "./Home.css";

function presenceOf(m: OnlineMember | undefined): Presence {
  if (!m) return null;
  if (m.playing) return "playing";
  return m.state === "Online" ? "online" : null;
}

export function Home({ refreshKey }: { refreshKey: number }) {
  const { data, me, tr, locale, open } = useApp();
  const cache = useMemo(() => cachedHome(me.person_id), [me.person_id]);
  const thisMonth = currentMonth();
  const mine = useLoad(
    `mine:${refreshKey}`,
    () => clubApi.fetchPerson(data, null, me.person_id),
    cache?.mine,
  );
  const [month, setMonth] = useState(thisMonth);
  const shownKey = mine.data?.month_key ?? thisMonth;
  const other = useLoad(month === shownKey ? null : `m:${month}:${refreshKey}`, () =>
    clubApi.fetchPerson(data, null, me.person_id, { month }),
  );
  const online = useLoad(`online:${refreshKey}`, () => clubApi.fetchOnline(data, "following"), cache?.online);
  const following = useLoad(`following:${refreshKey}`, () => peopleApi.following(data), cache?.following);
  const favs = useLoad(`favs:${refreshKey}`, () => gameApi.favorites(data), cache?.favs);
  useEffect(() => {
    const changed = () => favs.reload();
    window.addEventListener(FAVORITES_CHANGED, changed);
    return () => window.removeEventListener(FAVORITES_CHANGED, changed);
  }, [favs.reload]);

  useEffect(() => {
    if (mine.data) rememberHome(me.person_id, { mine: mine.data });
  }, [mine.data, me.person_id]);
  useEffect(() => {
    if (online.data) rememberHome(me.person_id, { online: online.data });
  }, [online.data, me.person_id]);
  useEffect(() => {
    if (favs.data) rememberHome(me.person_id, { favs: favs.data });
  }, [favs.data, me.person_id]);
  useEffect(() => {
    if (following.data) rememberHome(me.person_id, { following: following.data });
  }, [following.data, me.person_id]);

  const hasAccount = me.xbox.linked || me.steam.linked || me.psn.linked;
  const payload = mine.data;
  const monthPayload = month === shownKey ? payload : other.data;
  const games = monthPayload ? gameLines(monthPayload) : [];
  const recent = (payload?.feed ?? []).slice(0, 12);

  const friends = new Set(
    (following.data?.people ?? []).filter((p) => p.relation.friends).map((p) => p.id),
  );
  const people = (online.data?.members ?? []).filter((m) => m.person_id !== me.person_id).sort(
    (a, b) =>
      Number(friends.has(b.person_id)) - Number(friends.has(a.person_id)) ||
      Number(b.playing) - Number(a.playing) ||
      Number(b.state === "Online") - Number(a.state === "Online"),
  );
  const mePresence = payload?.presence;

  return (
    <div className="home">
      <header className="home-top">
        <button
          type="button"
          className="home-me"
          onClick={() => {
            tick();
            open({ kind: "person", personId: me.person_id });
          }}
        >
          <span className="home-me-face shape-cookie9">
            <Face personId={me.person_id} name={me.handle?.display ?? ""} size={48} />
          </span>
          <span className="home-me-text">
            {mePresence?.playing && mePresence.title_name ? (
              <>
                <span className="home-me-name clamp-1">{me.handle?.display}</span>
                <span className="home-me-status">
                  <span className="home-me-dot" />
                  <span className="clamp-1">{mePresence.title_name}</span>
                </span>
              </>
            ) : (
              <>
                <span className="t-meta">{tr("homeHello")}</span>
                <span className="home-me-name clamp-1">{me.handle?.display}</span>
              </>
            )}
          </span>
        </button>
        <IconButton
          icon="bell"
          label={tr("notificationsTitle")}
          badge={me.notifications_unread}
          onClick={() => open({ kind: "notifications" })}
        />
        <IconButton icon="settings" label={tr("settings")} onClick={() => open({ kind: "settings", pane: "root" })} />
      </header>

      <InstallCard />

      {!hasAccount && (
        <section className="home-welcome">
          <p className="t-title">{tr("welcomeTitle")}</p>
          <p className="t-body">{tr("welcomeText")}</p>
          <div className="home-welcome-buttons">
            <Button variant="filled" onClick={() => open({ kind: "settings", pane: "accounts" })}>
              {tr("welcomeXbox")}
            </Button>
            <Button variant="tonal" onClick={() => open({ kind: "connect", platform: "psn" })}>
              {tr("welcomePsn")}
            </Button>
            <Button variant="tonal" onClick={() => open({ kind: "connect", platform: "steam" })}>
              {tr("welcomeSteam")}
            </Button>
          </div>
        </section>
      )}

      {hasAccount && (
        <MonthHero
          payload={monthPayload}
          month={month}
          months={mine.data?.months?.length ? mine.data.months : recentMonths(12)}
          onMonth={setMonth}
          personId={me.person_id}
          season
        />
      )}


      {hasAccount && (
        <section className="sec">
          <div className="sec-head">
            <h2 className="t-title">{tr("homeRecent")}</h2>
          </div>
          {payload && recent.length === 0 ? (
            <Empty icon="trophy" title={tr("emptyTitleNow")} text={tr("emptyHomeHint")} />
          ) : (
            <div className="rail">
              {payload ? (
                recent.map((item) => <AchTile key={`${item.title_id}:${item.achievement_id}`} ach={achOfFeed(item)} />)
              ) : (
                [0, 1, 2].map((i) => <span key={i} className="tile tile-skel skel" />)
              )}
            </div>
          )}
        </section>
      )}

      <section className="sec">
        <div className="sec-head">
          <h2 className="t-title">{tr("homeNow")}</h2>
          {people.length > 0 && (
            <button type="button" className="link-btn" onClick={() => open({ kind: "follows", personId: null, which: "following" })}>
              {tr("seeAll")}
            </button>
          )}
        </div>
        {online.data && people.length === 0 ? (
          <Empty
            icon="people"
            title={tr("homeNowEmpty")}
            text={tr("followingEmpty")}
            action={
              <Button variant="tonal" icon="search" onClick={() => open({ kind: "search" })}>
                {tr("homeFindPeople")}
              </Button>
            }
          />
        ) : (
          <div className="rail now-rail">
            {people.map((m) => {
              const p = presenceOf(m);
              return (
                <button
                  key={m.person_id}
                  type="button"
                  className={`now-person${p ? "" : " now-off"}`}
                  onClick={() => {
                    tick();
                    open({ kind: "person", personId: m.person_id });
                  }}
                >
                  <Face personId={m.person_id} name={m.name} size={68} presence={p} thinRing />
                  <span className="now-name clamp-1">{m.name}</span>
                  <span className="now-status clamp-1">
                    {m.playing ? m.title_name || tr("playing") : p === "online" ? tr("idle") : tr("nowOffline")}
                  </span>
                </button>
              );
            })}
            {!online.data && [0, 1, 2, 3].map((i) => <span key={i} className="now-skel skel shape-cookie12" />)}
          </div>
        )}
      </section>

      {hasAccount && (
        <section className="sec">
          <div className="sec-head">
            <h2 className="t-title">{tr("homeGamesOf").replace("{month}", monthName(month, locale))}</h2>
            {me.role === "superadmin" && (
              <button type="button" className="link-btn" onClick={() => open({ kind: "addGame" })}>
                {tr("addGameButton")}
              </button>
            )}
          </div>
          {monthPayload && games.length === 0 ? (
            <Empty icon="gamepad" title={capital(formatMonth(month, locale, "sheet"))} text={tr("emptyTitlePast")} />
          ) : (
            <MonthGames games={games} person={null} loading={!monthPayload} />
          )}
        </section>
      )}

      <section className="sec">
        <div className="sec-head">
          <h2 className="t-title">{tr("gpFavoritesTitle")}</h2>
        </div>
        {/* The hint only while there is nothing to show. */}
        <FavoriteGames games={favs.data?.games ?? []} hint={favs.data && !favs.data.games.length ? tr("gpFavoritesEmpty") : undefined} />
      </section>
    </div>
  );
}
