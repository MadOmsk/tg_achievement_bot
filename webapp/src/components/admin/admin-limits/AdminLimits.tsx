import { useEffect, useState } from "react";
import {
  fetchAdminLimits,
  patchAdminLimit,
  type AdminLimit,
} from "../../../api";
import { t, type Locale } from "../../../i18n";
import { BackHead, GlassWait } from "../../shared/lib";

export function AdminLimits({
  data,
  locale,
  onBack,
  onFail,
}: {
  data: string;
  locale: Locale;
  onBack: () => void;
  onFail: (err: unknown) => void;
}) {
  const [limits, setLimits] = useState<AdminLimit[] | null>(null);

  useEffect(() => {
    void fetchAdminLimits(data)
      .then((r) => setLimits(r.items))
      .catch(onFail);
  }, [data, onFail]);

  return (
    <>
      <BackHead
        title={t(locale, "adminLimits")}
        backLabel={t(locale, "back")}
        onBack={onBack}
      />
      {limits == null ? (
        <GlassWait />
      ) : (
        <div className="glass-card admin-limits">
          {limits.map((item) => {
            const hint =
              item.zero_means === "unlimited"
                ? t(locale, "limitZeroUnlimited")
                : (item.zero_means === "off") && t(locale, "limitZeroOff");
            return (
              <label key={item.key} className="ios-row admin-limit-row">
                <span className="admin-limit-copy">
                  <strong>{item.label}</strong>
                  {hint && <small>{hint}</small>}
                </span>
                <input
                  className="admin-limit-input"
                  type="number"
                  defaultValue={String(item.value)}
                  min={item.min}
                  max={item.max}
                  inputMode="numeric"
                  key={`${item.key}:${item.value}`}
                  onBlur={(e) => {
                    const n = Number(e.target.value);
                    if (Number.isNaN(n) || n === item.value) return;
                    const clamped = Math.min(
                      item.max,
                      Math.max(item.min, Math.trunc(n)),
                    );
                    void patchAdminLimit(data, item.key, clamped)
                      .then((r) => setLimits(r.items))
                      .catch(onFail);
                  }}
                />
              </label>
            );
          })}
        </div>
      )}
    </>
  );
}
