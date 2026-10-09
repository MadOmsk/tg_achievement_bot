/**
 * Dev helper: a Cloudflare quick tunnel to the catalog viewer (scripts/catalog_viewer.py,
 * :8090), for reaching it from outside. Writes the URL to ../data/viewer-tunnel.url.
 * The viewer has no authentication yet: share the address with care.
 */
import { startTunnel } from "untun";
import { writeFile } from "node:fs/promises";
const tunnel = await startTunnel({ url: "http://127.0.0.1:8090", acceptCloudflareNotice: true });
const url = (await tunnel.getURL()).trim();
await writeFile(new URL("../../data/viewer-tunnel.url", import.meta.url), url + "\n");
console.log("viewer tunnel:", url);
setInterval(() => {}, 1 << 30);
