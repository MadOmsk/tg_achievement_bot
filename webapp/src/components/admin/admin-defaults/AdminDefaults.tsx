import { useEffect, useState } from "react";
import {
  fetchAdminDefaults,
  patchAdminDefaults,
  type AdminDefaults as AdminDefaultsType,
} from "../../../api";
import { rarityLabel, t, type Locale } from "../../../i18n";
import { BackHead, GlassWait, Toggle } from "../../shared/lib";
import { RARITY_MODES } from "../../shared/constants";

export function AdminDefaults({
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
  const [defaults, setDefaults] = useState<AdminDefaultsType | null>(null);

  useEffect(() => {
    void fetchAdminDefaults(data).then(setDefaults).catch(onFail);
  }, [data, onFail]);

  return (
    <>
      <BackHead
        title={t(locale, "adminDefaults")}
        backLabel={t(locale, "back")}
        onBack={onBack}
      />
      {defaults == null ? (
        <GlassWait />
      ) : (
        <div className="glass-card">
          <label className="ios-row">
            <span>{t(locale, "defaultsRarity")}</span>
            <select
              className="tz-select"
              value={defaults.rarity_mode}
              aria-label={t(locale, "defaultsRarity")}
              onChange={(e) =>
                void patchAdminDefaults(data, { rarity_mode: e.target.value })
                  .then(setDefaults)
                  .catch(onFail)
              }
            >
              <option value={RARITY_MODES.ALL}>{rarityLabel(RARITY_MODES.ALL, locale)}</option>
              <option value={RARITY_MODES.RARE}>{rarityLabel(RARITY_MODES.RARE, locale)}</option>
              <option value={RARITY_MODES.HIDDEN}>{rarityLabel(RARITY_MODES.HIDDEN, locale)}</option>
            </select>
          </label>
          <div className="ios-row">
            <span>{t(locale, "defaultsLinks")}</span>
            <Toggle
              on={defaults.show_profile_links}
              label={t(locale, "defaultsLinks")}
              onClick={() =>
                void patchAdminDefaults(data, {
                  show_profile_links: !defaults.show_profile_links,
                })
                  .then(setDefaults)
                  .catch(onFail)
              }
            />
          </div>
        </div>
      )}
    </>
  );
}
