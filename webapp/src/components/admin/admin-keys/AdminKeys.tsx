import { useEffect, useState } from "react";
import {
  deleteAdminKey,
  fetchAdminKeys,
  putAdminKey,
  type AdminKeys as AdminKeysType,
} from "../../../api";
import { t, type Locale } from "../../../i18n";
import { BackHead, GlassWait, Chevron } from "../../shared/lib";
import {
  ADMIN_KEY_NAMES,
  type AdminKeyName,
} from "../../shared/constants";

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
  const [keyName, setKeyName] = useState<AdminKeyName | null>(null);
  const [secret, setSecret] = useState("");

  useEffect(() => {
    void fetchAdminKeys(data).then(setKeys).catch(onFail);
  }, [data, onFail]);

  const keyLabels: Record<AdminKeyName, "keySteam" | "keyPsn" | "keyAnthropic"> = {
    steam: "keySteam",
    psn: "keyPsn",
    anthropic: "keyAnthropic",
  };

  return (
    <>
      <BackHead
        title={t(locale, "adminKeys")}
        backLabel={t(locale, "back")}
        onBack={onBack}
      />
      {keys == null ? (
        <GlassWait />
      ) : (
        <>
          <div className="glass-card">
            {ADMIN_KEY_NAMES.map((name) => (
              <button
                key={name}
                type="button"
                className="ios-row"
                onClick={() => {
                  setKeyName(name);
                  setSecret("");
                }}
              >
                <span>{t(locale, keyLabels[name])}</span>
                <span className="ios-value">
                  {keys[name] ? t(locale, "keySet") : t(locale, "keyUnset")}
                  <Chevron />
                </span>
              </button>
            ))}
          </div>

          {keyName && (
            <div className="glass-card">
              <div className="ios-row">
                <span className="admin-limit-copy">
                  <strong>{t(locale, keyLabels[keyName])}</strong>
                  <small>{t(locale, "pasteKey")}</small>
                </span>
              </div>
              <label className="ios-row">
                <input
                  className="admin-secret-input"
                  value={secret}
                  onChange={(e) => setSecret(e.target.value)}
                  autoComplete="off"
                  aria-label={t(locale, "pasteKey")}
                />
              </label>
              <button
                type="button"
                className="ios-row"
                disabled={!secret.trim()}
                onClick={() => {
                  void putAdminKey(data, keyName, secret.trim())
                    .then((next) => {
                      setKeys(next);
                      setSecret("");
                      setKeyName(null);
                    })
                    .catch(onFail);
                }}
              >
                <span>{t(locale, "save")}</span>
                <span className="ios-value">
                  <Chevron />
                </span>
              </button>
              {keys[keyName] && (
                <button
                  type="button"
                  className="ios-row danger"
                  onClick={() => {
                    if (!window.confirm(t(locale, "confirmClear"))) return;
                    void deleteAdminKey(data, keyName)
                      .then((next) => {
                        setKeys(next);
                        setKeyName(null);
                        setSecret("");
                      })
                      .catch(onFail);
                  }}
                >
                  <span>{t(locale, "clearKey")}</span>
                </button>
              )}
              <button
                type="button"
                className="ios-row"
                onClick={() => {
                  setKeyName(null);
                  setSecret("");
                }}
              >
                <span>{t(locale, "cancel")}</span>
              </button>
            </div>
          )}
        </>
      )}
    </>
  );
}
