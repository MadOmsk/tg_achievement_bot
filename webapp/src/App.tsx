import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, userApi, WEB_SESSION, type MeResponse } from "./api";
import { peopleApi } from "./api/people/peopleApi";
import { AppContext, DEFAULT_PICTURE, translator, type App as AppValue } from "./app/context";
import { followTheme, inTelegram, paintTelegram, surfaceColor } from "./app/env";
import { TABS, type Layer, type Tab } from "./app/layers";
import { LayerView, barShownOver, prefetchLayers } from "./app/LayerView";
import { useBackHandler } from "./core/back-stack";
import { cachedMe, forgetHome, rememberMe } from "./core/home-cache";
import { initData, launchContext, localeOf, savePlace, setWebSession } from "./core/launch";
import type { TranslationKey } from "./i18n";
import { Home } from "./screens/home/Home";
const Feed = lazy(() => import("./screens/feed/Feed").then((m) => ({ default: m.Feed })));
const Ranking = lazy(() => import("./screens/ranking/Ranking").then((m) => ({ default: m.Ranking })));
const SignIn = lazy(() => import("./screens/signin/SignIn").then((m) => ({ default: m.SignIn })));
import { FirstRun } from "./screens/signin/FirstRun";
import { FOLLOWS_CHANGED } from "./parts/FollowButton";
import { BottomBar } from "./ui/BottomBar";
import { ImageViewer } from "./ui/Viewer";
import { Button } from "./ui/Controls";
import { showToast, Toaster } from "./ui/Toast";
import "./styles/tokens.css";
import "./styles/base.css";
import "./ui/ui.css";
import "./App.css";

type Boot =
  | { status: "loading" }
  | { status: "login" }
  | { status: "error"; message: string }
  | { status: "ok"; me: MeResponse };

const deviceLocale = () => (navigator.language.toLowerCase().startsWith("ru") ? "ru" : "en");

export function App() {
  const [boot, setBoot] = useState<Boot>({ status: "loading" });

  useEffect(() => followTheme(() => paintTelegram(surfaceColor())), []);

  /** `fromCache`: draw the viewer last seen on this device at once and let
   * `/me` replace it. A browser is signed in when its cookie answers `/me`. */
  const load = useCallback(async (fromCache: boolean) => {
    const telegram = inTelegram();
    const cached = fromCache ? cachedMe() : null;
    if (cached) {
      if (!telegram) setWebSession(true);
      setBoot({ status: "ok", me: cached });
    }
    try {
      const me = await userApi.fetchMe(telegram ? initData() : WEB_SESSION);
      if (!telegram) setWebSession(true);
      rememberMe(me);
      setBoot({ status: "ok", me });
    } catch (err) {
      const refused = err instanceof ApiError && (err.status === 401 || err.status === 403);
      if (refused) forgetHome();
      if (!telegram && (refused || !cached)) {
        setWebSession(false);
        setBoot({ status: "login" });
        return;
      }
      // Offline with a page to show: keep showing it.
      if (cached && !refused) return;
      setBoot({ status: "error", message: String(err) });
    }
  }, []);

  useEffect(() => {
    void load(true);
  }, [load]);

  if (boot.status === "loading") return <Splash />;
  if (boot.status === "login") {
    return (
      <>
        <Suspense fallback={<Splash />}>
          <SignIn locale={deviceLocale()} onSignedIn={() => void load(false)} />
        </Suspense>
        <Toaster />
      </>
    );
  }
  if (boot.status === "error") {
    const tr = translator(deviceLocale());
    return (
      <div className="boot-error">
        <p className="t-title">{tr("bootErrorTitle")}</p>
        <p className="t-body">{tr("bootErrorText")}</p>
        <Button onClick={() => void load(false)}>{tr("retry")}</Button>
      </div>
    );
  }
  return (
    <Shell
      me={boot.me}
      setMe={(me) => {
        rememberMe(me);
        setBoot({ status: "ok", me });
      }}
      reloadMe={() => load(false)}
      signedOut={() => {
        forgetHome();
        setWebSession(false);
        setBoot({ status: "login" });
      }}
    />
  );
}

