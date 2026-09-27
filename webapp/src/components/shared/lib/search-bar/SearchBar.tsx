import { t, type Locale } from "../../../../i18n";
import { Icon } from "../icon/Icon";
import "./SearchBar.css";

export function SearchBar({
  locale,
  value,
  onChange,
}: {
  locale: Locale;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="search-bar">
      <Icon name="search" size={18} />
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={t(locale, "searchHint")}
        enterKeyHint="search"
        autoComplete="off"
      />
      {value && (
        <button
          type="button"
          className="search-clear"
          onClick={() => onChange("")}
          aria-label={t(locale, "close")}
        >
          ✕
        </button>
      )}
    </label>
  );
}
