/**
 * The lens at a glass bar's edge, as Apple's glass bends what lies under it
 * (owner, 2026-10-25): an SVG displacement map that is neutral grey in the
 * middle and leans along the rim, so the content under the bar's edge is
 * pulled in like through the side of a lens while its middle stays true.
 *
 * Only Chromium draws an SVG filter as a backdrop (Android, Telegram there,
 * the desktop); Safari — every browser on an iPhone — would drop the whole
 * backdrop rule, so it keeps the plain blur and `lensSupported()` says no.
 */

const W = 360;
const H = 60;
const R = 30;
const RIM = 9;

// Red runs left to right, blue top to bottom: their difference makes each
// side lean its own way; the grey rect over the middle (blurred into the rim)
// is "no displacement".
const MAP = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
<defs>
<linearGradient id="r" x1="100%" y1="0%" x2="0%" y2="0%"><stop offset="0%" stop-color="#000"/><stop offset="100%" stop-color="#f00"/></linearGradient>
<linearGradient id="b" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stop-color="#000"/><stop offset="100%" stop-color="#00f"/></linearGradient>
<filter id="s"><feGaussianBlur stdDeviation="6"/></filter>
</defs>
<rect width="${W}" height="${H}" fill="#000"/>
<rect width="${W}" height="${H}" rx="${R}" fill="url(#r)"/>
<rect width="${W}" height="${H}" rx="${R}" fill="url(#b)" style="mix-blend-mode:difference"/>
<rect x="${RIM}" y="${RIM}" width="${W - 2 * RIM}" height="${H - 2 * RIM}" rx="${R - RIM}" fill="rgb(128,128,128)" fill-opacity="0.94" filter="url(#s)"/>
</svg>`;

const MAP_URL = `data:image/svg+xml,${encodeURIComponent(MAP)}`;

export const GLASS_LENS_ID = "glass-lens";

let supported: boolean | null = null;

export function lensSupported(): boolean {
  if (supported === null) {
    const ua = typeof navigator === "undefined" ? "" : navigator.userAgent;
    supported = /Chrome\/|Chromium\//.test(ua) && !/iPhone|iPad|iPod/.test(ua);
  }
  return supported;
}

/** The filter itself, once in the app; a bar uses it by `.has-lens`. */
export function GlassLens() {
  if (!lensSupported()) return null;
  return (
    <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden focusable="false">
      <filter
        id={GLASS_LENS_ID}
        x="0"
        y="0"
        width="1"
        height="1"
        primitiveUnits="objectBoundingBox"
        colorInterpolationFilters="sRGB"
      >
        <feImage href={MAP_URL} x="0" y="0" width="1" height="1" preserveAspectRatio="none" result="map" />
        <feDisplacementMap
          in="SourceGraphic"
          in2="map"
          scale="-0.2"
          xChannelSelector="R"
          yChannelSelector="B"
        />
      </filter>
    </svg>
  );
}
