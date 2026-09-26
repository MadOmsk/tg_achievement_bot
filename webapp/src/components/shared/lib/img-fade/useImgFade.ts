import { useCallback, useEffect, useState } from "react";

// Pictures this session has already loaded once. A picture seen before is in
// the browser's cache: it must show at full strength on the very first frame,
// or every re-opened screen would fade its pictures in again — which read as
// a blink.
const seen = new Set<string>();

/**
 * Pictures appear all at once, faded in, once they are fully loaded — not
 * painted row by row from the top while they download. Spread the result on
 * the <img>. A picture already loaded before this session shows straight away.
 */
export function useImgFade(src: string | null | undefined) {
  const [loaded, setLoaded] = useState(() => Boolean(src && seen.has(src)));

  useEffect(() => {
    setLoaded(Boolean(src && seen.has(src)));
  }, [src]);

  const ref = useCallback(
    (node: HTMLImageElement | null) => {
      if (node && node.complete && node.naturalWidth > 0) {
        if (src) seen.add(src);
        setLoaded(true);
      }
    },
    [src],
  );

  return {
    ref,
    onLoad: () => {
      if (src) seen.add(src);
      setLoaded(true);
    },
    // Already-seen pictures skip the transition too.
    className: loaded ? "img-fade is-loaded" : "img-fade",
  };
}

/**
 * Loads pictures ahead of the screen that shows them, so it can appear with its
 * pictures already in place instead of drawing them in one by one. Gives up
 * after `ms`: a slow or broken picture never holds a screen back.
 */
export function preloadImages(urls: Array<string | null | undefined>, ms = 1500): Promise<void> {
  const wanted = [...new Set(urls.map((u) => (u ?? "").trim()).filter(Boolean))].filter(
    (u) => !seen.has(u),
  );
  if (wanted.length === 0) return Promise.resolve();
  return new Promise((resolve) => {
    let left = wanted.length;
    const done = () => {
      left -= 1;
      if (left <= 0) resolve();
    };
    const timer = window.setTimeout(resolve, ms);
    for (const url of wanted) {
      const img = new Image();
      img.onload = () => {
        seen.add(url);
        done();
      };
      img.onerror = done;
      img.src = url;
    }
    void timer;
  });
}
