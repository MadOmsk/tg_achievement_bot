import { useState, type CSSProperties } from "react";
import { useApp } from "../app/context";
import { Icon, type IconName } from "./Icon";

/** An achievement's picture filling its block — unless it is small (under the
 * admin's limit, `me.picture`): then it is not stretched but enlarged `scale`
 * times against a 1024 px card and set in the middle of a ground made of
 * itself, blurred (the posts' own rule). */
export function AchPic({
  src,
  className = "",
  style,
  veiled = false,
}: {
  src: string | null | undefined;
  className?: string;
  style?: CSSProperties;
  veiled?: boolean;
}) {
  const { picture } = useApp();
  const [natural, setNatural] = useState<number | null>(null);
  const [failed, setFailed] = useState(false);
  if (!src || failed) {
    return (
      <span className={`pic pic-empty ${className}`} style={style}>
        <Icon name="trophy" size={22} />
      </span>
    );
  }
  const small = picture.on && natural !== null && natural < picture.lowRes;
  const share = small ? Math.min(0.9, (natural * picture.scale) / 1024) : 1;
  return (
    <span className={`pic ${small ? "pic-small" : ""} ${className}`} style={style}>
      {small && <img className="pic-ground" src={src} alt="" aria-hidden="true" />}
      <img
        className="pic-img"
        src={src}
        alt=""
        loading="lazy"
        decoding="async"
        style={small ? ({ "--share": share } as CSSProperties) : undefined}
        onLoad={(e) => setNatural(Math.max(e.currentTarget.naturalWidth, e.currentTarget.naturalHeight))}
        onError={() => setFailed(true)}
      />
      {veiled && (
        <span className="pic-veil">
          <Icon name="lock" size={20} />
        </span>
      )}
    </span>
  );
}

/** A game's picture — never enlarged on a ground, whatever its size. */
export function Cover({
  src,
  className = "",
  style,
  fallback = "gamepad",
  alt = "",
}: {
  src: string | null | undefined;
  className?: string;
  style?: CSSProperties;
  fallback?: IconName;
  alt?: string;
}) {
  const [failed, setFailed] = useState(false);
  return (
    <span className={`cover ${className}`} style={style}>
      {src && !failed ? (
        <img src={src} alt={alt} loading="lazy" decoding="async" onError={() => setFailed(true)} />
      ) : (
        <Icon name={fallback} size={22} />
      )}
    </span>
  );
}
