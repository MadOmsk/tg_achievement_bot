import { useCallback, useEffect, useState, type CSSProperties } from "react";
import { CoverMark } from "../cover-img/CoverImg";
import { useImgFade } from "../img-fade/useImgFade";
import { isSmallPicture, pictureLook } from "./pictureLook";
import "./FitImg.css";

/**
 * The picture itself, un-stretched, on top of a card's stretched backdrop.
 *
 * `height` (the default) shows the whole picture top to bottom and crops
 * whatever does not fit sideways; `width` does the opposite — the full width
 * first, the vertical overflow is what gets cropped (HowLongToBeat's covers
 * are portrait, so height-first would leave them a thin strip); `contain` shows
 * all of it, whichever way it is longer; `cover` fills the frame both ways.
 *
 * An achievement's picture that is small (a 64 px icon) is none of those: it
 * is enlarged a few times and set in the middle of the block, rounded and
 * shadowed, and the ground behind it — the card's own blurred copy — shows
 * around it (`pictureLook`: the same rule the Telegram posts follow).
 */
export function FitImg({
  src,
  mode = "height",
  kind = "achievement",
  top = false,
}: {
  src?: string | null;
  mode?: "height" | "width" | "contain" | "cover";
  /** Which glyph stands in, centred in the block, when there is no picture. */
  kind?: "game" | "achievement";
  /** `contain`: a picture wider than the block sits at its top, not its middle. */
  top?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  // The picture's own size, once it is known: what decides "small".
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const url = (src ?? "").trim();
  const fade = useImgFade(url);

  useEffect(() => {
    setFailed(false);
    setSize(null);
  }, [url]);

  const measure = useCallback(
    (node: HTMLImageElement | null) => {
      fade.ref(node);
      if (node && node.complete && node.naturalWidth > 0) {
        setSize((cur) =>
          cur && cur.w === node.naturalWidth && cur.h === node.naturalHeight
            ? cur
            : { w: node.naturalWidth, h: node.naturalHeight },
        );
      }
    },
    // `fade.ref` follows the url.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [fade.ref],
  );
  const small = kind === "achievement" && size != null && isSmallPicture(size.w, size.h);
  const smallStyle = small
    ? ({
        "--fit-nat": Math.max(size.w, size.h),
        "--fit-scale": pictureLook().scale,
      } as CSSProperties)
    : undefined;

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
    <span
      className={`fit-layer is-${mode}${top ? " is-top" : ""}${small ? " is-small" : ""}`}
      style={smallStyle}
      aria-hidden
    >
      <img
        ref={measure}
        src={url}
        alt=""
        className={fade.className}
        draggable={false}
        loading="eager"
        onLoad={(e) => {
          fade.onLoad();
          const img = e.currentTarget;
          setSize({ w: img.naturalWidth, h: img.naturalHeight });
        }}
        onError={() => setFailed(true)}
      />
      {/* The glyph stands in, centred, until the picture is actually there —
       * not just a blank layer while it downloads. */}
      {!fade.loaded && (
        <span className="cover-ph-mark">
          <CoverMark kind={kind} size={96} />
        </span>
      )}
    </span>
  );
}
