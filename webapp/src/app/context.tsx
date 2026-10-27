import { createContext, useContext } from "react";
import type { MeResponse } from "../api";
import { t, type Locale, type TranslationKey } from "../i18n";
import type { Layer, Tab } from "./layers";

export type PictureLook = { on: boolean; scale: number; lowRes: number };

export type App = {
  /** Init Data inside Telegram, the session marker in a browser. */
  data: string;
  me: MeResponse;
  locale: Locale;
  tr: (key: TranslationKey) => string;
  picture: PictureLook;
  setMe: (me: MeResponse) => void;
  reloadMe: () => Promise<void>;
  tab: Tab;
  setTab: (tab: Tab) => void;
  open: (layer: Layer) => void;
  /** Close the topmost layer. */
  back: () => void;
  /** Close every layer, e.g. a tab tapped while pages are open. */
  closeAll: () => void;
  toast: (message: string, kind?: "info" | "error") => void;
  signOut: () => void;
};

export const AppContext = createContext<App | null>(null);

export function useApp(): App {
  const app = useContext(AppContext);
  if (!app) throw new Error("useApp outside AppContext");
  return app;
}

export function translator(locale: Locale): (key: TranslationKey) => string {
  return (key) => t(locale, key);
}

export const DEFAULT_PICTURE: PictureLook = { on: true, scale: 4, lowRes: 200 };