function Splash() {
  return (
    <div className="splash">
      <img src={`${import.meta.env.BASE_URL}logo.svg`} alt="Unlocked" className="splash-logo" />
    </div>
  );
}

type Stacked = { id: number; layer: Layer };

let layerSeq = 0;

function placeLayers(): Stacked[] {
  const launch = launchContext();
  const out: Layer[] = [];
  // A link's tab that is a page here rather than a tab (`t=people`, `t=settings`).
  const asked = new URLSearchParams(window.location.search).get("t");
  if (asked === "people") out.push({ kind: "search" });
  if (asked === "settings") out.push({ kind: "settings", pane: "root" });
  if (asked === "pass") out.push({ kind: "pass" });
  if (launch.personId != null) out.push({ kind: "person", personId: launch.personId });
  if (launch.game && launch.achievement) {
    const who = launch.game.person && "person_id" in launch.game.person ? launch.game.person : null;
    out.push({
      kind: "achievementRef",
      platform: launch.game.platform,
      titleId: launch.game.title_id,
      achievementId: launch.achievement,
      person: who?.person_id != null ? { id: who.person_id, name: who.name } : null,
    });
  } else if (launch.game) out.push({ kind: "game", ref: launch.game });
  if (launch.news) {
    out.push({
      kind: "news",
      appid: launch.news.appid,
      gid: launch.news.gid,
      item: null,
      game: launch.news.game
        ? { platform: launch.news.game.platform, title_id: launch.news.game.title_id, name: null, icon_url: null }
        : null,
    });
  }
  return out.map((layer) => ({ id: ++layerSeq, layer }));
}

