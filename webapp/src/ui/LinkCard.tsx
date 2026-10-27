import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";

/** A way to somewhere else — a game a post belongs to, a guide video: its
 * picture, what it is and a line under it, and a round mark of where it goes
 * (forward, play). One shape for every such link. */
export function LinkCard({
  media,
  title,
  sub,
  go = "forward",
  onOpen,
  wide = false,
}: {
  media: ReactNode;
  title: ReactNode;
  sub?: ReactNode;
  go?: IconName;
  onOpen?: () => void;
  /** A 16:9 picture (a video) instead of a square one. */
  wide?: boolean;
}) {
  return (
    <button type="button" className={`link-card${wide ? " link-card-wide" : ""}`} disabled={!onOpen} onClick={onOpen}>
      <span className="link-card-media">{media}</span>
      <span className="link-card-text">
        <span className="link-card-title clamp-2">{title}</span>
        {sub && <span className="link-card-sub clamp-1">{sub}</span>}
      </span>
      {onOpen && (
        <span className="link-card-go shape-cookie9">
          <Icon name={go} size={20} />
        </span>
      )}
    </button>
  );
}
