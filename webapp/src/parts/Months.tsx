import { useState } from "react";
import { useApp } from "../app/context";
import { formatMonth } from "../core/people-utils";
import { Segmented } from "../ui/Controls";
import { Icon } from "../ui/Icon";
import { Sheet } from "../ui/Page";

/** The months a list has, newest first: the three latest as a connected
 * group, the rest a tap away in a sheet. */
export function MonthSwitch({
  months,
  value,
  onChange,
}: {
  months: string[];
  value: string;
  onChange: (month: string) => void;
}) {
  const { locale, tr } = useApp();
  const [all, setAll] = useState(false);
  const list = months.length ? months : [value];
  const latest = list.slice(0, 3);
  const shown = (latest.includes(value) ? latest : [value, ...latest.slice(0, 2)]).sort();
  return (
    <div className="months">
      {list.length > 3 && (
        <button type="button" className="months-more" aria-label={tr("pickMonth")} onClick={() => setAll(true)}>
          <Icon name="calendar" size={20} />
        </button>
      )}
      <Segmented
        options={shown.map((m) => ({ value: m, label: capital(formatMonth(m, locale, "chip")) }))}
        value={value}
        onChange={onChange}
      />
      {all && (
        <Sheet title={tr("pickMonth")} onClose={() => setAll(false)} layer="months">
          <div className="months-grid">
            {list.map((m) => (
              <button
                key={m}
                type="button"
                className={m === value ? "months-on" : ""}
                onClick={() => {
                  setAll(false);
                  onChange(m);
                }}
              >
                {capital(formatMonth(m, locale, "sheet"))}
              </button>
            ))}
          </div>
        </Sheet>
      )}
    </div>
  );
}

/** A split button for a screen's month: the month's name, and an arrow that
 * opens every month the list has. */
export function MonthButton({
  months,
  value,
  onChange,
}: {
  months: string[];
  value: string;
  onChange: (month: string) => void;
}) {
  const { locale, tr } = useApp();
  const [all, setAll] = useState(false);
  const list = months.length ? months : [value];
  return (
    <>
      <div className="split">
        <button type="button" onClick={() => setAll(true)}>
          {capital(formatMonth(value, locale, "chip"))}
        </button>
        <button type="button" aria-label={tr("pickMonth")} onClick={() => setAll(true)}>
          <Icon name="down" size={18} />
        </button>
      </div>
      {all && <MonthSheet months={list} value={value} onChange={onChange} onClose={() => setAll(false)} />}
    </>
  );
}

/** Every month a list has, in a sheet: what the month button opens. */
export function MonthSheet({
  months,
  value,
  onChange,
  onClose,
}: {
  months: string[];
  value: string;
  onChange: (month: string) => void;
  onClose: () => void;
}) {
  const { locale, tr } = useApp();
  return (
    <Sheet title={tr("pickMonth")} onClose={onClose} layer="months">
      <div className="months-grid">
        {months.map((m) => (
          <button
            key={m}
            type="button"
            className={m === value ? "months-on" : ""}
            onClick={() => {
              onClose();
              onChange(m);
            }}
          >
            {capital(formatMonth(m, locale, "sheet"))}
          </button>
        ))}
      </div>
    </Sheet>
  );
}

/** The last `n` months, this one first, for a screen whose answer lists none. */
export function recentMonths(n: number, from = new Date()): string[] {
  const out: string[] = [];
  for (let i = 0; i < n; i += 1) {
    const d = new Date(from.getFullYear(), from.getMonth() - i, 1);
    out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }
  return out;
}

export function capital(text: string): string {
  return text ? text[0].toUpperCase() + text.slice(1) : text;
}

/** The month's name as a title takes it: «октября» in Russian, «October» in English. */
export function monthName(month: string, locale: string): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1, 1);
  if (locale === "en") return d.toLocaleDateString("en-GB", { month: "long" });
  return d.toLocaleDateString("ru-RU", { day: "numeric", month: "long" }).replace(/^\d+\s*/, "");
}