function Shell({
  me,
  setMe,
  reloadMe,
  signedOut,
}: {
  me: MeResponse;
  setMe: (me: MeResponse) => void;
  reloadMe: () => Promise<void>;
  signedOut: () => void;
}) {
  useEffect(() => prefetchLayers(), []);
  // Once Home is drawn, the Feed and the Ranking load behind it, so a tap on
  // their tab finds them ready.
  const [warm, setWarm] = useState(false);
  useEffect(() => {
    const id = window.setTimeout(() => setWarm(true), 1200);
    return () => window.clearTimeout(id);
  }, []);
  const locale = localeOf(me);
  const tr = useMemo(() => translator(locale), [locale]);
  const launch = useMemo(() => launchContext(), []);
  const [tab, setTabState] = useState<Tab>(() => {
    const back = launch.screen as Tab | undefined;
    if (back && TABS.includes(back)) return back;
    return TABS.includes(launch.tab as Tab) ? (launch.tab as Tab) : "home";
  });
  const [layers, setLayers] = useState<Stacked[]>(placeLayers);
  const [refreshKey, setRefreshKey] = useState(0);
  const [firstRunDone, setFirstRunDone] = useState(false);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  useEffect(() => {
    const top = [...layers].reverse();
    const person = top.find((s) => s.layer.kind === "person")?.layer;
    const game = top.find((s) => s.layer.kind === "game")?.layer;
    savePlace({
      screen: tab,
      personId: person?.kind === "person" ? person.personId : null,
      game: game?.kind === "game" ? game.ref : null,
    });
  }, [tab, layers]);

  // A post's button from before person ids (#156) names a Telegram id.
  const legacy = useRef(launch.legacyTgId);
  useEffect(() => {
    const tgId = legacy.current;
    if (tgId == null || launch.personId != null) return;
    legacy.current = null;
    peopleApi
      .profileByTg(initData(), tgId)
      .then((card) => setLayers((s) => [...s, { id: ++layerSeq, layer: { kind: "person", personId: card.id } }]))
      .catch(() => undefined);
  }, [launch.personId]);

  const open = useCallback((layer: Layer) => {
    setLayers((s) => [...s, { id: ++layerSeq, layer }]);
  }, []);
  const back = useCallback(() => setLayers((s) => s.slice(0, -1)), []);
  const closeAll = useCallback(() => setLayers([]), []);
  const setTab = useCallback((next: Tab) => {
    setLayers([]);
    setTabState(next);
  }, []);

  // A follow, an unfollow or a block changes whose activity the tabs show:
  // one reload for a burst of changes.
  useEffect(() => {
    let timer = 0;
    const changed = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => setRefreshKey((n) => n + 1), 700);
    };
    window.addEventListener(FOLLOWS_CHANGED, changed);
    return () => {
      window.removeEventListener(FOLLOWS_CHANGED, changed);
      window.clearTimeout(timer);
    };
  }, []);

  // Back from Microsoft's sign-in or another tab: an account linked meanwhile
  // shows without a reload. At most once in half a minute.
  useEffect(() => {
    let last = Date.now();
    const back = () => {
      if (document.visibilityState !== "visible" || Date.now() - last < 30_000) return;
      last = Date.now();
      void reloadMe();
    };
    document.addEventListener("visibilitychange", back);
    return () => document.removeEventListener("visibilitychange", back);
  }, [reloadMe]);

  // Another tab than Home steps back to Home before the app closes.
  useBackHandler(tab !== "home", () => setTabState("home"), `tab:${tab}`);

  const app: AppValue = useMemo(
    () => ({
      data: initData(),
      me,
      locale,
      tr: tr as (key: TranslationKey) => string,
      picture: me.picture ? { on: me.picture.on, scale: me.picture.scale, lowRes: me.picture.low_res } : DEFAULT_PICTURE,
      setMe,
      reloadMe,
      tab,
      setTab,
      open,
      back,
      closeAll,
      toast: showToast,
      signOut: signedOut,
    }),
    [me, locale, tr, setMe, reloadMe, tab, setTab, open, back, closeAll, signedOut],
  );

  const needsFirstRun = !firstRunDone && (me.handle?.confirmed === false || Boolean(me.email_prompt));
  if (needsFirstRun) {
    return (
      <AppContext.Provider value={app}>
        <FirstRun onDone={() => setFirstRunDone(true)} />
        <Toaster />
      </AppContext.Provider>
    );
  }

  const top = layers[layers.length - 1]?.layer;
  const barShown = !top || barShownOver(top);

  return (
    <AppContext.Provider value={app}>
      <main className="tabs">
        <TabPane active={tab === "home"}>
          <Home refreshKey={refreshKey} />
        </TabPane>
        <TabPane active={tab === "feed"} lazy warm={warm}>
          <Feed refreshKey={refreshKey} />
        </TabPane>
        <TabPane active={tab === "summary"} lazy warm={warm}>
          <Ranking refreshKey={refreshKey} />
        </TabPane>
      </main>
      {layers.map((s, i) => (
        <LayerView
          key={s.id}
          layer={s.layer}
          covered={i < layers.length - 1}
          onClose={() => setLayers((all) => all.filter((x) => x.id !== s.id))}
        />
      ))}
      <BottomBar
        tabs={[
          { id: "home", icon: "home", label: tr("tabHome") },
          { id: "feed", icon: "feed", label: tr("feed") },
          { id: "summary", icon: "rank", label: tr("ranking") },
        ]}
        current={layers.length ? null : tab}
        onTab={(next) => {
          if (next === tab && layers.length === 0) {
            document.querySelector(".tab-active")?.scrollTo({ top: 0, behavior: "smooth" });
            return;
          }
          setTab(next);
        }}
        onSearch={() => open({ kind: "search" })}
        searchLabel={tr("searchTitle")}
        hidden={!barShown}
      />
      <ImageViewer />
      <Toaster />
    </AppContext.Provider>
  );
}

/** A tab keeps its place when left: it stays mounted, only hidden. A `lazy`
 * one is first built when first opened. */
function TabPane({
  active,
  lazy = false,
  warm = false,
  children,
}: {
  active: boolean;
  lazy?: boolean;
  /** Mount it in the background, before its first visit. */
  warm?: boolean;
  children: React.ReactNode;
}) {
  const [seen, setSeen] = useState(active || !lazy);
  useEffect(() => {
    if (active || warm) setSeen(true);
  }, [active, warm]);
  return (
    <div className={`tab${active ? " tab-active" : ""}`} data-scroll={active ? true : undefined} hidden={!active}>
      <Suspense fallback={null}>{seen && children}</Suspense>
    </div>
  );
}
