import { useEffect, useState } from "react";

/** A frame's proportions, width to height, are kept between a portrait 4:5
 * and a wide 1.91:1; a picture beyond that is shown whole over its blurred copy.
 * A feed post wider than a square puts its text under the picture, not over
 * it (`isWide`): the frame is the picture's own height. */
export const RATIO_MIN = 4 / 5;
export const RATIO_MAX = 1.91;
/** A feed post's frame is never wider than this (owner, 2026-10-05): a wide
 * picture keeps its whole height and gives up a little of its sides, rather
 * than making a thin strip of a post. */
export const FEED_RATIO_MAX = 1.3;

export function isWide(ratio: number): boolean {
  return ratio > 1.05;
}

const STORE_KEY = "img-ratios";
const STORE_MAX = 400;
const known = new Map<string, number>(load());

function load(): [string, number][] {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    return raw ? (JSON.parse(raw) as [string, number][]) : [];
  } catch {
    return [];
  }
}

function save(): void {
  try {
    // The latest ones: a feed is read newest first.
    localStorage.setItem(STORE_KEY, JSON.stringify([...known].slice(-STORE_MAX)));
  } catch {
    // No storage: the frame is measured again next time.
  }
}


/** The frame a picture wants: its own proportions, kept within reason, read
 * when it loads and remembered so the frame is right at once next time.
 * `fallback` until then. */
export function useImageRatio(
  src: string | null | undefined,
  { fallback = 1, max = RATIO_MAX }: { fallback?: number; max?: number } = {},
): number {
  const url = (src ?? "").trim();
  const [ratio, setRatio] = useState(() => known.get(url) ?? fallback);

  useEffect(() => {
    if (!url) {
      setRatio(fallback);
      return;
    }
    const cached = known.get(url);
    if (cached !== undefined) {
      setRatio(cached);
      return;
    }
    let cancelled = false;
    const img = new Image();
    img.onload = () => {
      if (cancelled || !img.naturalWidth || !img.naturalHeight) return;
      const next = img.naturalWidth / img.naturalHeight;
      known.set(url, next);
      save();
      setRatio(next);
    };
    img.src = url;
    return () => {
      cancelled = true;
    };
  }, [url, fallback]);

  return Math.min(max, Math.max(RATIO_MIN, ratio));
}
