import { useEffect, useState, type CSSProperties } from "react";

const STORE_KEY = "art-hues";
const STORE_MAX = 300;
const cache = new Map<string, number | null>(loadHues());

/** Hues read before, kept on the device: a game opened again is drawn in its
 * own colours at once. */
function loadHues(): [string, number | null][] {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    return raw ? (JSON.parse(raw) as [string, number | null][]) : [];
  } catch {
    return [];
  }
}

function saveHues(): void {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify([...cache].slice(-STORE_MAX)));
  } catch {
    // No storage: read again next time.
  }
}

/** A small copy of the picture, where the store can make one: the colour is
 * read from 64 pixels, not from a 1920 px hero. */
function sampleUrl(url: string): string {
  try {
    const u = new URL(url, window.location.href);
    if (u.hostname === "store-images.s-microsoft.com") u.searchParams.set("w", "64");
    return u.toString();
  } catch {
    return url;
  }
}

/** The picture's leading hue: the average of its colourful pixels, weighted by
 * how colourful each is. Null when the store does not allow reading it. */
function readHue(url: string): Promise<number | null> {
  return new Promise((resolve) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.decoding = "async";
    img.onload = () => {
      try {
        const size = 24;
        const canvas = document.createElement("canvas");
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext("2d", { willReadFrequently: true });
        if (!ctx) return resolve(null);
        ctx.drawImage(img, 0, 0, size, size);
        const px = ctx.getImageData(0, 0, size, size).data;
        let x = 0;
        let y = 0;
        let weight = 0;
        for (let i = 0; i < px.length; i += 4) {
          const r = px[i] / 255;
          const g = px[i + 1] / 255;
          const b = px[i + 2] / 255;
          const max = Math.max(r, g, b);
          const min = Math.min(r, g, b);
          const chroma = max - min;
          if (chroma < 0.08 || max < 0.12) continue;
          let h: number;
          if (max === r) h = ((g - b) / chroma) % 6;
          else if (max === g) h = (b - r) / chroma + 2;
          else h = (r - g) / chroma + 4;
          const rad = (h * 60 * Math.PI) / 180;
          x += Math.cos(rad) * chroma;
          y += Math.sin(rad) * chroma;
          weight += chroma;
        }
        if (weight < 3) return resolve(null);
        resolve(((Math.atan2(y, x) * 180) / Math.PI + 360) % 360);
      } catch {
        resolve(null);
      }
    };
    img.onerror = () => resolve(null);
    img.src = sampleUrl(url);
  });
}

/** A whole tonal scheme from one hue, always muted: the containers barely
 * coloured, only the accent a clear tone of it. */
function scheme(h: number, light: boolean): CSSProperties {
  const hsl = (s: number, l: number) => `hsl(${Math.round(h)} ${s}% ${l}%)`;
  const vars: Record<string, string> = light
    ? {
        "--surface": hsl(40, 98),
        "--surface-1": hsl(32, 95),
        "--surface-2": hsl(28, 93),
        "--surface-3": hsl(24, 90),
        "--surface-4": hsl(20, 87),
        "--outline": hsl(12, 78),
        "--outline-soft": hsl(18, 89),
        "--primary": hsl(42, 36),
        "--on-primary": "#ffffff",
        "--primary-container": hsl(70, 90),
        "--primary-container-2": hsl(60, 85),
        "--on-primary-container": hsl(60, 15),
        "--on-primary-container-2": hsl(24, 32),
        "--secondary-container": hsl(36, 88),
        "--on-secondary-container": hsl(24, 28),
      }
    : {
        "--surface": hsl(18, 7),
        "--surface-1": hsl(15, 11),
        "--surface-2": hsl(14, 13),
        "--surface-3": hsl(13, 17),
        "--surface-4": hsl(12, 22),
        "--outline": hsl(10, 32),
        "--outline-soft": hsl(12, 19),
        "--primary": hsl(85, 80),
        "--on-primary": hsl(70, 16),
        "--primary-container": hsl(36, 24),
        "--primary-container-2": hsl(34, 29),
        "--on-primary-container": hsl(90, 91),
        "--on-primary-container-2": hsl(45, 82),
        "--secondary-container": hsl(22, 24),
        "--on-secondary-container": hsl(45, 90),
      };
  return vars as CSSProperties;
}

/** Which picture a game's page took its colours from, by the game's
 * lists and its name: the pages inside a game (its achievements, one
 * achievement, its gallery, a post of its) take the same colours. */
const gameArt = new Map<string, string>();

export function rememberGameArt(keys: Array<string | null | undefined>, url: string | null | undefined): void {
  if (!url) return;
  for (const k of keys) if (k) gameArt.set(k, url);
}

export function gameArtOf(...keys: Array<string | null | undefined>): string | undefined {
  for (const k of keys) {
    const url = k ? gameArt.get(k) : undefined;
    if (url) return url;
  }
  return undefined;
}

/** The page's own colours from its picture (owner's design E), set on the
 * page's root so every part of it draws in them. `settled` once the colour is
 * known or known to be unknowable — or a short wait ran out —, so the page can
 * show its body in its final colours instead of repainting before the eyes. */
export function useArtTheme(url: string | null | undefined): { style: CSSProperties | undefined; settled: boolean } {
  const [hue, setHue] = useState<number | null>(() => (url ? (cache.get(url) ?? null) : null));
  const [settled, setSettled] = useState(() => Boolean(url && cache.has(url)));
  useEffect(() => {
    if (!url) return;
    if (cache.has(url)) {
      setHue(cache.get(url) ?? null);
      setSettled(true);
      return;
    }
    let live = true;
    const giveUp = window.setTimeout(() => live && setSettled(true), 250);
    void readHue(url).then((h) => {
      cache.set(url, h);
      saveHues();
      if (!live) return;
      setHue(h);
      setSettled(true);
    });
    return () => {
      live = false;
      window.clearTimeout(giveUp);
    };
  }, [url]);
  return {
    style: hue === null ? undefined : scheme(hue, document.documentElement.dataset.theme === "light"),
    settled,
  };
}
