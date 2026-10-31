import { useEffect, useRef, useState } from "react";
import { adminApi, clubApi, gameApi } from "../../api";
import type { Role } from "../../api/admin/adminApi";
import { peopleApi, type PersonProfile, type Relation } from "../../api/people/peopleApi";
import { useApp } from "../../app/context";
import { useArtTheme } from "../../app/artTheme";
import { AccountChip } from "../../parts/AccountCard";
import { useLoad } from "../../app/useLoad";
import { currentMonth } from "../../core/people-utils";
import { tick } from "../../core/haptic";
import { num, type TranslationKey } from "../../i18n";
import { FAVORITES_CHANGED, FOLLOWS_CHANGED } from "../../parts/FollowButton";
import { monthName, recentMonths } from "../../parts/Months";
import { gameLines, MonthGames } from "../../parts/MonthGames";
import { AchTile } from "../../parts/AchTile";
import { achOfFeed } from "../../app/views";
import { gameArtOf } from "../../app/artTheme";
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
  const followAt = useRef<HTMLDivElement>(null);

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

  const [face, setFace] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    void faceSrc(personId).then((url) => live && setFace(url));
    return () => {
      live = false;
    };
  }, [personId]);
  const faceArt = useArtTheme(face);
  // The banner: the art of the game of their latest achievement, as the
  // catalog has it — the feed item carries it, so it is known with the rest.
  const latest = a?.feed?.[0];
  const chosen = latest
    ? latest.game_hero ||
      latest.game_poster ||
      gameArtOf(latest.game_id ? `g${latest.game_id}` : null, `${latest.platform}:${latest.title_id}`, latest.game) ||
      latest.game_icon_url ||
      null
    : null;
  const kept = useRef<{ person: number; src: string | null } | null>(null);
  if (kept.current?.person !== personId) kept.current = null;
  if (!kept.current && a) kept.current = { person: personId, src: chosen };
  const banner = kept.current?.src ?? null;
  // Their own picture stands in only once it is known there is no game's art.
  const bannerKnown = kept.current != null;
  const [roling, setRoling] = useState(false);

  return (
    <Page
      title={name}
      onBack={onClose}
      layer={layer}
      hero
      // The page takes its colours from the face, as a game's from its art.
      style={faceArt.style}
      actions={
        self ? (
          <IconButton icon="settings" label={tr("settings")} variant="plain" onClick={() => open({ kind: "settings", pane: "profile" })} />
        ) : me.role === "superadmin" ? (
          // The super-admin's own menu on another person: their role.
          <IconButton icon="more" label={tr("roleTitle")} variant="plain" onClick={() => setRoling(true)} />
        ) : null
      }
    >
      {/* Headed as a game is (owner, 2026-10-29): a picture across the top —
          the art of the game of their latest achievement, else their own
          picture blurred —, the face where a game's poster sits, the name
          and the accounts beside it. */}
      <div className="pp-banner">
        {banner ? (
          <img src={banner} alt="" />
        ) : bannerKnown && face ? (
          <img src={face} alt="" className="pp-banner-face" />
        ) : (
          <span className="pp-banner-empty" />
        )}
      </div>
      <header className="pp-head2">
        <button type="button" className="pp-face" onClick={() => void faceSrc(personId).then((src) => src && openImage(src))} aria-label={name}>
          <Face personId={personId} name={name || "?"} size={128} thinRing presence={presence?.playing ? "playing" : presence?.state === "Online" ? "online" : null} />
        </button>
        <div className="pp-titles">
          {name ? <h1 className="pp-name2 clamp-2">{name}</h1> : <span className="skel pp-skel-name" />}
          {/* What they are doing and how they stand to you: one quiet line. */}
          {(presence?.playing || presence?.state === "Online" || (!rel?.friends && rel?.followed_by) || rel?.blocked) && (
            <p className="pp-status">
              {(presence?.playing || presence?.state === "Online") && <span className={`pp-dot${presence?.playing ? " pp-dot-play" : ""}`} />}
              <span className="clamp-1">
                {[
                  presence?.playing && presence.title_name ? `${tr("playing")} · ${presence.title_name}` : presence?.state === "Online" ? tr("idle") : null,
                  !rel?.friends && rel?.followed_by ? tr("followsYou") : null,
                  rel?.blocked ? tr("stateBlocked") : null,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            </p>
          )}
          {!hidden && (c?.activity?.platforms?.length ?? 0) > 0 && (
            <div className="pp-accs2">
              {c!.activity!.platforms.map((p) => (
                <AccountChip key={`${p.platform}:${p.name}`} p={p} />
              ))}
            </div>
          )}
        </div>
      </header>

      {!c && (
        <div className="pp-skel" aria-hidden="true">
          <div className="pp-row pp-skel-row">
            <div className="pp-figs">
              {[0, 1, 2].map((i) => (
                <span key={i} className="skel pp-skel-fig" />
              ))}
            </div>
            {!self && <span className="skel pp-skel-btn" />}
          </div>
        </div>
      )}
      {c && (
        <div className="pp-row">
          <div className="pp-figs">
            <button type="button" onClick={() => (c.can_view || self) && open({ kind: "follows", personId: self ? null : personId, which: "following" })}>
              <b className="t-num">{num(c.following, locale)}</b>
              <span>{tr("peopleFollowing")}</span>
            </button>
            <button type="button" onClick={() => (c.can_view || self) && open({ kind: "follows", personId: self ? null : personId, which: "followers" })}>
              <b className="t-num">{num(c.followers, locale)}</b>
              <span>{tr("peopleFollowers")}</span>
            </button>
          </div>
          {/* The page's one action: following — filled to start, tonal once on. */}
          {!self && rel && !rel.blocked && (
            <div className="pp-follow" ref={followAt}>
              <Button
              variant={rel.following ? "tonal" : "filled"}
              icon={rel.following ? "check" : "plus"}
              onClick={() => {
                tick();
                if (rel.following) setMenu(true);
                else void follow();
              }}
            >
              {rel.friends ? tr("friendsBtn") : rel.following ? tr("followingBtn") : rel.followed_by ? tr("followBack") : tr("follow")}
            </Button>
            </div>
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
              {a ? (
                a.feed.slice(0, 12).map((item) => (
                  <AchTile key={`${item.title_id}:${item.achievement_id}`} ach={achOfFeed(item)} />
                ))
              ) : (
                [0, 1, 2].map((i) => <span key={i} className="tile tile-skel skel" />)
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
      {roling && <RoleSheet personId={personId} onClose={() => setRoling(false)} />}
    </Page>
  );
}

const ROLES: Array<{ role: Role; title: TranslationKey; about: TranslationKey }> = [
  { role: "user", title: "roleUser", about: "roleUserAbout" },
  { role: "admin", title: "roleAdmin", about: "roleAdminAbout" },
  { role: "superadmin", title: "roleSuperadmin", about: "roleSuperadminAbout" },
];

/** One step up or down, as the bot's card does (#232): the registry's role
 * actions, so the server says whether a step is allowed and asks first. */
const STEPS: Partial<Record<`${Role}>${Role}`, string>> = {
  "user>admin": "make_admin",
  "admin>superadmin": "make_superadmin",
  "admin>user": "unmake_admin",
  "superadmin>admin": "unmake_superadmin",
};

/** The super-admin gives a person a role (owner, 2026-10-28). */
function RoleSheet({ personId, onClose }: { personId: number; onClose: () => void }) {
  const { data, tr, toast } = useApp();
  const [state, setState] = useState<{ role: Role; fixed: boolean } | null>(null);
  const [ask, setAsk] = useState<{ action: string; to: Role; text: string; yes: string; step: number } | null>(null);
  useEffect(() => {
    let live = true;
    adminApi
      .fetchRole(data, personId)
      .then((r) => live && setState({ role: r.role, fixed: r.fixed }))
      .catch(() => live && toast(tr("somethingWrong"), "error"));
    return () => {
      live = false;
    };
  }, [data, personId, toast, tr]);
  const stepTo = (role: Role) => (state && !state.fixed ? STEPS[`${state.role}>${role}`] : undefined);
  const run = async (action: string, to: Role, step: number) => {
    try {
      const res = await adminApi.postAction(data, { scope: "user", target: `p${personId}`, action, step });
      if (res.confirm) {
        setAsk({ action, to, text: res.confirm.text, yes: res.confirm.yes, step: res.confirm.step });
        return;
      }
      if (res.done?.ok && state) {
        setState({ ...state, role: to });
        toast(tr("roleSaved"));
      } else if (res.done?.text) {
        toast(res.done.text, "error");
      }
    } catch {
      toast(tr("somethingWrong"), "error");
    }
  };
  const pick = (role: Role) => {
    const action = stepTo(role);
    if (!action) return;
    tick();
    void run(action, role, 0);
  };
  return (
    <Sheet title={tr("roleTitle")} onClose={onClose} layer="role">
      {state?.fixed && <p className="pp-role-note">{tr("roleFixed")}</p>}
      <div className="group">
        <div className="group-items">
          {ROLES.map((r) => (
            <Row
              key={r.role}
              title={tr(r.title)}
              sub={tr(r.about)}
              trail={state?.role === r.role ? <Icon name="check" size={20} /> : undefined}
              onClick={stepTo(r.role) ? () => pick(r.role) : undefined}
            />
          ))}
        </div>
      </div>
      {ask && (
        <Confirm
          text={ask.text}
          yes={ask.yes}
          no={tr("cancel")}
          onYes={() => {
            const a = ask;
            setAsk(null);
            void run(a.action, a.to, a.step);
          }}
          onNo={() => setAsk(null)}
        />
      )}
    </Sheet>
  );
}
