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
