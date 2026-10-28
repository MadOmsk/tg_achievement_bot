import { useEffect, useRef, useState } from "react";
import { clubApi, gameApi } from "../../api";
import { peopleApi, type PersonProfile, type Relation } from "../../api/people/peopleApi";
import { useApp } from "../../app/context";
import { useLoad } from "../../app/useLoad";
import { currentMonth } from "../../core/people-utils";
import { tick } from "../../core/haptic";
import { num } from "../../i18n";
import { FAVORITES_CHANGED, FOLLOWS_CHANGED } from "../../parts/FollowButton";
import { monthName, recentMonths } from "../../parts/Months";
import { gameLines, MonthGames } from "../../parts/MonthGames";
import { AchTile } from "../../parts/AchTile";
import { achOfFeed } from "../../app/views";
import { AccountChip } from "../../parts/AccountCard";
import { Button, Empty, IconButton, Row, Section } from "../../ui/Controls";
import { Face, faceSrc, knownName } from "../../ui/Face";
import { Icon } from "../../ui/Icon";
import { BarAction, Confirm, Page, Sheet } from "../../ui/Page";
import { openImage } from "../../ui/Viewer";
import { FavoriteGames } from "../../parts/FavoriteGames";
import { MonthHero } from "../../parts/MonthHero";
import "./People.css";

