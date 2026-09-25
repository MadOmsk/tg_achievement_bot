import { useCallback, useEffect, useState } from "react";

/**
 * Pictures appear all at once, faded in, once they are fully loaded — not
 * painted row by row from the top while they download. Spread the result on
 * the <img>; a picture that is already in the cache shows straight away.
 */
export function useImgFade(src: string | null | undefined) {
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    setLoaded(false);
  }, [src]);

  const ref = useCallback((node: HTMLImageElement | null) => {
    if (node && node.complete && node.naturalWidth > 0) setLoaded(true);
  }, []);

  return {
    ref,
    onLoad: () => setLoaded(true),
    className: loaded ? "img-fade is-loaded" : "img-fade",
  };
}
