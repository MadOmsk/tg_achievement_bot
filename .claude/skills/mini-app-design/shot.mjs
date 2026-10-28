// Screenshots of the local Mini App as one signed-in person, phone-sized.
// node shot.mjs <url-path> <out.png> [scrollY] [fullPage]
import { spawn } from "node:child_process";
import { readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const [path = "/?t=pass", out = "shot.png", scroll = "0", full = "0"] = process.argv.slice(2);
const token = readFileSync(join(here, "..", "..", "..", "data", "screenshot-session.txt"), "utf8").trim();
const port = 9300 + Math.floor(Math.random() * 500);
const chrome = spawn("C:/Program Files/Google/Chrome/Application/chrome.exe", [
  "--headless=new",
  "--disable-gpu",
  "--hide-scrollbars",
  `--remote-debugging-port=${port}`,
  `--user-data-dir=${mkdtempSync(join(tmpdir(), "shot-"))}`,
  "about:blank",
]);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let target;
for (let i = 0; i < 50 && !target; i++) {
  await sleep(200);
  try {
    const list = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
    target = list.find((t) => t.type === "page");
  } catch {}
}
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r));
let id = 0;
const pending = new Map();
ws.addEventListener("message", (e) => {
  const msg = JSON.parse(e.data);
  // The page's own errors, so a blank screen says why.
  if (msg.method === "Runtime.exceptionThrown") console.error("page error:", msg.params.exceptionDetails?.exception?.description ?? msg.params.exceptionDetails?.text);
  if (msg.id && pending.has(msg.id)) {
    pending.get(msg.id)(msg.result ?? msg.error);
    pending.delete(msg.id);
  }
});
const send = (method, params = {}) =>
  new Promise((r) => {
    const n = ++id;
    pending.set(n, r);
    ws.send(JSON.stringify({ id: n, method, params }));
  });
await send("Network.enable");
await send("Runtime.enable");
// SLOW="*/api/mini/pass*|…": those requests never answer, so the screen's
// skeleton is what is shot.
if (process.env.SLOW) {
  await send("Fetch.enable", { patterns: process.env.SLOW.split("|").map((urlPattern) => ({ urlPattern })) });
}
await send("Network.setCookie", { name: "ab_session", value: token, domain: "localhost", path: "/", httpOnly: true });
await send("Emulation.setDeviceMetricsOverride", { width: 412, height: 915, deviceScaleFactor: 2, mobile: true });
await send("Page.enable");
await send("Page.navigate", { url: `http://localhost:5173${path}` });
await sleep(6000);
// Taps by visible text or aria-label, one after another: CLICKS="Изменить|Ноябрь 2026|Предпросмотр"
for (const label of (process.env.CLICKS ?? "").split("|").filter(Boolean)) {
  await send("Runtime.evaluate", {
    expression: `(() => { const t = ${JSON.stringify(label)}; const el = [...document.querySelectorAll("button, [role=button], .row, article, label")].reverse().find((e) => e.textContent.trim().includes(t) || e.getAttribute("aria-label") === t); el?.click(); return Boolean(el); })()`,
  });
  await sleep(1500);
}
// A script run on the page before the shot (EVAL="…"): a long text to try, say.
if (process.env.EVAL) {
  await send("Runtime.evaluate", { expression: process.env.EVAL });
  await sleep(500);
}
if (Number(scroll)) {
  await send("Runtime.evaluate", {
    expression: `document.querySelectorAll("[data-scroll]").forEach((el) => el.scrollTo(0, ${Number(scroll)}))`,
  });
  await sleep(800);
}
const shot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: full === "1" });
writeFileSync(out, Buffer.from(shot.data, "base64"));
ws.close();
chrome.kill();
console.log("saved", out);
process.exit(0);
