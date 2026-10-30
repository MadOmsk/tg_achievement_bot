import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, Ref } from "react";
import { tick } from "../core/haptic";
import { GoMark } from "./GoMark";
import { Icon, type IconName } from "./Icon";

type Variant = "filled" | "tonal" | "text" | "danger";

export function Button({
  variant = "filled",
  icon,
  wide = false,
  busy = false,
  children,
  className = "",
  onClick,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  icon?: IconName;
  wide?: boolean;
  busy?: boolean;
}) {
  return (
    <button
      type="button"
      {...rest}
      className={`btn btn-${variant}${wide ? " btn-wide" : ""}${busy ? " btn-busy" : ""} ${className}`}
      disabled={busy || rest.disabled}
      onClick={(e) => {
        tick();
        onClick?.(e);
      }}
    >
      {icon && <Icon name={icon} size={20} />}
      {children}
    </button>
  );
}

/** A round icon button; `square` is the morphed, selected form. */
export function IconButton({
  icon,
  label,
  variant = "tonal",
  square = false,
  badge,
  filled = false,
  className = "",
  onClick,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  icon: IconName;
  label: string;
  variant?: "tonal" | "plain" | "glass";
  square?: boolean;
  badge?: number | null;
  filled?: boolean;
}) {
  return (
    <button
      type="button"
      {...rest}
      aria-label={label}
      title={label}
      className={`ibtn ibtn-${variant}${square ? " ibtn-square" : ""} ${className}`}
      onClick={(e) => {
        tick();
        onClick?.(e);
      }}
    >
      <Icon name={icon} filled={filled} />
      {badge ? <span className="ibtn-badge">{badge > 99 ? "99+" : badge}</span> : null}
    </button>
  );
}

export function Chip({
  children,
  tone = "outline",
  icon,
  onClick,
  className = "",
}: {
  children: ReactNode;
  tone?: "outline" | "tonal" | "primary" | "tertiary" | "secondary";
  icon?: IconName;
  onClick?: () => void;
  className?: string;
}) {
  const body = (
    <>
      {icon && <Icon name={icon} size={16} />}
      {children}
    </>
  );
  return onClick ? (
    <button type="button" className={`chip chip-${tone} ${className}`} onClick={onClick}>
      {body}
    </button>
  ) : (
    <span className={`chip chip-${tone} ${className}`}>{body}</span>
  );
}

/** A connected button group: one choice, the chosen one rounder and checked. */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  onRepeat,
  className = "",
}: {
  options: Array<{ value: T; label: string; more?: boolean }>;
  value: T;
  onChange: (value: T) => void;
  /** A tap on the segment already chosen: one marked `more` opens its own
   * choices (a month, a year). */
  onRepeat?: (value: T) => void;
  className?: string;
}) {
  return (
    <div className={`seg ${className}`} role="radiogroup">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          className={o.value === value ? "seg-on" : ""}
          onClick={() => {
            tick();
            if (o.value !== value) onChange(o.value);
            else if (o.more) onRepeat?.(o.value);
          }}
        >
          {o.value === value && !o.more && <Icon name="check" size={16} />}
          <span className="clamp-1">{o.label}</span>
          {o.more && <Icon name="down" size={16} />}
        </button>
      ))}
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (on: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      className={`toggle${checked ? " toggle-on" : ""}`}
      onClick={(e) => {
        e.stopPropagation();
        tick();
        onChange(!checked);
      }}
    >
      <span className="toggle-thumb">{checked && <Icon name="check" size={14} />}</span>
    </button>
  );
}

export function Field({
  label,
  hint,
  error,
  icon,
  inputRef,
  trail,
  className = "",
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
  hint?: string | null;
  error?: string | null;
  icon?: IconName;
  inputRef?: Ref<HTMLInputElement>;
  /** A button at the field's end, inside it. */
  trail?: ReactNode;
}) {
  return (
    <label className={`field${error ? " field-error" : ""} ${className}`}>
      {label && <span className="field-label">{label}</span>}
      <span className="field-box">
        {icon && <Icon name={icon} size={20} />}
        <input ref={inputRef} {...rest} />
        {trail}
      </span>
      {(error || hint) && <span className="field-hint">{error || hint}</span>}
    </label>
  );
}

/** A list whose rows are separate pebbles: round at the group's ends, nearly
 * square between. */
export function Group({ children, title, action, className = "" }: {
  children: ReactNode;
  title?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`group ${className}`}>
      {title && (
        <div className="group-head">
          <h2 className="t-title">{title}</h2>
          {action}
        </div>
      )}
      <div className="group-items">{children}</div>
    </section>
  );
}

export function Row({
  lead,
  title,
  sub,
  trail,
  onClick,
  chevron = false,
  danger = false,
  className = "",
}: {
  lead?: ReactNode;
  title: ReactNode;
  sub?: ReactNode;
  trail?: ReactNode;
  onClick?: () => void;
  chevron?: boolean;
  danger?: boolean;
  className?: string;
}) {
  const body = (
    <>
      {lead && <span className="row-lead">{lead}</span>}
      <span className="row-text">
        <span className={`row-title${danger ? " row-danger" : ""}`}>{title}</span>
        {sub && <span className="row-sub">{sub}</span>}
      </span>
      {trail && <span className="row-trail">{trail}</span>}
      {chevron && <GoMark />}
    </>
  );
  return onClick ? (
    <button
      type="button"
      className={`row row-tap ${className}`}
      onClick={() => {
        tick();
        onClick();
      }}
    >
      {body}
    </button>
  ) : (
    <div className={`row ${className}`}>{body}</div>
  );
}

export function Section({ title, action, children, className = "" }: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`sec ${className}`}>
      <div className="sec-head">
        <h2 className="t-title">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export function Empty({ icon = "sparkle", title, text, action }: {
  icon?: IconName;
  title: string;
  text?: string | null;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-mark shape-puffy">
        <Icon name={icon} size={28} />
      </span>
      <p className="t-label">{title}</p>
      {text && <p className="t-body">{text}</p>}
      {action}
    </div>
  );
}

export function Spinner({ size = 28 }: { size?: number }) {
  return <span className="spinner shape-cookie9" style={{ width: size, height: size }} aria-hidden="true" />;
}
