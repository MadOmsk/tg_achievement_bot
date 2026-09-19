import { useCallback, useEffect, useState } from "react";
import {
  connectPsn,
  connectSteam,
  connectXbox,
  disconnectPsn,
  disconnectSteam,
  disconnectXbox,
  fetchMe,
  isPreview,
  patchChat,
  patchSettings,
  syncXbox,
  type MeResponse,
} from "./api";
import { Club } from "./Club";
import { Admin } from "./Admin";
import { t, type Locale } from "./i18n";
import { ConnectForm, Settings, type PlatNotes } from "./Me";
import { previewMe } from "./preview";
import { Icon, PageSkel, usePullToRefresh } from "./ui";

const SCREENS = {
  home: { name: "home" },
  feed: { name: "feed" },
  summary: { name: "summary" },
  settings: { name: "settings" },
  admin: { name: "admin" },
  "connect-steam": { name: "connect-steam" },
  "connect-psn": { name: "connect-psn" },
} as const;

type Screen = (typeof SCREENS)[keyof typeof SCREENS];
type DockTab = "feed" | "summary" | "settings";
type LaunchTab = "home" | "feed" | "summary";

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
    tab: tab === "summary" ? "summary" : tab === "feed" ? "feed" : "home",
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
  // Bumped by pull-to-refresh so Club refetches without remounting the tab.
  const [refreshKey, setRefreshKey] = useState(0);

  const reload = useCallback(async () => {
    if (isPreview()) {
      setState({ status: "ok", me: previewMe });
      setChatId((current) => current ?? previewMe.chats[0]?.chat_id ?? null);
      return;
    }
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
  const data = isPreview() ? "preview" : initData();

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

  const showChrome = !personOpen && screen.name === "home";
  const clubPane =
    screen.name === "feed"
      ? "feed"
      : screen.name === "summary"
        ? "summary"
        : "home";
  const goHome = () => {
    if (screen.name === "home" && !personOpen) {
      window.scrollTo(0, 0);
      return;
    }
    setPersonId(null);
    setScreen(SCREENS.home);
  };

  const goTab = (tab: DockTab) => {
    const already =
      tab === "settings"
        ? screen.name === "settings" || screen.name === "admin"
        : screen.name === tab && !personOpen;
    if (already) {
      window.scrollTo(0, 0);
      return;
    }
    setPersonId(null);
    setScreen(SCREENS[tab]);
  };

  return (
    <div
      className={[
        busy ? "busy" : "",
        showChrome && screen.name === "home" ? "is-home" : "",
        personOpen ? "is-person" : "",
      ]
        .filter(Boolean)
        .join(" ") || undefined}
    >
      {pullIndicator}
      {busy ? <div className="busy-bar" /> : null}
      {flash ? <p className="flash">{flash}</p> : null}

      {screen.name === "home" || screen.name === "feed" || screen.name === "summary" ? (
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
      ) : null}

      {screen.name === "settings" ? (
        <Settings
          me={me}
          locale={locale}
          onAdmin={me.is_admin ? () => setScreen(SCREENS.admin) : undefined}
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
      ) : null}

      {screen.name === "admin" ? (
        <Admin
          locale={locale}
          data={data}
          onFlash={setFlash}
          onBack={() => setScreen(SCREENS.settings)}
        />
      ) : null}

      {screen.name === "connect-steam" ? (
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
      ) : null}

      {screen.name === "connect-psn" ? (
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
      ) : null}

      {screen.name === "connect-steam" || screen.name === "connect-psn" ? null : (
        <nav className="dock">
          <span
            className="dock-pill"
            style={{
              transform: `translateX(${
                (screen.name === "settings" || screen.name === "admin"
                  ? 3
                  : screen.name === "summary"
                    ? 2
                    : screen.name === "feed"
                      ? 1
                      : 0) * 100
              }%)`,
            }}
            aria-hidden
          />
          <button
            type="button"
            className={screen.name === "home" && !personOpen ? "is-on" : undefined}
            onClick={goHome}
            aria-label={t(locale, "home")}
          >
            <Icon name="home" filled={screen.name === "home" && !personOpen} />
          </button>
          <button
            type="button"
            className={screen.name === "feed" && !personOpen ? "is-on" : undefined}
            onClick={() => goTab("feed")}
            aria-label={t(locale, "feed")}
          >
            <Icon name="feed" filled={screen.name === "feed" && !personOpen} />
          </button>
          <button
            type="button"
            className={screen.name === "summary" && !personOpen ? "is-on" : undefined}
            onClick={() => goTab("summary")}
            aria-label={t(locale, "stats")}
          >
            <Icon name="stats" filled={screen.name === "summary" && !personOpen} />
          </button>
          <button
            type="button"
            className={screen.name === "settings" || screen.name === "admin" ? "is-on" : undefined}
            onClick={() => goTab("settings")}
            aria-label={t(locale, "settings")}
          >
            <Icon name="gear" filled={screen.name === "settings" || screen.name === "admin"} />
          </button>
        </nav>
      )}
    </div>
  );
}
