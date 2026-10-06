import type { ReactNode } from "react";
import { Icon } from "../../shared/lib";
import "./FriendMark.css";

/** An avatar with a small mark at its lower left when the person is the
 * viewer's friend (following each other) — readable at a glance in a list. */
export function FriendMark({
  friend,
  label,
  big = false,
  children,
}: {
  friend: boolean;
  label: string;
  /** On a large face (Home's strip): the larger mark, as the presence mark grows. */
  big?: boolean;
  children: ReactNode;
}) {
  return (
    <span className="friend-mark-wrap">
      {children}
      {friend && (
        <span className="friend-mark" title={label} aria-label={label}>
          <Icon name="handshake" size={big ? 14 : 12} filled />
        </span>
      )}
    </span>
  );
}
