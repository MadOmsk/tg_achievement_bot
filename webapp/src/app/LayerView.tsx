import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import type { Layer } from "./layers";

// Every page over the tabs is its own chunk, fetched the first time it
// opens (and ahead of that once Home is drawn, `prefetchLayers`), so the
// first load carries Home alone.
const AdminPage = lazy(() => import("../screens/admin/Admin").then((m) => ({ default: m.AdminPage })));
const AchievementPage = lazy(() => import("../screens/game/AchievementPage").then((m) => ({ default: m.AchievementPage })));
const Achievements = lazy(() => import("../screens/game/Achievements").then((m) => ({ default: m.Achievements })));
const GamePage = lazy(() => import("../screens/game/GamePage").then((m) => ({ default: m.GamePage })));
const NewsPostPage = lazy(() => import("../screens/news/NewsPostPage").then((m) => ({ default: m.NewsPostPage })));
const NotificationsPage = lazy(() => import("../screens/notifications/NotificationsPage").then((m) => ({ default: m.NotificationsPage })));
const FollowsPage = lazy(() => import("../screens/people/FollowsPage").then((m) => ({ default: m.FollowsPage })));
const PersonPage = lazy(() => import("../screens/people/PersonPage").then((m) => ({ default: m.PersonPage })));
const SearchPage = lazy(() => import("../screens/people/SearchPage").then((m) => ({ default: m.SearchPage })));
const AddGamePage = lazy(() => import("../screens/home/AddGame").then((m) => ({ default: m.AddGamePage })));
const ConnectPage = lazy(() => import("../screens/settings/Accounts").then((m) => ({ default: m.ConnectPage })));
const PsnTokenPage = lazy(() => import("../screens/settings/PsnToken").then((m) => ({ default: m.PsnTokenPage })));
const SettingsPage = lazy(() => import("../screens/settings/Settings").then((m) => ({ default: m.SettingsPage })));
const GalleryPage = lazy(() => import("../screens/game/GalleryPage").then((m) => ({ default: m.GalleryPage })));
const DlcPage = lazy(() => import("../screens/game/DlcPage").then((m) => ({ default: m.DlcPage })));
const EditionPage = lazy(() => import("../screens/game/DlcPage").then((m) => ({ default: m.EditionPage })));
const DlcDetailPage = lazy(() => import("../screens/game/DlcPage").then((m) => ({ default: m.DlcDetailPage })));
const SeasonPassPage = lazy(() => import("../screens/season-pass/SeasonPassPage").then((m) => ({ default: m.SeasonPassPage })));
const AchievementByRef = lazy(() => import("../screens/game/AchievementByRef").then((m) => ({ default: m.AchievementByRef })));

const LOADERS = [
  () => import("../screens/admin/Admin"),
  () => import("../screens/game/AchievementPage"),
  () => import("../screens/game/Achievements"),
  () => import("../screens/game/GamePage"),
  () => import("../screens/news/NewsPostPage"),
  () => import("../screens/notifications/NotificationsPage"),
  () => import("../screens/people/FollowsPage"),
  () => import("../screens/people/PersonPage"),
  () => import("../screens/people/SearchPage"),
  () => import("../screens/settings/Accounts"),
  () => import("../screens/settings/Settings"),
  () => import("../screens/game/GalleryPage"),
  () => import("../screens/game/DlcPage"),
  () => import("../screens/game/AchievementByRef"),
  () => import("../screens/season-pass/SeasonPassPage"),
];

/** Fetch every page's code once the app is idle, so a first visit never
 * waits on it (a page appears whole, in one motion). */
export function prefetchLayers(): void {
  const go = () => {
    for (const load of LOADERS) void load();
  };
  const idle = (window as { requestIdleCallback?: (f: () => void) => void }).requestIdleCallback;
  if (idle) idle(go);
  else window.setTimeout(go, 1500);
}

/** Pages that keep the toolbar under them: browsing, where a tab is one tap
 * away. Forms, sheets and the achievement page cover it. */
export function barShownOver(layer: Layer): boolean {
  return layer.kind === "game" || layer.kind === "person" || layer.kind === "news" || layer.kind === "achievements";
}

