import { t, type Locale } from "../../../i18n";
import { Sheet } from "../../shared/lib";
import { formatMonth } from "../utils";

export function MonthSheet({
  months,
  selected,
  liveMonth,
  locale,
  onClose,
  onPick,
}: {
  months: string[];
  selected: string;
  liveMonth: string;
  locale: Locale;
  onClose: () => void;
  onPick: (ym: string) => void;
}) {
  return (
    <Sheet onClose={onClose} closeLabel={t(locale, "close")} noClose mid>
      <div className="sheet-content score-sheet picker-sheet">
        <h2>{t(locale, "pickMonth")}</h2>
        <div className="picker-list">
          {months.map((ym) => (
            <button
              key={ym}
              type="button"
              className={ym === selected ? "picker-row is-on" : "picker-row"}
              onClick={() => onPick(ym)}
            >
              <strong>{formatMonth(ym, locale, "sheet")}</strong>
              {(ym === liveMonth) && <span>{t(locale, "nowMonth")}</span>}
            </button>
          ))}
        </div>
      </div>
    </Sheet>
  );
}