export function PersonPage({ personId, onClose, layer }: { personId: number; onClose: () => void; layer: string }) {
  const { data, tr, locale, me, open, toast } = useApp();
  const self = personId === me.person_id;
  const card = useLoad<PersonProfile>(`card:${personId}`, () => peopleApi.profile(data, personId));
  const [month, setMonth] = useState(currentMonth());
  const activity = useLoad(`person:${personId}:${month}`, () => clubApi.fetchPerson(data, null, personId, { month }));
  const favs = useLoad(`favs:${personId}`, () => gameApi.favorites(data, personId));
  useEffect(() => {
    if (!self) return;
    const changed = () => favs.reload();
    window.addEventListener(FAVORITES_CHANGED, changed);
    return () => window.removeEventListener(FAVORITES_CHANGED, changed);
  }, [self, favs.reload]);
  const [relation, setRelation] = useState<Relation | null>(null);
  const [menu, setMenu] = useState(false);
  const [askBlock, setAskBlock] = useState(false);
  const [askUnfollow, setAskUnfollow] = useState(false);
  const followAt = useRef<HTMLButtonElement>(null);

  const c = card.data;
  const rel = relation ?? c?.relation ?? null;
  const a = activity.data;
  const hidden = Boolean(a?.hidden) || (c ? !c.can_view && !self : false);
  const name = c?.handle ?? a?.name ?? knownName(personId) ?? "";
  const presence = a?.presence ?? c?.activity?.presence ?? null;

  const block = async (on: boolean) => {
    try {
      const res = on ? await peopleApi.block(data, personId) : await peopleApi.unblock(data, personId);
      setRelation(res.relation);
      window.dispatchEvent(new Event(FOLLOWS_CHANGED));
    } catch {
      toast(tr("somethingWrong"), "error");
    }
  };

  const follow = async () => {
    try {
      const res = await peopleApi.follow(data, personId);
      setRelation(res.relation);
      window.dispatchEvent(new Event(FOLLOWS_CHANGED));
    } catch {
      toast(tr("followTooSoon"), "error");
    }
  };

  const unfollow = async () => {
    try {
      const res = await peopleApi.unfollow(data, personId);
      setRelation(res.relation);
      window.dispatchEvent(new Event(FOLLOWS_CHANGED));
    } catch {
      toast(tr("somethingWrong"), "error");
    }
  };

  return (
    <Page
      title={name}
      onBack={onClose}
      layer={layer}
      hero
      actions={
        self ? (
          <IconButton icon="settings" label={tr("settings")} variant="plain" onClick={() => open({ kind: "settings", pane: "profile" })} />
        ) : null
      }
    >
      <header className="pp-head">
        <Backdrop key={personId} personId={personId} />
        <button type="button" className="pp-face" onClick={() => void faceSrc(personId).then((src) => src && openImage(src))} aria-label={name}>
          <Face personId={personId} name={name || "?"} size={112} thinRing presence={presence?.playing ? "playing" : presence?.state === "Online" ? "online" : null} />
        </button>
        {name ? <h1 className="pp-name">{name}</h1> : <span className="skel pp-skel-name" />}
        {!hidden && (c?.activity?.platforms?.length ?? 0) > 0 && (
          <div className="pp-accs">
            {c!.activity!.platforms.map((p) => (
              <AccountChip key={`${p.platform}:${p.name}`} p={p} />
            ))}
          </div>
        )}
        <div className="pp-tags">
          {!rel?.friends && rel?.followed_by && <span className="chip chip-outline">{tr("followsYou")}</span>}
          {rel?.blocked && <span className="chip chip-outline chip-danger">{tr("stateBlocked")}</span>}
          {presence?.playing && presence.title_name && (
            <span className="chip chip-outline">
              {tr("playing")} · {presence.title_name}
            </span>
          )}
          {!presence?.playing && presence?.state === "Online" && <span className="chip chip-outline">{tr("idle")}</span>}
        </div>
      </header>

      {!c && (
        <div className="pp-skel" aria-hidden="true">
          <span className="skel pp-skel-chip" />
          <div className="pp-counts">
            {[0, 1, 2].map((i) => (
              <span key={i} className="skel" />
            ))}
          </div>
        </div>
      )}
      {c && (
        <div className="pp-counts">
          <button type="button" onClick={() => (c.can_view || self) && open({ kind: "follows", personId: self ? null : personId, which: "following" })}>
            <b className="t-num">{num(c.following, locale)}</b>
            <span>{tr("peopleFollowing")}</span>
          </button>
          <button type="button" onClick={() => (c.can_view || self) && open({ kind: "follows", personId: self ? null : personId, which: "followers" })}>
            <b className="t-num">{num(c.followers, locale)}</b>
            <span>{tr("peopleFollowers")}</span>
          </button>
          {!self && rel && !rel.blocked && (
            <button
              ref={followAt}
              type="button"
              className={`pp-count-follow${rel.following ? " pp-count-on" : ""}`}
              onClick={() => {
                tick();
                setMenu(true);
              }}
            >
              <Icon name={rel.following ? "check" : "plus"} size={22} />
              <span className="pp-follow-label">
                {rel.friends
                  ? tr("friendsBtn")
                  : rel.following
                    ? tr("followingBtn")
                    : tr("notFollowing")}
                <Icon name="down" size={14} />
              </span>
            </button>
          )}
        </div>
      )}
      {!self && rel && !rel.blocked && (
        <BarAction anchor={followAt}>
          <button
            type="button"
            className={`pp-bar-follow${rel.following ? " pp-bar-on" : ""}`}
            aria-label={rel.friends ? tr("friendsBtn") : rel.following ? tr("followingBtn") : tr("follow")}
            onClick={() => {
              tick();
              setMenu(true);
            }}
          >
            <Icon name={rel.following ? "check" : "plus"} size={18} />
            <span>{rel.friends ? tr("friendsBtn") : rel.following ? tr("followingBtn") : tr("follow")}</span>
          </button>
        </BarAction>
      )}
      {!self && rel?.blocked && (
        <div className="pp-actions">
          <Button variant="tonal" icon="block" onClick={() => void block(false)}>
            {tr("unblock")}
          </Button>
        </div>
      )}
      {menu && rel && (
        <Sheet onClose={() => setMenu(false)} title={name} layer="person-menu">
          <div className="group">
            <div className="group-items">
              {!rel.following && (
                <Row
                  lead={<Icon name="plus" />}
                  title={rel.followed_by ? tr("followBack") : tr("follow")}
                  onClick={() => {
                    setMenu(false);
                    void follow();
                  }}
                />
              )}
              {rel.following && (
                <Row
                  lead={<Icon name="close" />}
                  title={tr("unfollow")}
                  onClick={() => {
                    setMenu(false);
                    setAskUnfollow(true);
                  }}
                />
              )}
              <Row
                lead={<Icon name="block" />}
                title={tr("block")}
                sub={tr("blockHint")}
                danger
                onClick={() => {
                  setMenu(false);
                  setAskBlock(true);
                }}
              />
            </div>
          </div>
        </Sheet>
      )}
      {askUnfollow && (
        <Confirm
          text={tr("confirmUnfollow")}
          yes={tr("unfollow")}
          no={tr("cancel")}
          onYes={() => {
            setAskUnfollow(false);
            void unfollow();
          }}
          onNo={() => setAskUnfollow(false)}
        />
      )}
      {askBlock && (
        <Confirm
          text={tr("confirmBlock")}
          yes={tr("block")}
          no={tr("cancel")}
          danger
          onYes={() => {
            setAskBlock(false);
            setMenu(false);
            void block(true);
          }}
          onNo={() => setAskBlock(false)}
        />
      )}

      {!hidden && (a || activity.loading) && (
        <div className="pp-hero">
          <MonthHero
            payload={a}
            month={month}
            months={a?.months?.length ? a.months : recentMonths(12)}
            onMonth={setMonth}
            personId={personId}
          />
        </div>
      )}

      {hidden && <Empty icon="lock" title={tr("activityHidden")} text={tr("activityHiddenHint")} />}


      {!hidden && (
        <Section title={tr("recentUnlocks")}>
          {a && (a.feed ?? []).length === 0 ? (
            <Empty icon="trophy" title={tr("emptyPersonTitle")} />
          ) : (
            <div className="rail">
              {(a ? a.feed.slice(0, 12) : Array.from({ length: 3 }, () => null)).map((item, i) =>
                item ? (
                  <AchTile key={`${item.title_id}:${item.achievement_id}`} ach={achOfFeed(item)} />
                ) : (
                  <span key={i} className="tile tile-skel skel" />
                ),
              )}
            </div>
          )}
        </Section>
      )}

      {!hidden && a && a.games.length > 0 && (
        <Section title={tr("homeGamesOf").replace("{month}", monthName(month, locale))}>
          <MonthGames games={gameLines(a)} person={{ id: personId, name }} loading={false} />
        </Section>
      )}

      {!hidden && (favs.data?.games.length ?? 0) > 0 && (
        <Section title={tr("gpFavoritesTitle")}>
          <FavoriteGames games={favs.data!.games} />
        </Section>
      )}
    </Page>
  );
}

/** The face again behind the head, blurred into a glow of its colours. */
function Backdrop({ personId }: { personId: number }) {
  const [src, setSrc] = useState<string | null>(null);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    let live = true;
    void faceSrc(personId).then((url) => live && setSrc(url));
    return () => {
      live = false;
    };
  }, [personId]);
  return (
    <span className={`pp-backdrop${shown ? " on" : ""}`} aria-hidden="true">
      {src && <img src={src} alt="" onLoad={() => setShown(true)} />}
    </span>
  );
}
