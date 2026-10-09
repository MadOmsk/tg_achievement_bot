import { useEffect, useState } from "react";
import {
  ApiError,
  deleteAdminKey,
  fetchAdminHome,
  fetchAdminKeys,
  putAdminKey,
  type AdminCredential,
  type AdminHome,
} from "../../../api";
import { t, type Locale } from "../../../i18n";
import { BackHead, Group, InfoRow, NavRow, SettingsSkel } from "../../shared/lib";
import "./AdminKeys.css";

/** The shared keys, as the server's registry lists them (#176) — a new one
 * appears here with no change to the app. A key is never shown back: one can
 * only set, replace or clear it. */
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
  const [keys, setKeys] = useState<AdminCredential[] | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [secret, setSecret] = useState("");
  const [error, setError] = useState<string | null>(null);
  // How hard the bot leans on each service, beside the keys it uses.
  const [usage, setUsage] = useState<AdminHome | null>(null);

  useEffect(() => {
    void fetchAdminHome(data).then(setUsage).catch(onFail);
  }, [data, onFail]);

  useEffect(() => {
    void fetchAdminKeys(data)
      .then((r) => setKeys(r.keys))
      .catch(onFail);
  }, [data, onFail]);

  const close = () => {
    setEditing(null);
    setSecret("");
    setError(null);
  };

  const refused = (err: unknown) => {
    if (err instanceof ApiError && (err.code === "invalid" || err.code === "setup")) {
      setError(t(locale, err.code === "invalid" ? "keyInvalid" : "keySetupError"));
      return;
    }
    onFail(err);
  };

  if (keys == null) {
    return (
      <>
        <BackHead title={t(locale, "adminKeys")} backLabel={t(locale, "back")} onBack={onBack} />
        <SettingsSkel groups={[5]} />
      </>
    );
  }

  const current = editing ? keys.find((k) => k.name === editing) : undefined;
  if (current) {
    return (
      <>
        <BackHead title={current.label} backLabel={t(locale, "back")} onBack={close} />
        <form
          className="form-stack admin-key-form"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            if (!secret.trim()) return;
            setError(null);
            void putAdminKey(data, current.name, secret.trim())
              .then((next) => {
                setKeys(next.keys);
                close();
              })
              .catch(refused);
          }}
        >
          <label className={`field${error ? " is-error" : ""}`}>
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
          {error ? (
            <p className="field-note is-error">{error}</p>
          ) : (
            <p className="field-note">
              {current.hint} {t(locale, "pasteKey")}
            </p>
          )}
          <button type="submit" className="btn is-wide" disabled={!secret.trim()}>
            {t(locale, "save")}
          </button>
        </form>
        {current.configured && (
          <Group>
            <NavRow
              danger
              label={t(locale, "clearKey")}
              onClick={() => {
                if (!window.confirm(t(locale, "confirmClear"))) return;
                void deleteAdminKey(data, current.name)
                  .then((next) => {
                    setKeys(next.keys);
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

  const keyState = (key: AdminCredential) =>
    !key.configured
      ? t(locale, "keyUnset")
      : key.status === "invalid"
        ? t(locale, "keyDead")
        : t(locale, "keySet");

  return (
    <>
      <BackHead title={t(locale, "adminKeys")} backLabel={t(locale, "back")} onBack={onBack} />
      <Group>
        {keys.map((key) => (
          <NavRow
            key={key.name}
            label={key.label}
            value={keyState(key)}
            onClick={() => {
              setEditing(key.name);
              setSecret("");
              setError(null);
            }}
          />
        ))}
      </Group>
      <Group title={t(locale, "groupApi")}>
        <InfoRow label={t(locale, "xboxUsage")} value={usage?.xbox_usage ?? "…"} />
        <InfoRow label={t(locale, "steamUsage")} value={usage?.steam_usage ?? "…"} />
        <InfoRow label={t(locale, "psnToday")} value={usage?.psn_requests ?? "…"} />
        <InfoRow
          label={t(locale, "mailHour")}
          value={usage ? `${usage.mail.hour}/${usage.mail.hour_limit}` : "…"}
        />
        <InfoRow
          label={t(locale, "mailDay")}
          value={usage ? `${usage.mail.day}/${usage.mail.day_limit}` : "…"}
        />
      </Group>
    </>
  );
}
