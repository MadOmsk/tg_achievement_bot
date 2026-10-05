import type { ReactNode } from "react";
import { Chevron } from "../rows/Rows";
import { Dropdown, DropdownArrow } from "../dropdown/Dropdown";
import { Toggle } from "../toggle/Toggle";
import { Icon } from "../icon";
import "./FormRows.css";

/**
 * The one vocabulary of every settings and admin screen: a group of rows with an
 * optional title and hint, and a handful of row kinds. Screens compose these and
 * never style a row of their own, so every screen reads the same.
 */

export function Group({
  title,
  hint,
  aside,
  children,
}: {
  title?: string;
  hint?: ReactNode;
  /** A small action beside the title. */
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className={title || aside ? "fr-group" : "fr-group is-bare"}>
      {(title || aside) && (
        <div className="fr-head">
          {title && <p className="fr-title">{title}</p>}
          {aside}
        </div>
      )}
      <div className="fr-card">{children}</div>
      {hint && <p className="fr-hint">{hint}</p>}
    </section>
  );
}

function Label({ label, sub, lead }: { label: ReactNode; sub?: ReactNode; lead?: ReactNode }) {
  return (
    <>
      {lead && <span className="fr-lead">{lead}</span>}
      <span className="fr-label">
        <span className="fr-text">{label}</span>
        {sub && <small className="fr-sub">{sub}</small>}
      </span>
    </>
  );
}

/** A row's glyph: a list of rows that open screens reads as one when each
 * starts the same way. */
export function RowGlyph({ name }: { name: Parameters<typeof Icon>[0]["name"] }) {
  return (
    <span className="fr-glyph">
      <Icon name={name} size={26} />
    </span>
  );
}

/** Opens something: a screen, a picker, a link. */
export function NavRow({
  label,
  sub,
  lead,
  value,
  onClick,
  danger,
  disabled,
  className,
}: {
  label: ReactNode;
  sub?: ReactNode;
  lead?: ReactNode;
  value?: ReactNode;
  onClick: () => void;
  danger?: boolean;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <button
      type="button"
      className={["fr-row", danger ? "is-danger" : "", className ?? ""].filter(Boolean).join(" ")}
      onClick={onClick}
      disabled={disabled}
    >
      <Label label={label} sub={sub} lead={lead} />
      {value != null && value !== "" && <span className="fr-value">{value}</span>}
      {!danger && <Chevron />}
    </button>
  );
}

/** A plain fact, nothing to tap. */
export function InfoRow({
  label,
  sub,
  lead,
  value,
  children,
}: {
  label: ReactNode;
  sub?: ReactNode;
  lead?: ReactNode;
  value?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="fr-row is-static">
      <Label label={label} sub={sub} lead={lead} />
      {value != null && value !== "" && <span className="fr-value">{value}</span>}
      {children}
    </div>
  );
}

export function ToggleRow({
  label,
  sub,
  lead,
  on,
  onChange,
}: {
  label: ReactNode;
  sub?: ReactNode;
  lead?: ReactNode;
  on: boolean;
  onChange: (on: boolean) => void;
}) {
  return (
    <div className="fr-row is-static">
      <Label label={label} sub={sub} lead={lead} />
      <Toggle on={on} label={typeof label === "string" ? label : ""} onClick={() => onChange(!on)} />
    </div>
  );
}

/** Two or three short options, side by side. */
export function ChoiceRow<T extends string>({
  label,
  sub,
  value,
  options,
  onChange,
}: {
  label: ReactNode;
  sub?: ReactNode;
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
}) {
  return (
    <div className="fr-row is-static">
      <Label label={label} sub={sub} />
      <div className="segment" role="group">
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            className={o.value === value ? "is-on" : undefined}
            onClick={() => onChange(o.value)}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Many options: the value and a small arrow; the app's own dropdown opens. */
export function SelectRow<T extends string | number>({
  label,
  sub,
  value,
  options,
  onChange,
}: {
  label: ReactNode;
  sub?: ReactNode;
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
}) {
  const shown = options.find((o) => o.value === value)?.label ?? "";
  return (
    <Dropdown
      className="fr-row"
      value={value}
      options={options}
      onChange={onChange}
      label={typeof label === "string" ? label : undefined}
      trigger={
        <>
          <Label label={label} sub={sub} />
          <span className="fr-value">{shown}</span>
          <DropdownArrow />
        </>
      }
    />
  );
}

/** A number typed in place; saved when the field is left. */
export function NumberRow({
  label,
  sub,
  value,
  min,
  max,
  decimal,
  onChange,
}: {
  label: ReactNode;
  sub?: ReactNode;
  value: number;
  min?: number;
  max?: number;
  decimal?: boolean;
  onChange: (value: number) => void;
}) {
  return (
    <label className="fr-row">
      <Label label={label} sub={sub} />
      <input
        className="fr-number"
        defaultValue={String(value)}
        key={String(value)}
        inputMode={decimal ? "decimal" : "numeric"}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        }}
        onBlur={(e) => {
          let n = Number(e.target.value.replace(",", "."));
          if (Number.isNaN(n)) {
            e.target.value = String(value);
            return;
          }
          if (!decimal) n = Math.trunc(n);
          if (min != null) n = Math.max(min, n);
          if (max != null) n = Math.min(max, n);
          e.target.value = String(n);
          if (n !== value) onChange(n);
        }}
      />
    </label>
  );
}

/** One of a list of options, the chosen one ticked. */
export function CheckRow({
  label,
  sub,
  checked,
  onClick,
}: {
  label: ReactNode;
  sub?: ReactNode;
  checked: boolean;
  onClick: () => void;
}) {
  return (
    <button type="button" className="fr-row" onClick={onClick} aria-pressed={checked}>
      <Label label={label} sub={sub} />
      {checked && <span className="fr-check">✓</span>}
    </button>
  );
}

/** A small text action at the end of a row ("Подключить", "Разблокировать"). */
export function RowLink({
  children,
  onClick,
  danger,
}: {
  children: ReactNode;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button type="button" className={danger ? "fr-link is-danger" : "fr-link"} onClick={onClick}>
      {children}
    </button>
  );
}

/** What a settings screen shows while it loads: groups of plain rows. */
export function SettingsSkel({ groups = [3, 2] }: { groups?: number[] }) {
  return (
    <div aria-busy="true" aria-live="polite">
      {groups.map((rows, g) => (
        <section key={g} className="fr-group">
          <div className="fr-head">
            <span className="skel fr-skel-title" />
          </div>
          <div className="fr-card">
            {Array.from({ length: rows }, (_, i) => (
              <div key={i} className="fr-row is-static">
                <span className="skel fr-skel-label" style={{ width: `${46 - (i % 3) * 8}%` }} />
                <span className="skel fr-skel-value" />
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
