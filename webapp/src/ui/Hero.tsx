import type { ReactNode } from "react";

/** The head of a page about one thing — a post, an achievement: its picture
 * under the see-through bar, on a blurred ground of itself. */
export function Hero({
  ground,
  children,
  onOpen,
  full = false,
}: {
  ground: string | null | undefined;
  children: ReactNode;
  onOpen?: () => void;
  /** The picture runs edge to edge under the bar, as a game's art does. */
  full?: boolean;
}) {
  return (
    <div className={`hero${full ? " hero-full" : ""}`}>
      {ground && <img src={ground} alt="" className="hero-ground" aria-hidden="true" />}
      {onOpen ? (
        <button type="button" className="hero-stage" onClick={onOpen}>
          {children}
        </button>
      ) : (
        <div className="hero-stage hero-stage-still">{children}</div>
      )}
    </div>
  );
}
