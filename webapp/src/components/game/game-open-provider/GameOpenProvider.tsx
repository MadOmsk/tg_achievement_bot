import { lazy, Suspense, useCallback, useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { FeedItem, GameRef } from "../../../api";
import type { Locale } from "../../../i18n";
import { AchievementOpenContext, GameOpenContext } from "../../shared/lib";

// The game page (#147, stage 5; owner, 2026-10-25: a tap on a game opens it,
// the achievements of a list open from it) is kept off Home's own critical
// bundle, loaded only once a game is actually opened (including straight
// from a Mini App deep link).
const loadGamePage = () => import("../game-page/GamePage");
const GamePage = lazy(() => loadGamePage().then((m) => ({ default: m.GamePage })));
const AchievementLoader = lazy(() =>
  import("../achievement-page/AchievementLoader").then((m) => ({ default: m.AchievementLoader })),
);

/** Starts fetching the game page's code — for an app opened straight on a game,
 * while it still asks who is looking. */
export function preloadTitleSheet(): void {
  void loadGamePage();
}

/**
 * Lets any card open the game's own page. It is portalled to the body so it
 * stacks above a drawer the card may itself be in.
 */
export function GameOpenProvider({
  data,
  locale,
  showSecrets,
  meId,
  initialGame = null,
  onGameChange,
  children,
}: {
  data: string;
  locale: Locale;
  showSecrets?: boolean;
  meId: number;
  /** A game to open right away — a Mini App deep link landing straight on it. */
  initialGame?: GameRef | null;
  /** Told whether a game page is open, each time that changes. */
  /** The game page open now, or null once it is left. */
  onGameChange?: (game: GameRef | null) => void;
  children: ReactNode;
}) {
  const [game, setGame] = useState<GameRef | null>(initialGame);
  const open = useCallback((next: GameRef) => setGame(next), []);
  const [achievement, setAchievement] = useState<FeedItem | null>(null);
  const openAchievement = useCallback((item: FeedItem) => setAchievement(item), []);

  // While a game page covers the app, the app beneath stops being painted
  // (see base.css): a long feed of blurred, filtered cards under a full-screen
  // layer was eating the phone's graphics memory, and that showed as artifacts.
  useEffect(() => {
    onGameChange?.(game);
  }, [game, onGameChange]);

  useEffect(() => {
    if (!game) return;
    const html = document.documentElement;
    html.classList.add("has-game-page");
    return () => html.classList.remove("has-game-page");
  }, [game]);
  return (
    <GameOpenContext.Provider value={open}>
      <AchievementOpenContext.Provider value={openAchievement}>
      {children}
      {game &&
        createPortal(
          <Suspense fallback={null}>
            <GamePage
              game={game}
              data={data}
              locale={locale}
              showSecrets={showSecrets}
              meId={meId}
              onClose={() => setGame(null)}
            />
          </Suspense>,
          // A portal, like every sheet: appended after the ones already open,
          // so the page lands above them.
          document.body,
        )}
      {achievement && (
        <Suspense fallback={null}>
          <AchievementLoader
            data={data}
            locale={locale}
            item={achievement}
            onClose={() => setAchievement(null)}
          />
        </Suspense>
      )}
      </AchievementOpenContext.Provider>
    </GameOpenContext.Provider>
  );
}
