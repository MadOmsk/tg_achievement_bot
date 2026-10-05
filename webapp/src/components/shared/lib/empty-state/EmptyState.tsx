import "./EmptyState.css";
import { Icon } from "../icon/Icon";

/** What a list shows while it has nothing to show: said kindly, with a way on. */
export function EmptyState({
  title,
  hint,
  action,
  slide = false,
  icon = "cup",
}: {
  title: string;
  hint?: string;
  action?: { label: string; onClick: () => void };
  slide?: boolean;
  icon?: "cup" | "lock";
}) {
  return (
    <div className={slide ? "empty-state is-slide" : "empty-state"}>
      <span className="empty-state-mark" aria-hidden>
        <Icon name={icon} size={slide ? 52 : 28} />
      </span>
      <p className="empty-state-title">{title}</p>
      {hint && <p className="empty-state-hint">{hint}</p>}
      {action && (
        <button type="button" className="empty-state-action" onClick={action.onClick}>
          {action.label}
          <Icon name="forward" size={16} />
        </button>
      )}
    </div>
  );
}
