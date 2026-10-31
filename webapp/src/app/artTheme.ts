import { useEffect, useState, type CSSProperties } from "react";

// The second reading (the dominant colour, not the average): the first one's are not reused.
const STORE_KEY = "art-colours";
const STORE_MAX = 300;
const cache = new Map<string, Art | null>(loadHues());

/** Colours read before, kept on the device: a game opened again is drawn in its
 * own colours at once. */
function loadHues(): [string, Art | null][] {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    return raw ? (JSON.parse(raw) as [string, Art | null][]) : [];
  } catch {
    return [];
  }
}

function saveHues(): void {
  try {
    localStorage.setItem(
      STORE_KEY,
      JSON.stringify([...cache].slice(-STORE_MAX)),
    );
  } catch {
    // No storage: read again next time.
  }
}

/** A small copy of the picture, where the store can make one: the colour is
 * read from 64 pixels, not from a 1920 px hero. */
function sampleUrl(url: string): string {
  try {
    const u = new URL(url, window.location.href);
    if (u.hostname === "store-images.s-microsoft.com")
      u.searchParams.set("w", "64");
    return u.toString();
  } catch {
    return url;
  }
}

/** What a picture's colours are, for a scheme: its hue and how vivid it is
 * (0–1). */
type Art = { h: number; v: number };

/** The picture's dominant colour, not the average of all of them: the
 * average of a pumpkin on a blue night is neither. Pixels vote by how
 * colourful they are into 15° bins; the busiest bin with its neighbours wins,
 * and its own pixels give the exact hue and how vivid it is. Null when the
 * store does not allow reading it. */
function readArt(url: string): Promise<Art | null> {
  return new Promise((resolve) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.decoding = "async";
    img.onload = () => {
      try {
        const size = 32;
        const canvas = document.createElement("canvas");
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext("2d", { willReadFrequently: true });
        if (!ctx) return resolve(null);
        ctx.drawImage(img, 0, 0, size, size);
        const px = ctx.getImageData(0, 0, size, size).data;
        const BINS = 24;
        const votes = new Array<number>(BINS).fill(0);
        const hues: Array<[number, number]> = [];
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
          const deg = (h * 60 + 360) % 360;
          votes[Math.floor(deg / (360 / BINS)) % BINS] += chroma;
          hues.push([deg, chroma]);
        }
        let best = 0;
        let bestVotes = -1;
        for (let k = 0; k < BINS; k++) {
          const sum =
            votes[(k + BINS - 1) % BINS] + votes[k] + votes[(k + 1) % BINS];
          if (sum > bestVotes) {
            bestVotes = sum;
            best = k;
          }
        }
        if (bestVotes < 3) return resolve(null);
        const centre = (best + 0.5) * (360 / BINS);
        let x = 0;
        let y = 0;
        let weight = 0;
        let count = 0;
        for (const [deg, chroma] of hues) {
          const off = Math.abs(((deg - centre + 540) % 360) - 180);
          if (off > (360 / BINS) * 1.5) continue;
          const rad = (deg * Math.PI) / 180;
          x += Math.cos(rad) * chroma;
          y += Math.sin(rad) * chroma;
          weight += chroma;
          count++;
        }
        resolve({
          h: ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360,
          v: Math.min(1, weight / count),
        });
      } catch {
        resolve(null);
      }
    };
    img.onerror = () => resolve(null);
    img.src = sampleUrl(url);
  });
}

/** A whole tonal scheme from the picture's colour, muted: the containers
 * coloured as much as the picture is vivid (a grey one stays nearly grey, a
 * bright one clearly its colour), the accent a clear tone of it. */
function scheme({ h, v }: Art, light: boolean, bright = false): CSSProperties {
  const k = Math.min(1.8, Math.max(0.7, 0.6 + v * 1.8));
  const hsl = (s: number, l: number) =>
    `hsl(${Math.round(h)} ${Math.min(100, Math.round(s * k))}% ${l}%)`;
  // The containers in the picture's own colour (the month card, the season
  // pass): kept as dark as the page, an orange or a yellow is only ever brown,
  // so they sit halfway, with light text. The page itself stays muted.
  const own = !bright
    ? {}
    : light
      ? {
          "--primary-container": hsl(45, 80),
          "--primary-container-2": hsl(49, 74),
          "--on-primary-container": hsl(60, 12),
          "--on-primary-container-2": hsl(50, 24),
          "--surface-1": hsl(60, 90),
          "--surface-2": hsl(54, 86),
          "--surface-3": hsl(48, 83),
          "--secondary-container": hsl(44, 84),
          "--on-secondary-container": hsl(55, 18),
        }
      : {
          "--primary-container": hsl(42, 36),
          "--primary-container-2": hsl(44, 42),
          "--on-primary-container": hsl(90, 95),
          "--on-primary-container-2": hsl(70, 86),
          "--surface-1": hsl(28, 15),
          "--surface-2": hsl(32, 20),
          "--surface-3": hsl(36, 25),
          "--secondary-container": hsl(40, 30),
          "--on-secondary-container": hsl(85, 92),
        };
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
  return { ...vars, ...own } as CSSProperties;
}

/** Which picture a game's page took its colours from, by the catalog's game
 * (`g<game_id>`, what every payload carries), its lists and its name: the pages inside a game (its achievements, one
 * achievement, its gallery, a post of its) take the same colours. */
const gameArt = new Map<string, string>();

export function rememberGameArt(
  keys: Array<string | null | undefined>,
  url: string | null | undefined,
): void {
  if (!url) return;
  for (const k of keys) if (k) gameArt.set(k, url);
}

export function gameArtOf(
  ...keys: Array<string | null | undefined>
): string | undefined {
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
export function useArtTheme(
  url: string | null | undefined,
  bright = false,
): {
  style: CSSProperties | undefined;
  settled: boolean;
} {
  const [hue, setHue] = useState<Art | null>(() =>
    url ? (cache.get(url) ?? null) : null,
  );
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
    void readArt(url).then((h) => {
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
    style:
      hue === null
        ? undefined
        : scheme(
            hue,
            document.documentElement.dataset.theme === "light",
            bright,
          ),
    settled,
  };
}
