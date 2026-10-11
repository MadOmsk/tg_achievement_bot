import { useEffect, useState } from "react";
import { fetchAdminSettings, patchAdminSetting, type AdminSettingsGroup } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { BackHead, SettingsSkel } from "../../shared/lib";
import { AdminActions } from "../admin-actions/AdminActions";
import { AdminSettingsForm } from "../admin-settings-form/AdminSettingsForm";

/** Every global setting, in the groups the bot's «⚙️ Настройки» shows, then
 * the app's own actions (the notification test) — the server's registries. */
export function AdminSettings({
  data,
  locale,
  onBack,
  onFlash,
  onFail,
}: {
  data: string;
  locale: Locale;
  onBack: () => void;
  onFlash: (message: string) => void;
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
        <>
          <AdminSettingsForm
            groups={groups}
            locale={locale}
            onChange={(key, value) =>
              void patchAdminSetting(data, key, value)
                .then((r) => setGroups(r.groups))
                .catch(onFail)
            }
          />
          <AdminActions
            data={data}
            scope="global"
            target="all"
            onFlash={onFlash}
            onFail={onFail}
            onDone={() => undefined}
          />
        </>
      )}
    </>
  );
}
