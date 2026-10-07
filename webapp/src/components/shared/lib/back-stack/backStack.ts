import { useEffect, useRef } from "react";

/** The phone's own "back" (Android's button or gesture in the installed app,
 * Telegram's header button inside Telegram) steps back inside the app instead
 * of leaving it. Each open layer — a screen with a back arrow, a sheet, the game
 * page, a tab other than Home — registers here; "back" closes the topmost.
 *
 * The history holds one entry of ours per open layer, pushed when the layer
 * opens — while the tap that opened it still counts: Chrome lets "back" skip
 * any entry a page added without the user's gesture, so an entry put back
 * after a "back" was skipped and the next "back" left the app. Changes are
 * reconciled once a moment's layers have settled: a layer closing as another
 * opens is no history step at all, and nothing is pushed while a step back of
 * our own is still on its way. */

type Entry = { onBack: () => void };

const stack: Entry[] = [];
// How many entries of ours are in the history now.
let depth = 0;
// A step back of our own whose popstate has not come yet: not a "back".
let stepping = false;
let listening = false;

// The dev server's checks read how many layers are open and how many history
// entries hold them; a build leaves this out.
if (import.meta.env.DEV) {
  (window as unknown as { __backStack?: () => { layers: number; entries: number } }).__backStack = () => ({
    layers: stack.length,
    entries: depth,
  });
}

function telegramButton() {
  return window.Telegram?.WebApp?.BackButton;
}

/** Bring the history and Telegram's button in line with the stack. */
function settle(): void {
  window.setTimeout(() => {
    if (stepping) return;
    while (depth < stack.length) {
      window.history.pushState({ backStack: depth + 1 }, "");
      depth += 1;
    }
    if (depth > stack.length) {
      stepping = true;
      window.history.go(stack.length - depth);
      depth = stack.length;
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
    if (stepping) {
      stepping = false;
      settle();
      return;
    }
    depth = Math.max(0, depth - 1);
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
