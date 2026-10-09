import { useEffect, useState } from "react";
import { fetchAdminSettings, patchAdminSetting, type AdminSettingsGroup } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { BackHead, SettingsSkel } from "../../shared/lib";
import { AdminSettingsForm } from "../admin-settings-form/AdminSettingsForm";

/** Every global setting, in the groups the bot's «⚙️ Настройки» shows. */
export function AdminSettings({
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
  const [groups, setGroups] = useState<AdminSettingsGroup[] | null>(null);

  useEffect(() => {
    void fetchAdminSettings(data)
      .then((r) => setGroups(r.groups))
      .catch(onFail);
  }, [data, onFail]);

  return (
    <>
      <BackHead title={t(locale, "adminSettings")} backLabel={t(locale, "back")} onBack={onBack} />
      {groups == null ? (
        <SettingsSkel groups={[3, 3, 2, 6]} />
      ) : (
        <AdminSettingsForm
          groups={groups}
          locale={locale}
          onChange={(key, value) =>
            void patchAdminSetting(data, key, value)
              .then((r) => setGroups(r.groups))
              .catch(onFail)
          }
        />
      )}
    </>
  );
}
