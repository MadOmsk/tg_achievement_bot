import { t, type Locale } from "../../../../i18n";
import { Sheet } from "../sheet/Sheet";
import "./DayPicker.css";


/** The `Y-M-D` key (no zero padding) the feed groups its days by. */
export function pickerKey(year: number, month: number, day: number): string {
  return `${year}-${month + 1}-${day}`;
}

/**
 * The month of a tapped day, as a calendar for jumping to a day: only days
 * that have something are enabled (with how many). The month and year are
 * the sheet's title.
 */
export function DayPicker({
  locale,
  days,
  start,
  onPick,
  onClose,
}: {
  locale: Locale;
  /** day key -> how many entries fall on it */
  days: Map<string, number>;
  /** a date inside the month to show */
  start: Date;
  onPick: (key: string) => void;
  onClose: () => void;
}) {
  // One month, the one the tapped day belongs to.
  const cursor = new Date(start.getFullYear(), start.getMonth(), 1);
  const intl = locale === "en" ? "en-GB" : "ru-RU";

  const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
  const length = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0).getDate();
  // Monday first: getDay() is 0 for Sunday.
  const lead = (first.getDay() + 6) % 7;
  const weekdays = Array.from({ length: 7 }, (_, i) =>
    new Date(2024, 0, 1 + i).toLocaleDateString(intl, { weekday: "short" }),
  );
  const today = new Date();
  const todayKey = pickerKey(today.getFullYear(), today.getMonth(), today.getDate());

  return (
    <Sheet mid onClose={onClose} closeLabel={t(locale, "close")} noClose>
      <div className="sheet-content score-sheet picker-sheet day-picker">
        <h2 className="day-picker-title">
          {first.toLocaleDateString(intl, { month: "long", year: "numeric" })}
        </h2>
        <div className="day-picker-grid">
          {weekdays.map((name) => (
            <span key={name} className="day-picker-week">
              {name}
            </span>
          ))}
          {Array.from({ length: lead }, (_, i) => (
            <span key={`gap-${i}`} />
          ))}
          {Array.from({ length: length }, (_, i) => {
            const key = pickerKey(cursor.getFullYear(), cursor.getMonth(), i + 1);
            const count = days.get(key) ?? 0;
            return (
              <button
                key={key}
                type="button"
                disabled={count === 0}
                className={[
                  "day-picker-day",
                  key === todayKey ? "is-today" : "",
                  count > 0 ? "has-items" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                onClick={() => onPick(key)}
              >
                <span>{i + 1}</span>
                {count > 0 && <small>{count}</small>}
              </button>
            );
          })}
        </div>
      </div>
    </Sheet>
  );
}

