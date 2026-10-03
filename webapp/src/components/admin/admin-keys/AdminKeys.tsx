import { useEffect, useState } from "react";
import { deleteAdminKey, fetchAdminKeys, putAdminKey, type AdminKeys as AdminKeysType } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { BackHead, Group, NavRow, SettingsSkel } from "../../shared/lib";
import { ADMIN_KEY_NAMES, type AdminKeyName } from "../../shared/constants";

const LABELS: Record<AdminKeyName, "keySteam" | "keyPsn" | "keyAnthropic"> = {
  steam: "keySteam",
  psn: "keyPsn",
  anthropic: "keyAnthropic",
};

/** The shared keys. A key is never shown back: one can only set, replace or clear it. */
export function AdminKeys({
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
  const [keys, setKeys] = useState<AdminKeysType | null>(null);
  const [editing, setEditing] = useState<AdminKeyName | null>(null);
  const [secret, setSecret] = useState("");

  useEffect(() => {
    void fetchAdminKeys(data).then(setKeys).catch(onFail);
  }, [data, onFail]);

  const close = () => {
    setEditing(null);
    setSecret("");
  };

  if (keys == null) {
    return (
      <>
        <BackHead title={t(locale, "adminKeys")} backLabel={t(locale, "back")} onBack={onBack} />
        <SettingsSkel groups={[3]} />
      </>
    );
  }

  if (editing) {
    return (
      <>
        <BackHead title={t(locale, LABELS[editing])} backLabel={t(locale, "back")} onBack={close} />
        <Group title={t(locale, "keyNew")} hint={t(locale, "pasteKey")}>
          <label className="fr-row is-static">
            <input
              className="fr-input"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              autoComplete="off"
              autoFocus
              aria-label={t(locale, "keyNew")}
            />
          </label>
        </Group>
        <Group>
          <NavRow
            label={t(locale, "save")}
            disabled={!secret.trim()}
            onClick={() =>
              void putAdminKey(data, editing, secret.trim())
                .then((next) => {
                  setKeys(next);
                  close();
                })
                .catch(onFail)
            }
          />
          {keys[editing] && (
            <NavRow
              danger
              label={t(locale, "clearKey")}
              onClick={() => {
                if (!window.confirm(t(locale, "confirmClear"))) return;
                void deleteAdminKey(data, editing)
                  .then((next) => {
                    setKeys(next);
                    close();
                  })
                  .catch(onFail);
              }}
            />
          )}
        </Group>
      </>
    );
  }

  return (
    <>
      <BackHead title={t(locale, "adminKeys")} backLabel={t(locale, "back")} onBack={onBack} />
      <Group>
        {ADMIN_KEY_NAMES.map((name) => (
          <NavRow
            key={name}
            label={t(locale, LABELS[name])}
            value={keys[name] ? t(locale, "keySet") : t(locale, "keyUnset")}
            onClick={() => {
              setEditing(name);
              setSecret("");
            }}
          />
        ))}
      </Group>
    </>
  );
}
