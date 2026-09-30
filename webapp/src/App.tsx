import { lazy, Suspense, useCallback, useEffect, useLayoutEffect, useState } from "react";
import {
  connectPsn,
  connectSteam,
  connectXbox,
  deleteAccount,
  disconnectPsn,
  disconnectSteam,
  disconnectXbox,
  fetchMe,
  patchChat,
  patchSettings,
  syncXbox,
  type GameRef,
  type MeResponse,
} from "./api";
import { Club } from "./screens/club";
// Straight from its own file, not the ./components/game barrel — that barrel
// also re-exports TitleSheet (and its game.css), which GameOpenProvider now
// loads lazily; importing it through the barrel would pull TitleSheet back
// into this eager chunk regardless.
import { GameOpenProvider } from "./components/game/game-open-provider/GameOpenProvider";
import "./components/game/game.css";
import { t, type Locale } from "./i18n";
import type { PlatNotes } from "./screens/me";
import { AppSkel, Icon, usePullToRefresh } from "./components/shared/lib";

// Off Home's own critical path — loaded on first visit to each, not upfront.
const Admin = lazy(() => import("./screens/admin").then((m) => ({ default: m.Admin })));
const Settings = lazy(() => import("./screens/me").then((m) => ({ default: m.Settings })));
const ConnectForm = lazy(() => import("./screens/me").then((m) => ({ default: m.ConnectForm })));
import {
  ADMIN_SCREENS,
  asLaunchTab,
  SCREEN_NAMES,
  SCREENS,
  type AdminScreen,
  type DockTab,
  type LaunchTab,
  type Screen,
} from "./components/shared/constants";

type LoadState =
  | { status: "loading" }
  | { status: "need-telegram" }
  | { status: "error"; message: string }
  | { status: "ok"; me: MeResponse };

function initData(): string {
  return window.Telegram?.WebApp?.initData ?? "";
}

function localeOf(me: MeResponse): Locale {
  return me.settings.locale === "en" ? "en" : "ru";
}

/** The reverse of `bot/services/mini_app.py::_encode_game` — base64url,
 * padding restored, back to "platform:titleId". `null` on anything that
 * doesn't actually decode, rather than a page that opens on garbage. */
function decodeGameToken(token: string): string | null {
  try {
    const padded = token + "=".repeat((4 - (token.length % 4)) % 4);
    const std = padded.replace(/-/g, "+").replace(/_/g, "/");
    return atob(std);
  } catch {
    return null;
  }
}

function launchContext(): {
  chatId: number | null;
  personId: number | null;
  tab: LaunchTab;
  game: GameRef | null;
} {
  const q = new URLSearchParams(window.location.search);
  const start = window.Telegram?.WebApp?.initDataUnsafe?.start_param ?? "";
  let chatId = q.get("c");
  let personId = q.get("u");
  let tab = q.get("t");
  // From the query string (a DM's own https URL): plain "platform:titleId",
  // already percent-decoded by URLSearchParams.
  let game = q.get("g");
  // From a group's startapp value: base64url of the same string — Telegram's
  // start_parameter only allows [A-Za-z0-9_-], which a literal ':' falls
  // outside of (found live, 2026-09-30 review of #145: every group deep
  // link to a game was silently broken). See bot/services/mini_app.py's
  // `_encode_game`, which this must stay in sync with.
  const parsed = /^c(-?\d+)(?:u(\d+))?(?:t([a-z]+))?(?:g([A-Za-z0-9_-]+))?$/.exec(start);
  if (parsed) {
    chatId ??= parsed[1];
    personId ??= parsed[2] ?? null;
    tab ??= parsed[3] ?? null;
    game ??= parsed[4] ? decodeGameToken(parsed[4]) : null;
  }
  // Split on the first ":" only — a title_id is never expected to hold one,
  // but nothing stops it from someday.
  const colon = game?.indexOf(":") ?? -1;
  const personNum = personId ? Number(personId) : null;
  return {
    chatId: chatId ? Number(chatId) : null,
    personId: personNum,
    tab: asLaunchTab(tab),
    // Whose progress the game page opens on: the achievement's own owner,
    // not necessarily whoever tapped the link — the name is filled in once
    // the game page's own fetch resolves who that is (see TitleSheet).
    game:
      game && colon > 0 && colon < game.length - 1
        ? {
            platform: game.slice(0, colon),
            title_id: game.slice(colon + 1),
            person: personNum ? { tg_id: personNum, name: "" } : null,
          }
        : null,
  };
}

