import { useEffect, useState } from "react";
import {
  deleteAdminKey,
  fetchAdminHome,
  fetchAdminKeys,
  putAdminKey,
  type AdminHome,
  type AdminKeys as AdminKeysType,
} from "../../../api";
import { t, type Locale } from "../../../i18n";
import { BackHead, Group, InfoRow, NavRow, SettingsSkel } from "../../shared/lib";
import { ADMIN_KEY_NAMES, type AdminKeyName } from "../../shared/constants";
import "./AdminKeys.css";

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
  // How hard the bot leans on each platform, beside the keys it uses.
  const [usage, setUsage] = useState<AdminHome | null>(null);

  useEffect(() => {
    void fetchAdminHome(data).then(setUsage).catch(onFail);
  }, [data, onFail]);

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
        <form
          className="form-stack admin-key-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (!secret.trim()) return;
            void putAdminKey(data, editing, secret.trim())
              .then((next) => {
                setKeys(next);
                close();
              })
              .catch(onFail);
          }}
        >
          <label className="field">
            <input
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              placeholder={t(locale, "keyNew")}
              autoComplete="off"
              spellCheck={false}
              autoFocus
              aria-label={t(locale, "keyNew")}
            />
          </label>
          <p className="field-note">{t(locale, "pasteKey")}</p>
          <button type="submit" className="btn is-wide" disabled={!secret.trim()}>
            {t(locale, "save")}
          </button>
        </form>
        {keys[editing] && (
          <Group>
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
          </Group>
        )}
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
      <Group title={t(locale, "groupApi")}>
        <InfoRow label={t(locale, "xboxUsage")} value={usage?.xbox_usage ?? "…"} />
        <InfoRow label={t(locale, "steamUsage")} value={usage?.steam_usage ?? "…"} />
        <InfoRow label={t(locale, "psnToday")} value={usage?.psn_requests ?? "…"} />
      </Group>
    </>
  );
}
