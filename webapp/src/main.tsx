import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { captureInstallPrompt } from "./core/install";

const root = document.getElementById("root");
if (!root) {
  throw new Error("#root missing");
}

window.Telegram?.WebApp?.ready();
window.Telegram?.WebApp?.expand();
// Telegram's own vertical swipe (collapse/close) fights the feed scroll.
window.Telegram?.WebApp?.disableVerticalSwipes?.();

// The service worker shows the app's own pushes (#164). Only in a browser:
// inside Telegram the bot's messages already are the notifications.
if ("serviceWorker" in navigator && !window.Telegram?.WebApp?.initData) {
  void navigator.serviceWorker
    .register(`${import.meta.env.BASE_URL}sw.js`, { scope: import.meta.env.BASE_URL })
    .catch(() => undefined);
  captureInstallPrompt();
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