function layerKey(layer: Layer): string {
  switch (layer.kind) {
    case "game":
      return `game:${layer.ref.game_id ?? `${layer.ref.platform}:${layer.ref.title_id}`}:${layer.ref.person?.person_id ?? ""}`;
    case "person":
      return `person:${layer.personId}`;
    case "achievement":
      return `ach:${layer.ach.key}`;
    case "gallery":
      return `gallery:${layer.game}`;
    case "dlcs":
      return `dlcs:${layer.game}`;
    case "dlc":
      return `dlc:${layer.game}:${layer.dlc.name}`;
    case "edition":
      return `edition:${layer.game}:${layer.edition.name}`;
    case "achievementRef":
      return `ach-ref:${layer.platform}:${layer.titleId}:${layer.achievementId}:${layer.person?.id ?? ""}`;
    case "achievements":
      return `list:${layer.platform}:${layer.titleId}:${layer.person?.id ?? ""}`;
    case "news":
      return `news:${layer.appid}:${layer.gid}`;
    case "settings":
      return `settings:${layer.pane}`;
    case "admin":
      return `admin:${JSON.stringify(layer.screen)}`;
    case "follows":
      return `follows:${layer.personId}:${layer.which}`;
    case "connect":
      return `connect:${layer.platform}`;
    case "psn-token":
      return `psn-token:${layer.accountId ?? "new"}`;
    default:
      return layer.kind;
  }
}

/** A page whose code is still on its way: the page's ground slides in in its
 * place, and the page, once here, takes over without sliding in again. */
function Waiting({ onShown }: { onShown: () => void }) {
  useEffect(() => {
    onShown();
  }, [onShown]);
  return <div className="page page-waiting" />;
}

export function LayerView({
  layer,
  covered,
  onClose,
}: {
  layer: Layer;
  covered: boolean;
  onClose: () => void;
}) {
  const key = layerKey(layer);
  // Closing plays the page's way out before it goes.
  const [leaving, setLeaving] = useState(false);
  // A page plays its way in once: coming back to it (a back from the page
  // above) shows it as it was, with no motion again.
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const id = window.setTimeout(() => setSeen(true), 600);
    return () => window.clearTimeout(id);
  }, []);
  const done = useRef(false);
  const close = useCallback(() => {
    if (done.current) return;
    done.current = true;
    setLeaving(true);
    window.setTimeout(onClose, 180);
  }, [onClose]);
  const body = (() => {
    switch (layer.kind) {
      case "game":
        return <GamePage gameRef={layer.ref} onClose={close} layer={key} />;
      case "achievements":
        return <Achievements platform={layer.platform} titleId={layer.titleId} name={layer.name} cover={layer.cover ?? null} person={layer.person} lists={layer.lists} onClose={close} layer={key} />;
      case "achievement":
        return <AchievementPage ach={layer.ach} onClose={close} layer={key} />;
      case "gallery":
        return <GalleryPage game={layer.game} cover={layer.cover} videos={layer.videos} screenshots={layer.screenshots} onClose={close} layer={key} />;
      case "dlcs":
        return <DlcPage game={layer.game} gameNames={layer.gameNames} cover={layer.cover} dlcs={layer.dlcs} onClose={close} layer={key} />;
      case "edition":
        return <EditionPage game={layer.game} cover={layer.cover} edition={layer.edition} gameNames={layer.gameNames} dlcs={layer.dlcs} onClose={close} layer={key} />;
      case "dlc":
        return <DlcDetailPage game={layer.game} gameNames={layer.gameNames} cover={layer.cover} dlc={layer.dlc} onClose={close} layer={key} />;
      case "achievementRef":
        return (
          <AchievementByRef
            platform={layer.platform}
            titleId={layer.titleId}
            achievementId={layer.achievementId}
            person={layer.person}
            onClose={close}
            layer={key}
          />
        );
      case "person":
        return <PersonPage personId={layer.personId} onClose={close} layer={key} />;
      case "follows":
        return <FollowsPage personId={layer.personId} which={layer.which} onClose={close} layer={key} />;
      case "news":
        return <NewsPostPage appid={layer.appid} gid={layer.gid} item={layer.item} game={layer.game} onClose={close} layer={key} />;
      case "pass":
        return <SeasonPassPage onClose={close} layer={key} />;
      case "notifications":
        return <NotificationsPage onClose={close} layer={key} />;
      case "search":
        return <SearchPage onClose={close} layer={key} />;
      case "addGame":
        return <AddGamePage onClose={close} layer={key} />;
      case "settings":
        return <SettingsPage pane={layer.pane} onClose={close} layer={key} />;
      case "connect":
        return <ConnectPage platform={layer.platform} onClose={close} layer={key} />;
      case "psn-token":
        return <PsnTokenPage accountId={layer.accountId} onClose={close} layer={key} />;
      case "admin":
        return <AdminPage screen={layer.screen} onClose={close} layer={key} />;
    }
  })();
  return (
    <div className={`layer${covered ? " layer-covered" : ""}${seen ? " layer-seen" : ""}${leaving ? " layer-leaving" : ""}`}>
      <Suspense fallback={<Waiting onShown={() => setSeen(true)} />}>{body}</Suspense>
    </div>
  );
}
