import type { ReactNode } from "react";
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
          <svg width={big ? 16 : 13} height={big ? 16 : 13} viewBox="0 0 24 24" aria-hidden>
            <path
              d="M12 21s-7.5-4.6-9.6-9.2C.9 8.4 3 4.5 6.8 4.5c2.2 0 3.7 1.2 5.2 3 1.5-1.8 3-3 5.2-3 3.8 0 5.9 3.9 4.4 7.3C19.5 16.4 12 21 12 21z"
              fill="currentColor"
            />
          </svg>
        </span>
      )}
    </span>
  );
}
