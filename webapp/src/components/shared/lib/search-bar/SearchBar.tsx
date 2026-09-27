import { useEffect, useRef } from "react";
import { t, type Locale } from "../../../../i18n";
import { Icon } from "../icon/Icon";
import "./SearchBar.css";

export function SearchBar({
  locale,
  value,
  onChange,
  focusKey,
  onClose,
}: {
  locale: Locale;
  value: string;
  onChange: (value: string) => void;
  /** Focuses the field whenever this turns true — imperatively, since the
   * field can stay mounted (just hidden) while closed, and the "autofocus"
   * HTML attribute only ever fires once, on mount. */
  focusKey?: boolean;
  /** The field replaced the rest of the header to appear: its own "✕" is the
   * only way back, so it shows even with nothing typed, and closes instead
   * of just clearing. Omit it where the field sits beside other content. */
  onClose?: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (focusKey) inputRef.current?.focus();
  }, [focusKey]);

  return (
    <label className="search-bar">
      <Icon name="search" size={18} />
      <input
        ref={inputRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={t(locale, "searchHint")}
        enterKeyHint="search"
        autoComplete="off"
      />
      {(value || onClose) && (
        <button
          type="button"
          className="search-clear"
          onClick={() => (onClose ? onClose() : onChange(""))}
          aria-label={t(locale, "close")}
        >
          ✕
        </button>
      )}
    </label>
  );
}
