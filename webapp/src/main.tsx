import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// Imported before ./App on purpose: the bundler emits CSS in the order it
// first meets each module, depth-first from here, so this line is what
// guarantees the global layer (tokens/base/layout) actually precedes every
// component's own co-located stylesheet in the built output.
import "./components/shared/styles/index.css";
import { App } from "./App";

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
