import { lazy, Suspense, useCallback, useEffect, useLayoutEffect, useState } from "react";
import {
  connectPsn,
  connectSteam,
  confirmHandle,
  connectXbox,
  deleteAccount,
  disconnectPsn,
  disconnectSteam,
  disconnectXbox,
  fetchMe,
  logout,
  WEB_SESSION,
  patchChat,
  patchSettings,
  putHandle,
  putAvatar,
  deleteAvatar,
  setAccountPublishes,
  syncXbox,
  type GameRef,
  type MeResponse,
} from "./api";
import { Club } from "./screens/club";
// Straight from its own file, not the ./components/game barrel — that barrel
// also re-exports TitleSheet (and its game.css), which GameOpenProvider now
// loads lazily; importing it through the barrel would pull TitleSheet back
// into this eager chunk regardless.
import {
  GameOpenProvider,
  preloadTitleSheet,
} from "./components/game/game-open-provider/GameOpenProvider";
import "./components/game/game.css";
import { t, type Locale } from "./i18n";
import { ConnectForm, NicknameForm, Settings, type PlatNotes } from "./screens/me";
import { People } from "./screens/people";
import { FOLLOWS_CHANGED } from "./components/people/follow-button/FollowButton";
import { Login } from "./screens/login";
import { AddEmailScreen } from "./components/me/logins/AddEmailScreen";
import { peopleApi } from "./api/people/peopleApi";
import { AppSkel, GameSkel, Icon, ImageViewerHost, tick, InstallPrompt, SettingsSkel, useBackHandler, Toaster, showToast, setOwnAvatarCustom, forgetAvatar, usePullToRefresh } from "./components/shared/lib";

// Off Home's own critical path — loaded on first visit to each, not upfront.
// Settings and the connect forms are a few kilobytes and sit behind the dock like
// every other tab, so they ship with the app and open at once. Only the admin
// screens, which most people never see, load on their own — fetched while the
// app is idle once it is up, so even they open without a wait.
const loadAdmin = () => import("./screens/admin");
const Admin = lazy(() => loadAdmin().then((m) => ({ default: m.Admin })));
const PRELOAD_AFTER_MS = 1500;
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
  | { status: "login" }
  | { status: "error"; message: string }
  | { status: "ok"; me: MeResponse };

// Open in a plain browser, signed in through Telegram Login (#157): the session
// cookie signs requests, and this stands in for Init Data.
let webSession = false;

