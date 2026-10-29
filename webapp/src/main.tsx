import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { applyPalette } from "./app/env";
import { captureInstallPrompt } from "./core/install";

const root = document.getElementById("root");
if (!root) {
  throw new Error("#root missing");
}

// The palette this device picked, before the first paint, so it never flashes.
applyPalette();

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

// Every picture appears whole, in one fade, never drawn top to bottom as it
// arrives: it is shown once loaded (styles/base: img:not([data-in])).
const showImage = (event: Event) => {
  const img = event.target;
  if (img instanceof HTMLImageElement) img.dataset.in = "";
};
document.addEventListener("load", showImage, true);
document.addEventListener("error", showImage, true);
// A picture the browser already had can finish before it is in the page
// (its load event then never reaches the document): mark those as they come in.
const markLoaded = (node: Node) => {
  const imgs = node instanceof HTMLImageElement ? [node] : node instanceof Element ? [...node.querySelectorAll("img")] : [];
  for (const img of imgs) if (img.complete) img.dataset.in = "";
};
new MutationObserver((changes) => {
  for (const change of changes) {
    if (change.type === "attributes" && change.target instanceof HTMLImageElement) markLoaded(change.target);
    change.addedNodes.forEach(markLoaded);
  }
}).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ["src"] });

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
