import { useEffect, useState } from "react";
import {
  fetchAdminDefaults,
  patchAdminDefaults,
  type AdminDefaults as AdminDefaultsType,
} from "../../../api";
import { rarityLabel, t, type Locale } from "../../../i18n";
import { BackHead, ChoiceRow, Group, NumberRow, SettingsSkel, ToggleRow } from "../../shared/lib";
import { RARITY_MODES } from "../../shared/constants";

/** Rules that hold for everybody: the rarity threshold, new people's mode and
 * whether cards link to profiles. */
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

  const patch = (body: Partial<AdminDefaultsType>) =>
    void patchAdminDefaults(data, body).then(setDefaults).catch(onFail);

  const modes = [RARITY_MODES.ALL, RARITY_MODES.RARE, RARITY_MODES.HIDDEN].map((m) => ({
    value: m as string,
    label: rarityLabel(m, locale).replace(/^./, (c) => c.toUpperCase()),
  }));

  return (
    <>
      <BackHead title={t(locale, "adminDefaults")} backLabel={t(locale, "back")} onBack={onBack} />
      {defaults == null ? (
        <SettingsSkel groups={[1, 1, 1]} />
      ) : (
        <>
          <Group hint={t(locale, "adminRulesThresholdHint")}>
            <NumberRow
              label={t(locale, "adminRulesThreshold")}
              value={defaults.rare_threshold_percent}
              min={0.01}
              max={100}
              decimal
              onChange={(v) => patch({ rare_threshold_percent: v })}
            />
          </Group>
          <Group hint={t(locale, "adminRulesRarityHint")}>
            <ChoiceRow
              label={t(locale, "defaultsRarity")}
              value={defaults.rarity_mode}
              options={modes}
              onChange={(v) => patch({ rarity_mode: v })}
            />
          </Group>
          <Group>
            <ToggleRow
              label={t(locale, "defaultsLinks")}
              on={defaults.show_profile_links}
              onChange={(on) => patch({ show_profile_links: on })}
            />
          </Group>
        </>
      )}
    </>
  );
}
