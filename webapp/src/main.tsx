import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";

const root = document.getElementById("root");
if (!root) {
  throw new Error("#root missing");
}

window.Telegram?.WebApp?.ready();
window.Telegram?.WebApp?.expand();
// Telegram's own vertical swipe (collapse/close) fights the feed scroll.
window.Telegram?.WebApp?.disableVerticalSwipes?.();

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
