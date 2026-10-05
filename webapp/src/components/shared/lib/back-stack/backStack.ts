import { useEffect, useRef } from "react";

/** The phone's own "back" (Android's button or gesture in the installed app,
 * Telegram's header button inside Telegram) steps back inside the app instead
 * of leaving it. Each open layer — a screen with a back arrow, a sheet, the game
 * page, a tab other than Home — registers here; "back" closes the topmost.
 *
 * The browser's history holds one entry of ours, no more, while anything is
 * open: popping it is the "back", and it is put back while layers remain. One
 * entry, not one per layer, because a layer closing and another opening in the
 * same moment would race a history step against a new entry and lose one —
 * and the last "back" would then leave the app. */

type Entry = { onBack: () => void };

const stack: Entry[] = [];
// Whether our entry is in the history now.
let armed = false;
// History steps this module took itself: their popstate is not a "back".
let quiet = 0;
let listening = false;

function telegramButton() {
  return window.Telegram?.WebApp?.BackButton;
}

/** Bring the history and Telegram's button in line with the stack, once the
 * layers opening and closing in this moment have settled. */
function settle(): void {
  window.setTimeout(() => {
    if (stack.length > 0 && !armed) {
      window.history.pushState({ backStack: true }, "");
      armed = true;
    } else if (stack.length === 0 && armed) {
      armed = false;
      quiet += 1;
      window.history.back();
    }
    const button = telegramButton();
    if (stack.length > 0) button?.show();
    else button?.hide();
  }, 0);
}

function listen(): void {
  if (listening) return;
  listening = true;
  window.addEventListener("popstate", () => {
    if (quiet > 0) {
      quiet -= 1;
      return;
    }
    armed = false;
    stack.pop()?.onBack();
    settle();
  });
  telegramButton()?.onClick(() => window.history.back());
}

function push(entry: Entry): () => void {
  listen();
  stack.push(entry);
  settle();
  return () => {
    const at = stack.indexOf(entry);
    // Already popped: it was the "back" itself that closed this layer.
    if (at < 0) return;
    stack.splice(at, 1);
    settle();
  };
}

/** While `active`, the phone's "back" calls `onBack` (the latest one given).
 * `layer` names what is open: React keeps one component through a change of
 * screen (one back arrow, another title), and a new layer is a new entry. */
export function useBackHandler(active: boolean, onBack: () => void, layer?: string): void {
  const handler = useRef(onBack);
  handler.current = onBack;
  useEffect(() => {
    if (!active) return;
    return push({ onBack: () => handler.current() });
  }, [active, layer]);
}
