/**
 * Dev helper: Vite on :5173 + Cloudflare quick tunnel (via untun).
 *
 * Writes the public HTTPS URL to ../data/mini-app-tunnel.url so manage.ps1
 * can inject MINI_APP_URL into the test bot (menu button + /start Open app).
 * URL changes each run — BotFather Main Mini App is optional; Bot API menu is enough.
 */
import { spawn } from "node:child_process";
import { mkdir, writeFile, unlink } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { startTunnel } from "untun";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webappRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(webappRoot, "..");
const urlFile = path.join(repoRoot, "data", "mini-app-tunnel.url");
const pidFile = path.join(repoRoot, "data", "webapp.pid");
const vitePort = Number(process.env.VITE_PORT || 5173);
const localUrl = `http://127.0.0.1:${vitePort}`;

await mkdir(path.dirname(urlFile), { recursive: true });
await writeFile(pidFile, String(process.pid), "utf8");

const vite = spawn(
  process.platform === "win32" ? "npx.cmd" : "npx",
  ["vite", "--host", "127.0.0.1", "--port", String(vitePort)],
  {
    cwd: webappRoot,
    stdio: "inherit",
    shell: process.platform === "win32",
    env: process.env,
  },
);

vite.on("exit", (code) => {
  console.error(`[dev-tunnel] vite exited (${code})`);
  void shutdown(code ?? 1);
});

await waitForHttp(localUrl, 60_000);
console.log(`[dev-tunnel] vite ready at ${localUrl}`);

const tunnel = await startTunnel({
  url: localUrl,
  acceptCloudflareNotice: true,
});
if (!tunnel) {
  throw new Error("untun returned no tunnel");
}

const publicUrl = (await tunnel.getURL()).trim();
if (!publicUrl) {
  throw new Error("tunnel has no url");
}

await writeFile(urlFile, publicUrl + "\n", "utf8");
console.log(`[dev-tunnel] public URL: ${publicUrl}`);
console.log(`[dev-tunnel] wrote ${urlFile}`);
console.log(
  "[dev-tunnel] use: .\\manage.ps1 start -Test -Web  (or restart test bot with MINI_APP_URL set)",
);

async function shutdown(code = 0) {
  try {
    await tunnel.close();
  } catch {
    /* ignore */
  }
  if (!vite.killed) {
    vite.kill();
  }
  await unlink(urlFile).catch(() => undefined);
  await unlink(pidFile).catch(() => undefined);
  process.exit(code);
}

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    void shutdown(0);
  });
}

async function waitForHttp(url, timeoutMs) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const res = await fetch(url, { method: "GET" });
      if (res.ok || res.status === 404) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  throw new Error(`timed out waiting for ${url}`);
}
