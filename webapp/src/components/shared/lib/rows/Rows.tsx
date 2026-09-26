import type { ReactNode } from "react";
import { Icon } from "../icon/Icon";
import "./Rows.css";

/** The arrow at the end of a tappable row — one drawing for every list. */
export function Chevron() {
  return (
    <span className="rows-chevron" aria-hidden>
      <Icon name="forward" size={16} />
    </span>
  );
}

/** A titled group of plain rows — no frame, hairlines between the rows. */
export function RowsSection({
  title,
  action,
  className,
  children,
}: {
  title?: ReactNode;
  action?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={className ? `rows-section ${className}` : "rows-section"}>
      {(title || action) && (
        <div className="rows-head">
          <h3 className="rows-title">{title}</h3>
          {action}
        </div>
      )}
      <div className="rows">{children}</div>
    </section>
  );
}

/**
 * One line of a list: something on the left, a title (and a smaller line
 * under it), something on the right. A row with `onClick` is a button and
 * shows a chevron unless `chevron={false}`.
 */
export function Row({
  lead,
  title,
  subtitle,
  trailing,
  chevron = true,
  onClick,
  className,
}: {
  lead?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  trailing?: ReactNode;
  chevron?: boolean;
  onClick?: () => void;
  className?: string;
}) {
  const body = (
    <>
      {lead && <span className="rows-lead">{lead}</span>}
      <span className="rows-copy">
        <strong>{title}</strong>
        {subtitle && <p>{subtitle}</p>}
      </span>
      {trailing != null && trailing !== false && trailing !== "" && (
        <span className="rows-trail">{trailing}</span>
      )}
      {onClick && chevron && <Chevron />}
    </>
  );
  const cls = className ? `rows-row ${className}` : "rows-row";
  return onClick ? (
    <button type="button" className={cls} onClick={onClick}>
      {body}
    </button>
  ) : (
    <div className={cls}>{body}</div>
  );
}
