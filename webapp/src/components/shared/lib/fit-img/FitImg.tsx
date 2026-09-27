import { useEffect, useState } from "react";
import { CoverMark } from "../cover-img/CoverImg";
import { useImgFade } from "../img-fade/useImgFade";
import "./FitImg.css";

/**
 * The picture itself, un-stretched, on top of a card's stretched backdrop.
 *
 * `height` (the default) shows the whole picture top to bottom and crops
 * whatever does not fit sideways; `width` does the opposite — the full width
 * first, the vertical overflow is what gets cropped (HowLongToBeat's covers
 * are portrait, so height-first would leave them a thin strip).
 */
export function FitImg({
  src,
  mode = "height",
  kind = "achievement",
}: {
  src?: string | null;
  mode?: "height" | "width";
  /** Which glyph stands in, centred in the block, when there is no picture. */
  kind?: "game" | "achievement";
}) {
  const [failed, setFailed] = useState(false);
  const url = (src ?? "").trim();
  const fade = useImgFade(url);

  useEffect(() => {
    setFailed(false);
  }, [url]);

  if (!url || failed) {
    return (
      <span className="fit-layer is-empty" aria-hidden>
        <span className="cover-ph-mark">
          <CoverMark kind={kind} size={96} />
        </span>
      </span>
    );
  }
  return (
    <span className={`fit-layer is-${mode}`} aria-hidden>
      <img
        ref={fade.ref}
        src={url}
        alt=""
        className={fade.className}
        draggable={false}
        loading="eager"
        onLoad={fade.onLoad}
        onError={() => setFailed(true)}
      />
    </span>
  );
}
