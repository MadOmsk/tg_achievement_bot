import { isStandalone } from "../core/install";

/** Where the app runs: inside Telegram as a Mini App (signed by Init Data, its
 * header's back button, the bot's DMs as notices), or as a site — in a browser
 * tab or installed as an app (a session cookie, our own back arrow, pushes). */
export type RunMode = "telegram" | "browser" | "installed";

export function runMode(): RunMode {
  if (window.Telegram?.WebApp?.initData) return "telegram";
  return isStandalone() ? "installed" : "browser";
}

export function inTelegram(): boolean {
  return runMode() === "telegram";
}

/** Stores, Steam, YouTube, HLTB: through Telegram's own opener inside it (a
 * plain link would open inside the Mini App's webview), a new tab elsewhere. */
export function openExternal(url: string): void {
  const app = window.Telegram?.WebApp;
  if (app?.initData && app.openLink) {
    app.openLink(url);
    return;
  }
  window.open(url, "_blank", "noopener,noreferrer");
}

/** Telegram draws its own header and the area behind the page: in our colour. */
export function paintTelegram(surface: string): void {
  const app = window.Telegram?.WebApp;
  if (!app?.initData) return;
  app.setHeaderColor?.(surface);
  app.setBackgroundColor?.(surface);
}

export type Palette = "violet" | "graphite" | "ocean" | "mint" | "ember" | "rose" | "halloween";
export type Mode = "auto" | "light" | "dark";
export const PALETTES: Palette[] = ["violet", "graphite", "ocean", "mint", "ember", "rose", "halloween"];
const LOOK_KEY = "look";
const LOOK_CHANGED = "look-changed";

/** The palette and the mode this device keeps (a per-viewer convenience:
 * gone in a private window, the defaults then). */
export function look(): { palette: Palette; mode: Mode } {
  try {
    const raw = JSON.parse(localStorage.getItem(LOOK_KEY) ?? "{}");
    return {
      palette: PALETTES.includes(raw.palette) ? raw.palette : "violet",
      mode: ["auto", "light", "dark"].includes(raw.mode) ? raw.mode : "auto",
    };
  } catch {
    return { palette: "violet", mode: "auto" };
  }
}

export function setLook(next: Partial<{ palette: Palette; mode: Mode }>): void {
  try {
    localStorage.setItem(LOOK_KEY, JSON.stringify({ ...look(), ...next }));
  } catch {
    // Not kept on this device; it still applies until the page is closed.
  }
  applyPalette(next.palette ?? look().palette);
  window.dispatchEvent(new Event(LOOK_CHANGED));
}

export function applyPalette(palette: Palette = look().palette): void {
  if (palette === "violet") delete document.documentElement.dataset.palette;
  else document.documentElement.dataset.palette = palette;
}

/** Dark or light: the mode picked, else Telegram's own theme inside it and
 * the system's elsewhere — and follow it when it changes. */
export function followTheme(onChange: () => void): () => void {
  const app = window.Telegram?.WebApp;
  const media = window.matchMedia?.("(prefers-color-scheme: light)");
  const apply = () => {
    const mode = look().mode;
    const light =
      mode === "auto" ? (app?.initData ? app.colorScheme === "light" : Boolean(media?.matches)) : mode === "light";
    document.documentElement.dataset.theme = light ? "light" : "dark";
    applyPalette();
    onChange();
  };
  apply();
  window.addEventListener(LOOK_CHANGED, apply);
  media?.addEventListener?.("change", apply);
  const tg = app as unknown as { onEvent?: (e: string, f: () => void) => void; offEvent?: (e: string, f: () => void) => void };
  if (app?.initData) tg.onEvent?.("themeChanged", apply);
  return () => {
    window.removeEventListener(LOOK_CHANGED, apply);
    media?.removeEventListener?.("change", apply);
    if (app?.initData) tg.offEvent?.("themeChanged", apply);
  };
}

export function surfaceColor(): string {
  return getComputedStyle(document.documentElement).getPropertyValue("--surface").trim() || "#141218";
}