function initData(): string {
  return window.Telegram?.WebApp?.initData || (webSession ? WEB_SESSION : "");
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

// Where the app was, kept for this tab's session (owner, 2026-10-06): a reload
// — a new build, a pull of the browser — comes back to the same screen, the
// same person and the same game instead of Home. A link that names where to
// go always wins.
const PLACE_KEY = "app-place";
type Place = { screen: string; personId: number | null; game: GameRef | null };

function savedPlace(): Place | null {
  try {
    const raw = sessionStorage.getItem(PLACE_KEY);
    return raw ? (JSON.parse(raw) as Place) : null;
  } catch {
    return null;
  }
}

function savePlace(place: Place): void {
  try {
    sessionStorage.setItem(PLACE_KEY, JSON.stringify(place));
  } catch {
    // No storage: a reload opens Home.
  }
}

function launchContext(): {
  chatId: number | null;
  personId: number | null;
  /** A post's button from before person ids (#156) names a Telegram id. */
  legacyTgId: number | null;
  tab: LaunchTab;
  game: GameRef | null;
  /** The screen a reload comes back to. */
  screen?: string;
} {
  const q = new URLSearchParams(window.location.search);
  const start = window.Telegram?.WebApp?.initDataUnsafe?.start_param ?? "";
  let chatId = q.get("c");
  let personId = q.get("p");
  let legacyTg = q.get("u");
  let tab = q.get("t");
  // From the query string (a DM's own https URL): plain "platform:titleId",
  // already percent-decoded by URLSearchParams.
  let game = q.get("g");
  // From a group's startapp value: base64url of the same string — Telegram's
  // start_parameter only allows [A-Za-z0-9_-], which a literal ':' falls
  // outside of (found live, 2026-09-30 review of #145: every group deep
  // link to a game was silently broken). See bot/services/mini_app.py's
  // `_encode_game`, which this must stay in sync with.
  const parsed = /^c(-?\d+)(?:([pu])(\d+))?(?:t([a-z]+))?(?:g([A-Za-z0-9_-]+))?$/.exec(start);
  const linked = Boolean(start) || ["c", "p", "u", "t", "g"].some((key) => q.has(key));
  const place = linked ? null : savedPlace();
  if (parsed) {
    chatId ??= parsed[1];
    if (parsed[2] === "p") personId ??= parsed[3] ?? null;
    else legacyTg ??= parsed[3] ?? null;
    tab ??= parsed[4] ?? null;
    game ??= parsed[5] ? decodeGameToken(parsed[5]) : null;
  }
  // Split on the first ":" only — a title_id is never expected to hold one,
  // but nothing stops it from someday.
  const colon = game?.indexOf(":") ?? -1;
  const personNum = personId ? Number(personId) : null;
  if (place) {
    return {
      chatId: null,
      personId: place.personId,
      legacyTgId: null,
      tab: SCREEN_NAMES.HOME,
      game: place.game,
      screen: place.screen,
    };
  }
  return {
    chatId: chatId ? Number(chatId) : null,
    personId: personNum,
    legacyTgId: legacyTg ? Number(legacyTg) : null,
    tab: asLaunchTab(tab),
    // Whose progress the game page opens on: the achievement's own owner,
    // not necessarily whoever tapped the link — the name is filled in once
    // the game page's own fetch resolves who that is (see TitleSheet).
    game:
      game && colon > 0 && colon < game.length - 1
        ? {
            platform: game.slice(0, colon),
            title_id: game.slice(colon + 1),
            // A post's button from before person ids names a Telegram id: the
            // game page asks by it and learns the person from the answer.
            person: personNum
              ? { person_id: personNum, name: "" }
              : legacyTg
                ? { tg_id: Number(legacyTg), name: "" }
                : null,
          }
        : null,
  };
}

export function App() {
  const launch = launchContext();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [screen, setScreen] = useState<Screen>(() => {
    const back = launch.screen;
    // Connecting an account is a flow of its own: a reload starts it over at Home.
    return back && back in SCREENS && !back.startsWith("connect")
      ? SCREENS[back as keyof typeof SCREENS]
      : SCREENS[launch.tab];
  });
  const [chatId, setChatId] = useState<number | null>(launch.chatId);
  const [personId, setPersonId] = useState<number | null>(launch.personId);
  const [busy, setBusy] = useState(false);
  // Notices go to the global toaster, which floats over the page (#157).
  const setFlash = useCallback((message: string | null) => {
    if (!message) return;
    const failed = message.startsWith(t("ru", "error")) || message.startsWith(t("en", "error"));
    showToast(message, failed ? "error" : "info");
  }, []);
  const [platNotes, setPlatNotes] = useState<PlatNotes>({});
  const [personOpen, setPersonOpen] = useState(false);
  // The Find button on Home lands on People with the search focused.
  const [focusSearch, setFocusSearch] = useState(false);
  // Which admin screen Settings' admin list opened.
  const [adminScreen, setAdminScreen] = useState<AdminScreen>({ name: ADMIN_SCREENS.USERS });
  // Opened straight on a game (a notification's button), the home page is not
  // loaded behind it: it would only compete with the game for the network.
  // It is built once the game page is left.
  const [homeWanted, setHomeWanted] = useState(launch.game === null);
  const [openGameRef, setOpenGameRef] = useState<GameRef | null>(launch.game);
  const onGameChange = useCallback((game: GameRef | null) => {
    if (!game) setHomeWanted(true);
    setOpenGameRef(game);
  }, []);
  useEffect(() => {
    savePlace({ screen: screen.name, personId, game: openGameRef });
  }, [screen.name, personId, openGameRef]);
  // Bumped by pull-to-refresh so Club refetches without remounting the tab.
  const [refreshKey, setRefreshKey] = useState(0);
  // After a follow, unfollow or block, the screens built on who is followed
  // reload in the background — one reload for a burst of changes.
  useEffect(() => {
    let timer: number | undefined;
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

  const reload = useCallback(async () => {
    let data = initData();
    if (!data) {
      // Not inside Telegram: a browser, signed in or not.
      try {
        await fetchMe(WEB_SESSION);
        webSession = true;
        data = WEB_SESSION;
      } catch {
        setState({ status: "login" });
        return;
      }
    }
    const me = await fetchMe(data);
    setOwnAvatarCustom(Boolean(me.avatar_custom));
    setState({ status: "ok", me });
    setChatId((current) => {
      if (current && me.chats.some((c) => c.chat_id === current)) return current;
      return me.chats[0]?.chat_id ?? null;
    });
  }, []);

  useEffect(() => {
    window.Telegram?.WebApp?.setHeaderColor?.("#0a0c12");
    window.Telegram?.WebApp?.setBackgroundColor?.("#0a0c12");
    if (launchContext().game) preloadTitleSheet();
    let cancelled = false;
    void reload().catch((err: unknown) => {
      if (!cancelled) setState({ status: "error", message: String(err) });
    });
    return () => {
      cancelled = true;
    };
  }, [reload]);

  // A post's button from before person ids (#156) names a Telegram id: find whose
  // it is once signed in, then open their profile as a new button would.
  const signedIn = state.status === "ok";
  useEffect(() => {
    if (!signedIn || launch.legacyTgId == null || launch.personId != null) return;
    let cancelled = false;
    peopleApi
      .profileByTg(initData() || WEB_SESSION, launch.legacyTgId)
      .then((card) => {
        if (!cancelled) setPersonId((current) => current ?? card.id);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
    // Once, for the link the app was opened with.
  }, [signedIn]);

  const isSuperadmin = state.status === "ok" && state.me.is_superadmin;
  useEffect(() => {
    if (!isSuperadmin) return;
    const id = window.setTimeout(() => void loadAdmin(), PRELOAD_AFTER_MS);
    return () => window.clearTimeout(id);
  }, [isSuperadmin]);

  useLayoutEffect(() => {
    window.scrollTo(0, 0);
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
  }, [screen.name, personId]);

  const { indicator: pullIndicator } = usePullToRefresh(async () => {
    await reload();
    setRefreshKey((n) => n + 1);
  });

  // The phone's "back": from another tab to Home, and out of a person's page
  // (opened later, so it closes first). Screens, sheets and the game page
  // register their own.
  useBackHandler(screen.name !== SCREEN_NAMES.HOME, () => {
    setPersonId(null);
    setScreen(SCREENS.home);
  });
  useBackHandler(personId != null, () => setPersonId(null));

  if (state.status === "loading") {
    return launch.game ? <GameSkel /> : <AppSkel />;
  }
  if (state.status === "need-telegram") {
    return <p className="error">{t("ru", "needTelegram")}</p>;
  }
  if (state.status === "login") {
    return (
      <Login
        locale={navigator.language.startsWith("ru") ? "ru" : "en"}
        onSignedIn={() => {
          webSession = true;
          setState({ status: "loading" });
          void reload().catch((err: unknown) => setState({ status: "error", message: String(err) }));
        }}
      />
    );
  }
  if (state.status === "error") {
    return <p className="error">{state.message}</p>;
  }

  const { me } = state;
  const locale = localeOf(me);
  // Read by what renders outside the tree (a page's back arrow): the page's language.
  document.documentElement.lang = locale;
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

  // The first visit after nicknames arrived (#157): keep the one the bot made
  // from the username, or pick another. Shown before anything else, once.
  if (me.handle && !me.handle.confirmed) {
    return (
      <NicknameForm
        first
        locale={locale}
        handle={me.handle}
        personId={me.person_id ?? undefined}
        avatarCustom={me.avatar_custom}
        onAvatar={async (image) => {
          await putAvatar(data, image);
          setOwnAvatarCustom(true);
          if (me.person_id) forgetAvatar(me.person_id);
          await reload();
        }}
        onAvatarReset={async () => {
          await deleteAvatar(data);
          setOwnAvatarCustom(false);
          if (me.person_id) forgetAvatar(me.person_id);
          await reload();
        }}
        onSubmit={async (value) => {
          await putHandle(data, value);
          await reload();
        }}
        onKeep={async () => {
          await confirmHandle(data);
          await reload();
        }}
      />
    );
  }

  // Then, once, an email for whoever has none (owner, 2026-10-05): the main way
  // in, without Telegram.
  if (me.email_prompt) {
    return <AddEmailScreen locale={locale} data={data} onDone={reload} />;
  }

  // Every screen.name comparison the render below needs, computed once —
  // never a bare string literal re-typed at each call site.
  const isHome = screen.name === SCREEN_NAMES.HOME;
  const isFeed = screen.name === SCREEN_NAMES.FEED;
  const isSummary = screen.name === SCREEN_NAMES.SUMMARY;
  const isNews = screen.name === SCREEN_NAMES.NEWS;
  const isPeople = screen.name === SCREEN_NAMES.PEOPLE;
  const isSettings = screen.name === SCREEN_NAMES.SETTINGS;
  const isAdmin = screen.name === SCREEN_NAMES.ADMIN;
  const isConnectSteam = screen.name === SCREEN_NAMES.CONNECT_STEAM;
  const isConnectPsn = screen.name === SCREEN_NAMES.CONNECT_PSN;
  const isSettingsOrAdmin = isSettings || isAdmin;
  const isClubPane = isHome || isFeed || isSummary || isNews;
  const isConnectScreen = isConnectSteam || isConnectPsn;

  const showChrome = !personOpen && isHome;
  const clubPane = isFeed
    ? SCREEN_NAMES.FEED
    : isSummary
      ? SCREEN_NAMES.SUMMARY
      : isNews
        ? SCREEN_NAMES.NEWS
        : SCREEN_NAMES.HOME;
  const goHome = () => {
    tick();
    if (isHome && !personOpen) {
      window.scrollTo(0, 0);
      return;
    }
    setPersonId(null);
    setScreen(SCREENS.home);
  };

  const goTab = (tab: DockTab) => {
    tick();
    const already =
      tab === SCREEN_NAMES.SETTINGS
        ? isSettingsOrAdmin
        : tab === SCREEN_NAMES.FEED
          ? (isFeed || isSummary || isNews) && !personOpen
          : screen.name === tab && !personOpen;
    if (already) {
      window.scrollTo(0, 0);
      return;
    }
    setPersonId(null);
    setFocusSearch(false);
    setScreen(SCREENS[tab]);
  };

  return (
    <GameOpenProvider
      data={data}
      locale={locale}
      showSecrets={me.settings.show_secrets}
      // 0 matches nobody: a person without Telegram is not in a chat's lists.
      meId={me.person_id ?? 0}
      initialGame={launch.game}
      onGameChange={onGameChange}
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
      <Toaster />
      <ImageViewerHost closeLabel={t(locale, "close")} />

      {/* Kept mounted (just hidden) off the club pane, not unmounted:
          leaving it and coming back — e.g. through Settings — used to reset
          every pane's month and refetch from scratch. */}
      <div style={isClubPane ? undefined : { display: "none" }}>
        {homeWanted && (
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
            if (id === me.person_id) {
              setPersonId(null);
              setScreen(SCREENS.home);
              return;
            }
            setPersonId(id);
          }}
          onClosePerson={() => setPersonId(null)}
          onPane={(next) => setScreen(SCREENS[next])}
          onPersonVisible={setPersonOpen}
          onSettings={() => setScreen(SCREENS.settings)}
          onFind={() => {
            setFocusSearch(true);
            setPersonId(null);
            setScreen(SCREENS.people);
          }}
        />
        )}
      </div>

      {isPeople && (
        <People
          locale={locale}
          data={data}
          refreshKey={refreshKey}
          focusSearch={focusSearch}
          onFlash={setFlash}
          onOpenProfile={(id) => {
            setPersonId(id);
            setScreen(SCREENS.home);
          }}
        />
      )}

      {isSettings && (
        <Settings
          me={me}
          locale={locale}
          data={data}
          onFlash={setFlash}
          onAdmin={
            me.is_superadmin
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
          onAccountPublishes={(platform, publishes, accountId) =>
            void run(async () => {
              await setAccountPublishes(data, platform, publishes, accountId);
            })
          }
          onLogout={
            webSession
              ? () => {
                  void logout().finally(() => {
                    webSession = false;
                    setState({ status: "login" });
                  });
                }
              : undefined
          }
          onAvatar={async (image) => {
            await putAvatar(data, image);
            setOwnAvatarCustom(true);
            if (me.person_id) forgetAvatar(me.person_id);
            await reload();
          }}
          onAvatarReset={async () => {
            await deleteAvatar(data);
            setOwnAvatarCustom(false);
            if (me.person_id) forgetAvatar(me.person_id);
            await reload();
          }}
          onNickname={async (value) => {
            await putHandle(data, value);
            await reload();
          }}
          onConnectSteam={() => setScreen(SCREENS["connect-steam"])}
          onConnectPsn={() => setScreen(SCREENS["connect-psn"])}
          notes={platNotes}
          onConnectXbox={() =>
            void runPlat("xbox", async () => {
              const { authorize_url } = await connectXbox(data);
              if (window.Telegram?.WebApp?.openLink) window.Telegram.WebApp.openLink(authorize_url);
              else window.open(authorize_url, "_blank");
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
          onDisconnectPsn={(accountId) =>
            void runPlat("psn", async () => {
              if (!window.confirm(t(locale, "confirmDisconnect"))) return;
              await disconnectPsn(data, accountId);
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
          onLoginsChanged={() => void reload().catch(() => undefined)}
        />
      )}

      {isAdmin && (
        <Suspense fallback={<SettingsSkel />}>
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

      {!isConnectScreen && <InstallPrompt locale={locale} />}
      {!isConnectScreen && (
        <nav className="dock">
          <span
            className="dock-pill"
            style={{
              transform: `translateX(${
                (isSettingsOrAdmin ? 3 : isPeople ? 2 : isFeed || isSummary || isNews ? 1 : 0) * 100
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
            className={(isFeed || isSummary || isNews) && !personOpen ? "is-on" : undefined}
            onClick={() => goTab(SCREEN_NAMES.FEED)}
            aria-label={t(locale, "feed")}
          >
            <Icon name="feed" filled={(isFeed || isSummary || isNews) && !personOpen} />
          </button>
          <button
            type="button"
            className={isPeople ? "is-on" : undefined}
            onClick={() => goTab(SCREEN_NAMES.PEOPLE)}
            aria-label={t(locale, "searchTitle")}
          >
            <Icon name="search" filled={isPeople} />
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
