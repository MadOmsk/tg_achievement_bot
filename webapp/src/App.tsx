import { useCallback, useEffect, useState } from "react";
import {
  connectPsn,
  connectSteam,
  connectXbox,
  disconnectPsn,
  disconnectSteam,
  disconnectXbox,
  fetchMe,
  patchChat,
  patchSettings,
  syncXbox,
  type MeResponse,
} from "./api";
import { Club } from "./screens/club";
import { Admin } from "./screens/admin";
import { GameOpenProvider } from "./components/game";
import { t, type Locale } from "./i18n";
import { ConnectForm, Settings, type PlatNotes } from "./screens/me";
import { Icon, PageSkel, usePullToRefresh } from "./components/shared/lib";
import {
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

function launchContext(): {
  chatId: number | null;
  personId: number | null;
  tab: LaunchTab;
} {
  const q = new URLSearchParams(window.location.search);
  const start = window.Telegram?.WebApp?.initDataUnsafe?.start_param ?? "";
  let chatId = q.get("c");
  let personId = q.get("u");
  let tab = q.get("t");
  const parsed = /^c(-?\d+)(?:u(\d+))?(?:t([a-z]+))?$/.exec(start);
  if (parsed) {
    chatId ??= parsed[1];
    personId ??= parsed[2] ?? null;
    tab ??= parsed[3] ?? null;
  }
  return {
    chatId: chatId ? Number(chatId) : null,
    personId: personId ? Number(personId) : null,
    tab: asLaunchTab(tab),
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
  const [adminScreen, setAdminScreen] = useState<AdminScreen>({ name: "users" });
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

  useEffect(() => {
    window.scrollTo(0, 0);
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
  }, [screen.name, personId]);

  const { indicator: pullIndicator } = usePullToRefresh(async () => {
    await reload();
    setRefreshKey((n) => n + 1);
  });

  if (state.status === "loading") {
    return <PageSkel />;
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

      {isClubPane && (
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
      )}

      {isSettings && (
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
        />
      )}

      {isAdmin && (
        <Admin
          locale={locale}
          data={data}
          initial={adminScreen}
          onFlash={setFlash}
          onBack={() => setScreen(SCREENS.settings)}
        />
      )}

      {isConnectSteam && (
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
      )}

      {isConnectPsn && (
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