export function App() {
  const launch = launchContext();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [screen, setScreen] = useState<Screen>(SCREENS[launch.tab]);
  const [chatId, setChatId] = useState<number | null>(launch.chatId);
  const [personId, setPersonId] = useState<number | null>(launch.personId);
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const [platNotes, setPlatNotes] = useState<PlatNotes>({});
  const [personOpen, setPersonOpen] = useState(false);
  // Which admin screen Settings' admin list opened.
  const [adminScreen, setAdminScreen] = useState<AdminScreen>({ name: ADMIN_SCREENS.USERS });
  // Bumped by pull-to-refresh so Club refetches without remounting the tab.
  const [refreshKey, setRefreshKey] = useState(0);

  const reload = useCallback(async () => {
    const data = initData();
    if (!data) {
      setState({ status: "need-telegram" });
      return;
    }
    const me = await fetchMe(data);
    setState({ status: "ok", me });
    setChatId((current) => {
      if (current && me.chats.some((c) => c.chat_id === current)) return current;
      return me.chats[0]?.chat_id ?? null;
    });
  }, []);

  useEffect(() => {
    if (!flash) return;
    const id = window.setTimeout(() => setFlash(null), 4200);
    return () => window.clearTimeout(id);
  }, [flash]);

  useEffect(() => {
    window.Telegram?.WebApp?.setHeaderColor?.("#0a0c12");
    window.Telegram?.WebApp?.setBackgroundColor?.("#0a0c12");
    let cancelled = false;
    void reload().catch((err: unknown) => {
      if (!cancelled) setState({ status: "error", message: String(err) });
    });
    return () => {
      cancelled = true;
    };
  }, [reload]);

  useLayoutEffect(() => {
    window.scrollTo(0, 0);
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
  }, [screen.name, personId]);

  const { indicator: pullIndicator } = usePullToRefresh(async () => {
    await reload();
    setRefreshKey((n) => n + 1);
  });

  if (state.status === "loading") {
    return <AppSkel />;
  }
  if (state.status === "need-telegram") {
    return <p className="error">{t("ru", "needTelegram")}</p>;
  }
  if (state.status === "error") {
    return <p className="error">{state.message}</p>;
  }

  const { me } = state;
  const locale = localeOf(me);
  const data = initData();

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setFlash(null);
    try {
      await fn();
      await reload();
    } catch (err) {
      setFlash(`${t(locale, "error")}: ${String(err)}`);
    } finally {
      setBusy(false);
    }
  };

  const runPlat = async (plat: keyof PlatNotes, fn: () => Promise<string | void>) => {
    setBusy(true);
    setPlatNotes((current) => {
      const next = { ...current };
      delete next[plat];
      return next;
    });
    try {
      const info = await fn();
      await reload();
      if (info) setPlatNotes((current) => ({ ...current, [plat]: { kind: "info", text: info } }));
    } catch (err) {
      setPlatNotes((current) => ({ ...current, [plat]: { kind: "error", text: String(err) } }));
    } finally {
      setBusy(false);
    }
  };

  // Every screen.name comparison the render below needs, computed once —
  // never a bare string literal re-typed at each call site.
  const isHome = screen.name === SCREEN_NAMES.HOME;
  const isFeed = screen.name === SCREEN_NAMES.FEED;
  const isSummary = screen.name === SCREEN_NAMES.SUMMARY;
  const isSettings = screen.name === SCREEN_NAMES.SETTINGS;
  const isAdmin = screen.name === SCREEN_NAMES.ADMIN;
  const isConnectSteam = screen.name === SCREEN_NAMES.CONNECT_STEAM;
  const isConnectPsn = screen.name === SCREEN_NAMES.CONNECT_PSN;
  const isSettingsOrAdmin = isSettings || isAdmin;
  const isClubPane = isHome || isFeed || isSummary;
  const isConnectScreen = isConnectSteam || isConnectPsn;

  const showChrome = !personOpen && isHome;
  const clubPane = isFeed
    ? SCREEN_NAMES.FEED
    : isSummary
      ? SCREEN_NAMES.SUMMARY
      : SCREEN_NAMES.HOME;
  const goHome = () => {
    if (isHome && !personOpen) {
      window.scrollTo(0, 0);
      return;
    }
    setPersonId(null);
    setScreen(SCREENS.home);
  };

  const goTab = (tab: DockTab) => {
    const already =
      tab === SCREEN_NAMES.SETTINGS ? isSettingsOrAdmin : screen.name === tab && !personOpen;
    if (already) {
      window.scrollTo(0, 0);
      return;
    }
    setPersonId(null);
    setScreen(SCREENS[tab]);
  };

  return (
    <GameOpenProvider
      data={data}
      locale={locale}
      showSecrets={me.settings.show_secrets}
      meId={me.tg_id}
      initialGame={launch.game}
    >
    <div
      className={[
        busy ? "busy" : "",
        showChrome && isHome ? "is-home" : "",
        personOpen ? "is-person" : "",
      ]
        .filter(Boolean)
        .join(" ") || undefined}
    >
      {pullIndicator}
      {busy && <div className="busy-bar" />}
      {flash && <p className="flash">{flash}</p>}

      {/* Kept mounted (just hidden) off the club pane, not unmounted:
          leaving it and coming back — e.g. through Settings — used to reset
          every pane's month and refetch from scratch. */}
      <div style={isClubPane ? undefined : { display: "none" }}>
        <Club
          me={me}
          locale={locale}
          chatId={chatId}
          openPersonId={personId}
          data={data}
          pane={clubPane}
          refreshKey={refreshKey}
          onChat={setChatId}
          onFlash={setFlash}
          onOpenPerson={(id) => {
            if (id === me.tg_id) {
              setPersonId(null);
              setScreen(SCREENS.home);
              return;
            }
            setPersonId(id);
          }}
          onClosePerson={() => setPersonId(null)}
          onPersonVisible={setPersonOpen}
          onSettings={() => setScreen(SCREENS.settings)}
        />
      </div>

      {isSettings && (
        <Suspense fallback={null}>
        <Settings
          me={me}
          locale={locale}
          data={data}
          onFlash={setFlash}
          onAdmin={
            me.is_admin
              ? (next) => {
                  setAdminScreen(next);
                  setScreen(SCREENS.admin);
                }
              : undefined
          }
          onPatch={(body) =>
            void run(async () => {
              await patchSettings(data, body);
            })
          }
          onChatPatch={(chatId, body) =>
            void run(async () => {
              await patchChat(data, chatId, body);
            })
          }
          onConnectSteam={() => setScreen(SCREENS["connect-steam"])}
          onConnectPsn={() => setScreen(SCREENS["connect-psn"])}
          notes={platNotes}
          onConnectXbox={() =>
            void runPlat("xbox", async () => {
              const { authorize_url } = await connectXbox(data);
              window.Telegram?.WebApp?.openLink(authorize_url);
              return t(locale, "openMicrosoft");
            })
          }
          onDisconnectXbox={() =>
            void runPlat("xbox", async () => {
              if (!window.confirm(t(locale, "confirmDisconnect"))) return;
              await disconnectXbox(data);
            })
          }
          onDisconnectSteam={() =>
            void runPlat("steam", async () => {
              if (!window.confirm(t(locale, "confirmDisconnect"))) return;
              await disconnectSteam(data);
            })
          }
          onDisconnectPsn={() =>
            void runPlat("psn", async () => {
              if (!window.confirm(t(locale, "confirmDisconnect"))) return;
              await disconnectPsn(data);
            })
          }
          onSync={() =>
            void runPlat("xbox", async () => {
              await syncXbox(data);
            })
          }
          onDeleteAccount={async () => {
            await deleteAccount(data);
          }}
        />
        </Suspense>
      )}

      {isAdmin && (
        <Suspense fallback={null}>
        <Admin
          locale={locale}
          data={data}
          initial={adminScreen}
          onFlash={setFlash}
          onBack={() => setScreen(SCREENS.settings)}
        />
        </Suspense>
      )}

      {isConnectSteam && (
        <Suspense fallback={null}>
        <ConnectForm
          locale={locale}
          platform="steam"
          label={t(locale, "steamPrompt")}
          onBack={() => setScreen(SCREENS.settings)}
          onSubmit={async (identity) => {
            await connectSteam(data, identity);
            await reload();
            setPlatNotes((current) => ({
              ...current,
              steam: { kind: "info", text: t(locale, "backfillStarted") },
            }));
            setScreen(SCREENS.settings);
          }}
        />
        </Suspense>
      )}

      {isConnectPsn && (
        <Suspense fallback={null}>
        <ConnectForm
          locale={locale}
          platform="psn"
          label={t(locale, "psnPrompt")}
          onBack={() => setScreen(SCREENS.settings)}
          onSubmit={async (identity) => {
            await connectPsn(data, identity);
            await reload();
            setPlatNotes((current) => ({
              ...current,
              psn: { kind: "info", text: t(locale, "backfillStarted") },
            }));
            setScreen(SCREENS.settings);
          }}
        />
        </Suspense>
      )}

      {!isConnectScreen && (
        <nav className="dock">
          <span
            className="dock-pill"
            style={{
              transform: `translateX(${
                (isSettingsOrAdmin ? 3 : isSummary ? 2 : isFeed ? 1 : 0) * 100
              }%)`,
            }}
            aria-hidden
          />
          <button
            type="button"
            className={isHome && !personOpen ? "is-on" : undefined}
            onClick={goHome}
            aria-label={t(locale, "home")}
          >
            <Icon name="home" filled={isHome && !personOpen} />
          </button>
          <button
            type="button"
            className={isFeed && !personOpen ? "is-on" : undefined}
            onClick={() => goTab(SCREEN_NAMES.FEED)}
            aria-label={t(locale, "feed")}
          >
            <Icon name="feed" filled={isFeed && !personOpen} />
          </button>
          <button
            type="button"
            className={isSummary && !personOpen ? "is-on" : undefined}
            onClick={() => goTab(SCREEN_NAMES.SUMMARY)}
            aria-label={t(locale, "stats")}
          >
            <Icon name="stats" filled={isSummary && !personOpen} />
          </button>
          <button
            type="button"
            className={isSettingsOrAdmin ? "is-on" : undefined}
            onClick={() => goTab(SCREEN_NAMES.SETTINGS)}
            aria-label={t(locale, "settings")}
          >
            <Icon name="gear" filled={isSettingsOrAdmin} />
          </button>
        </nav>
      )}
    </div>
    </GameOpenProvider>
  );
}
