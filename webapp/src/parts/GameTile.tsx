import type { ReactNode } from "react";
import { tick } from "../core/haptic";
import { Cover } from "../ui/Pic";

/** One game in a rail, the same card everywhere — the month's games, the
 * favorites, what is trending: the cover with a mark in its corner (done, a
 * heart), the name, and what the rail says of it under the name. */
export function GameTile({
  cover,
  name,
  mark,
  done = false,
  onOpen,
  children,
}: {
  cover: string | null | undefined;
  name: string;
  mark?: ReactNode;
  done?: boolean;
  onOpen: () => void;
  children?: ReactNode;
}) {
  return (
    <button
      type="button"
      className={`game-tile${done ? " game-tile-done" : ""}`}
      onClick={() => {
        tick();
        onOpen();
      }}
    >
      <span className="game-tile-art">
        <Cover src={cover} className="game-tile-cover" alt={name} />
        {mark}
      </span>
      <span className="game-tile-name clamp-1">{name}</span>
      {children}
    </button>
  );
}
