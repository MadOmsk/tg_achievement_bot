import { useEffect, useState } from "react";
import type { MeResponse, NotifyPosts } from "../../../api";
import { t, type Locale, type TranslationKey } from "../../../i18n";
import { BackHead, Group, InfoRow, SelectRow, ToggleRow } from "../../shared/lib";
import { disablePush, enablePush, pushState, type PushState } from "./push";
import "./Notifications.css";

/** Why this device gets no pushes, when it cannot (#164). */
const DEVICE_HINT: Partial<Record<PushState, TranslationKey>> = {
  telegram: "pushInTelegram",
  "ios-install": "pushIosInstall",
  unsupported: "pushUnsupported",
  unavailable: "pushUnavailable",
  denied: "pushDenied",
};

/** Settings → «Уведомления» (#164): where the app's notices go — pushed to this
 * device, and as a Telegram message — and what they are about. */
export function NotificationsPane({
  me,
  locale,
  data,
  onBack,
  onPatch,
  onFlash,
  onAddTelegram,
}: {
  me: MeResponse;
  locale: Locale;
  data: string;
  onBack: () => void;
  onPatch: (body: {
    notify_push?: boolean;
    notify_telegram?: boolean;
    notify_followers?: boolean;
    notify_posts?: NotifyPosts;
  }) => void;
  onFlash: (message: string) => void;
  /** Opens Settings → «Вход», for somebody with no Telegram yet. */
  onAddTelegram: () => void;
}) {
  const [device, setDevice] = useState<PushState | null>(null);
  const [busy, setBusy] = useState(false);
  const pushOn = me.settings.notify_push !== false;
  const hasTelegram = me.tg_id !== null;

  useEffect(() => {
    let cancelled = false;
    void pushState(data).then((state) => {
      if (!cancelled) setDevice(state);
    });
    return () => {
      cancelled = true;
    };
  }, [data]);

  const toggleDevice = async (on: boolean) => {
    setBusy(true);
    try {
      setDevice(on ? await enablePush(data) : await disablePush(data));
    } catch (err) {
      onFlash(`${t(locale, "error")}: ${String(err)}`);
    } finally {
      setBusy(false);
    }
  };

  const hint = device ? DEVICE_HINT[device] : undefined;

  return (
    <>
      <BackHead title={t(locale, "notifications")} backLabel={t(locale, "back")} onBack={onBack} />
      <Group title={t(locale, "notifyWhere")} hint={pushOn && hint ? t(locale, hint) : undefined}>
        <ToggleRow
          label={t(locale, "notifyPush")}
          sub={t(locale, "notifyPushHint")}
          on={pushOn}
          onChange={(on) => onPatch({ notify_push: on })}
        />
        {pushOn && (device === "on" || device === "off") && (
          <InfoRow
            label={t(locale, "pushThisDevice")}
            sub={t(locale, device === "on" ? "pushDeviceOn" : "pushDeviceOff")}
          >
            <button
              type="button"
              className={device === "on" ? "btn sm is-quiet" : "btn sm"}
              disabled={busy}
              onClick={() => void toggleDevice(device !== "on")}
            >
              {t(locale, device === "on" ? "pushDisable" : "pushEnable")}
            </button>
          </InfoRow>
        )}
        {hasTelegram ? (
          <ToggleRow
            label={t(locale, "notifyTelegram")}
            sub={t(locale, "notifyTelegramHint")}
            on={me.settings.notify_telegram !== false}
            onChange={(on) => onPatch({ notify_telegram: on })}
          />
        ) : (
          <InfoRow label={t(locale, "notifyTelegram")} sub={t(locale, "notifyTelegramNeeds")}>
            <button type="button" className="btn sm is-quiet" onClick={onAddTelegram}>
              {t(locale, "notifyTelegramAdd")}
            </button>
          </InfoRow>
        )}
      </Group>
      <Group title={t(locale, "notifyWhat")}>
        <ToggleRow
          label={t(locale, "notifyFollowers")}
          sub={t(locale, "notifyFollowersHint")}
          on={me.settings.notify_followers !== false}
          onChange={(on) => onPatch({ notify_followers: on })}
        />
        <SelectRow<NotifyPosts>
          label={t(locale, "notifyPosts")}
          sub={t(locale, "notifyPostsHint")}
          value={me.settings.notify_posts ?? "friends"}
          options={[
            { value: "friends", label: t(locale, "notifyPostsFriends") },
            { value: "following", label: t(locale, "notifyPostsFollowing") },
            { value: "none", label: t(locale, "notifyPostsNone") },
          ]}
          onChange={(value) => onPatch({ notify_posts: value })}
        />
      </Group>
    </>
  );
}
