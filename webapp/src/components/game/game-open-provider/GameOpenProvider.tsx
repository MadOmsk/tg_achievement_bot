import { useCallback, useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { GameRef } from "../../../api";
import type { Locale } from "../../../i18n";
import { GameOpenContext } from "../../shared/lib";
import { TitleSheet } from "../title-sheet/TitleSheet";

/**
 * Lets any card open the game's own page. It is portalled to the body so it
 * stacks above a drawer the card may itself be in.
 */
export function GameOpenProvider({
  data,
  locale,
  showSecrets,
  meId,
  children,
}: {
  data: string;
  locale: Locale;
  showSecrets?: boolean;
  meId: number;
  children: ReactNode;
}) {
  const [game, setGame] = useState<GameRef | null>(null);
  const open = useCallback((next: GameRef) => setGame(next), []);

  // While a game page covers the app, the app beneath stops being painted
  // (see base.css): a long feed of blurred, filtered cards under a full-screen
  // layer was eating the phone's graphics memory, and that showed as artifacts.
  useEffect(() => {
    if (!game) return;
    const html = document.documentElement;
    html.classList.add("has-game-page");
    return () => html.classList.remove("has-game-page");
  }, [game]);
  return (
    <GameOpenContext.Provider value={open}>
      {children}
      {game &&
        createPortal(
          <TitleSheet
            game={game}
            data={data}
            locale={locale}
            showSecrets={showSecrets}
            meId={meId}
            onClose={() => setGame(null)}
          />,
          // A portal, like every sheet: appended after the ones already open,
          // so the page lands above them.
          document.body,
        )}
    </GameOpenContext.Provider>
  );
}
