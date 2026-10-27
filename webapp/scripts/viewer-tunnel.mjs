/**
 * Dev helper: a Cloudflare quick tunnel to the catalog viewer (scripts/catalog_viewer.py,
 * :8090, or the port given), for reaching it from outside. Writes the URL to
 * ../data/viewer-tunnel[-<port>].url.
 * The viewer has no authentication yet: share the address with care.
 */
import { startTunnel } from "untun";
import { writeFile } from "node:fs/promises";
const port = process.argv[2] || "8090";
const tunnel = await startTunnel({ url: `http://127.0.0.1:${port}`, acceptCloudflareNotice: true });
const url = (await tunnel.getURL()).trim();
const file = port === "8090" ? "viewer-tunnel.url" : `viewer-tunnel-${port}.url`;
await writeFile(new URL(`../../data/${file}`, import.meta.url), url + "\n");
console.log("viewer tunnel:", url);
setInterval(() => {}, 1 << 30);
