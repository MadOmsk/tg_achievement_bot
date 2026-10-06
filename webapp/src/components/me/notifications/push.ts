import { notificationsApi } from "../../../api/notifications/notificationsApi";

/** Where push stands on this device (#164). */
export type PushState =
  /** Inside Telegram: the bot's messages are the notifications there. */
  | "telegram"
  /** An iPhone/iPad page not added to the Home Screen: Safari pushes only then. */
  | "ios-install"
  /** The browser has no push at all. */
  | "unsupported"
  /** The server has no push set up (no app address to open). */
  | "unavailable"
  /** The person said no in the browser's own prompt; only its settings undo that. */
  | "denied"
  | "off"
  | "on";

function isIos(): boolean {
  return /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

function standalone(): boolean {
  return window.matchMedia?.("(display-mode: standalone)").matches || (navigator as { standalone?: boolean }).standalone === true;
}

function keyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const padded = (base64url + "=".repeat((4 - (base64url.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(padded);
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

async function registration(): Promise<ServiceWorkerRegistration | null> {
  if (!("serviceWorker" in navigator)) return null;
  return (await navigator.serviceWorker.getRegistration(import.meta.env.BASE_URL)) ?? null;
}

const LAST_STATE_KEY = "push-state";

function remember(state: PushState): PushState {
  try {
    localStorage.setItem(LAST_STATE_KEY, state);
  } catch {
    // Private mode: the next screen asks again.
  }
  return state;
}

/** What can be told at once, without the server or the service worker: the
 * device's own limits, else what this device was the last time it was asked.
 * The screen draws it straight away and `pushState` corrects it. */
export function quickPushState(): PushState {
  if (window.Telegram?.WebApp?.initData) return "telegram";
  if (isIos() && !standalone()) return "ios-install";
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
    return "unsupported";
  }
  if (Notification.permission === "denied") return "denied";
  try {
    const last = localStorage.getItem(LAST_STATE_KEY) as PushState | null;
    if (last === "on" || last === "off" || last === "unavailable") return last;
  } catch {
    // No storage: assume off until asked.
  }
  return Notification.permission === "granted" ? "on" : "off";
}

export async function pushState(data: string): Promise<PushState> {
  const quick = quickPushState();
  if (quick === "telegram" || quick === "ios-install" || quick === "unsupported" || quick === "denied") {
    return quick;
  }
  const key = await notificationsApi.pushKey(data).catch(() => null);
  if (!key?.available) return remember("unavailable");
  const reg = await registration();
  const sub = await reg?.pushManager.getSubscription();
  return remember(sub ? "on" : "off");
}

/** Ask the browser, subscribe with the server's key, and hand the subscription
 * to the server. Resolves to the state it ended in. */
export async function enablePush(data: string): Promise<PushState> {
  const key = await notificationsApi.pushKey(data);
  if (!key.available || !key.public_key) return "unavailable";
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return permission === "denied" ? "denied" : "off";
  const reg =
    (await registration()) ??
    (await navigator.serviceWorker.register(`${import.meta.env.BASE_URL}sw.js`, {
      scope: import.meta.env.BASE_URL,
    }));
  await navigator.serviceWorker.ready;
  const sub =
    (await reg.pushManager.getSubscription()) ??
    (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(key.public_key) }));
  await notificationsApi.subscribe(data, sub.toJSON());
  return remember("on");
}

export async function disablePush(data: string): Promise<PushState> {
  const reg = await registration();
  const sub = await reg?.pushManager.getSubscription();
  if (sub) {
    await notificationsApi.unsubscribe(data, sub.endpoint).catch(() => undefined);
    await sub.unsubscribe();
  }
  return remember("off");
}
