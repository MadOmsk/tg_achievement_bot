import { useEffect, useState } from "react";
import { ApiError, userApi, type PasskeysResponse } from "../../../api";
import { formatWhen, t, type Locale } from "../../../i18n";
import {
  Group,
  Icon,
  InfoRow,
  NavRow,
  createPasskey,
  passkeyCancelled,
  passkeysSupported,
  showToast,
} from "../../shared/lib";

/** Settings → «Вход» → «Ключи доступа» (owner, 2026-10-08): the keys that sign
 * this person in in place of an email's code — each with where it was made and
 * when it last signed in, a trash to remove it, and a row to add one more.
 * Only in a browser: inside Telegram the app signs in with Telegram. */
export function PasskeysGroup({ locale, data }: { locale: Locale; data: string }) {
  const [state, setState] = useState<PasskeysResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const supported = passkeysSupported();
  const inTelegram = Boolean(window.Telegram?.WebApp?.initData);
  const fail = (err: unknown) => showToast(`${t(locale, "error")}: ${String(err)}`, "error");

  useEffect(() => {
    userApi
      .passkeys(data)
      .then(setState)
      .catch(() => setState(null));
  }, [data]);

  if (!state?.available) return null;

  const add = () => {
    if (busy) return;
    setBusy(true);
    userApi
      .passkeyOptions(data)
      .then(async ({ token, options }) => {
        const credential = await createPasskey(options);
        setState(await userApi.addPasskey(data, token, credential));
        showToast(t(locale, "passkeyAdded"), "success");
      })
      .catch((err: unknown) => {
        if (passkeyCancelled(err)) return;
        // A key this phone already holds for this site: the browser refuses it
        // as InvalidStateError, the server as `taken`.
        const taken =
          (err instanceof DOMException && err.name === "InvalidStateError") ||
          (err instanceof ApiError && err.code === "taken");
        if (taken) showToast(t(locale, "passkeyTaken"), "error");
        else fail(err);
      })
      .finally(() => setBusy(false));
  };

  const remove = (id: string) => {
    if (!window.confirm(t(locale, "passkeyRemoveConfirm"))) return;
    userApi.removePasskey(data, id).then(setState).catch(fail);
  };

  return (
    <Group title={t(locale, "passkeysTitle")}>
      {state.keys.map((key) => (
        <InfoRow
          key={key.id}
          label={key.name ?? t(locale, "passkeyUnnamed")}
          sub={[
            `${t(locale, "passkeyCreated")} ${formatWhen(key.created_at, locale)}`,
            key.last_used_at ? `${t(locale, "passkeyUsed")} ${formatWhen(key.last_used_at, locale)}` : null,
          ]
            .filter(Boolean)
            .join(" · ")}
        >
          <span className="fr-icons" role="group">
            <button
              type="button"
              className="is-danger"
              onClick={() => remove(key.id)}
              aria-label={t(locale, "passkeyRemove")}
              title={t(locale, "passkeyRemove")}
            >
              <Icon name="trash" size={16} />
            </button>
          </span>
        </InfoRow>
      ))}
      {supported ? (
        // What a key is, as every setting says it: the row's own second line.
        <NavRow label={t(locale, "passkeyAdd")} sub={t(locale, "passkeysHint")} onClick={add} />
      ) : (
        <InfoRow label={t(locale, inTelegram ? "passkeyInTelegram" : "passkeyNoSupport")} />
      )}
    </Group>
  );
}
