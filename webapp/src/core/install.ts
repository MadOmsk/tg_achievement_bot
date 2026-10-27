/** Installing the app (a PWA) from a plain browser. Chromium browsers hand over
 * their own install dialog through `beforeinstallprompt`, which fires once and
 * early — so it is caught at start-up (`captureInstallPrompt` in main.tsx) and
 * kept until the banner asks for it. Safari has no such event: on an iPhone the
 * banner can only say where the menu item is. */

type InstallEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

export type InstallWay = "prompt" | "ios" | null;

const CHANGED = "install-prompt-changed";
let deferred: InstallEvent | null = null;

export function captureInstallPrompt(): void {
  window.addEventListener("beforeinstallprompt", (event) => {
    // Ours instead of the browser's own mini bar: one banner, one look.
    event.preventDefault();
    deferred = event as InstallEvent;
    window.dispatchEvent(new Event(CHANGED));
  });
  window.addEventListener("appinstalled", () => {
    deferred = null;
    window.dispatchEvent(new Event(CHANGED));
  });
}

export function onInstallChange(listener: () => void): () => void {
  window.addEventListener(CHANGED, listener);
  return () => window.removeEventListener(CHANGED, listener);
}

function isIos(): boolean {
  return (
    /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
  );
}

export function isStandalone(): boolean {
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    (navigator as { standalone?: boolean }).standalone === true
  );
}

/** How this device can install the app right now; null when it cannot or need not. */
export function installWay(): InstallWay {
  if (window.Telegram?.WebApp?.initData || isStandalone()) return null;
  if (deferred) return "prompt";
  return isIos() ? "ios" : null;
}

/** Opens the browser's own install dialog. True when the person accepted. */
export async function promptInstall(): Promise<boolean> {
  const event = deferred;
  if (!event) return false;
  deferred = null;
  await event.prompt();
  const { outcome } = await event.userChoice;
  window.dispatchEvent(new Event(CHANGED));
  return outcome === "accepted";
}
