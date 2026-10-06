import { useEffect, useState } from "react";
import type { MeResponse, GameNewsChoice, NotifyPosts } from "../../../api";
import { t, type Locale, type TranslationKey } from "../../../i18n";
import { BackHead, Group, InfoRow, SelectRow, ToggleRow } from "../../shared/lib";
import { disablePush, enablePush, pushState, quickPushState, type PushState } from "./push";
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
    notify_new_posts?: boolean;
    notify_friends?: boolean;
    notify_account?: boolean;
    notify_game_news?: GameNewsChoice;
  }) => void;
  onFlash: (message: string) => void;
  /** Opens Settings → «Вход», for somebody with no Telegram yet. */
  onAddTelegram: () => void;
}) {
  // Drawn at once from what is known now; the real answer replaces it.
  const [device, setDevice] = useState<PushState>(quickPushState);
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
    if (busy) return;
    setBusy(true);
    try {
      const next = on ? await enablePush(data) : await disablePush(data);
      setDevice(next);
      // Pushes to anywhere were switched off once: turning them on here means them.
      if (next === "on" && !pushOn) onPatch({ notify_push: true });
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
      <Group title={t(locale, "notifyWhere")}>
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
        {/* One row for push (owner, 2026-10-05): on is this device subscribed;
            a device that cannot get pushes says why instead of a switch. */}
        {device === "on" || device === "off" ? (
          <ToggleRow
            label={t(locale, "notifyPush")}
            sub={t(locale, "notifyPushHint")}
            on={device === "on" && pushOn}
            onChange={(on) => void toggleDevice(on)}
          />
        ) : (
          <InfoRow label={t(locale, "notifyPush")} sub={hint ? t(locale, hint) : t(locale, "notifyPushHint")} />
        )}
      </Group>
      {/* By what they are about (owner, 2026-10-06): people, games, accounts;
          whose activity first, then a switch per kind. */}
      <Group title={t(locale, "notifyPeople")}>
        <SelectRow<NotifyPosts>
          label={t(locale, "notifyFrom")}
          sub={t(locale, "notifyFromHint")}
          value={me.settings.notify_posts ?? "friends"}
          options={[
            { value: "friends", label: t(locale, "notifyPostsFriends") },
            { value: "following", label: t(locale, "notifyPostsFollowing") },
            { value: "none", label: t(locale, "notifyPostsNone") },
          ]}
          onChange={(value) => onPatch({ notify_posts: value })}
        />
        <ToggleRow
          label={t(locale, "notifyPosts")}
          sub={t(locale, "notifyPostsHint")}
          on={me.settings.notify_new_posts !== false && me.settings.notify_posts !== "none"}
          // "Nobody" switched them off too: turning them on brings friends back.
          onChange={(on) =>
            onPatch(
              on && me.settings.notify_posts === "none"
                ? { notify_new_posts: true, notify_posts: "friends" }
                : { notify_new_posts: on },
            )
          }
        />
        <ToggleRow
          label={t(locale, "notifyFollowers")}
          sub={t(locale, "notifyFollowersHint")}
          on={me.settings.notify_followers !== false}
          onChange={(on) => onPatch({ notify_followers: on })}
        />
        <ToggleRow
          label={t(locale, "notifyFriends")}
          sub={t(locale, "notifyFriendsHint")}
          on={me.settings.notify_friends !== false}
          onChange={(on) => onPatch({ notify_friends: on })}
        />
      </Group>
      <Group title={t(locale, "notifyGames")}>
        <SelectRow<GameNewsChoice>
          label={t(locale, "notifyGameNews")}
          sub={t(locale, "notifyGameNewsHint")}
          value={me.settings.notify_game_news ?? "all"}
          options={[
            { value: "all", label: t(locale, "postsAll") },
            { value: "patch", label: t(locale, "notifyGameNewsPatch") },
            { value: "news", label: t(locale, "notifyGameNewsNews") },
            { value: "none", label: t(locale, "notifyGameNewsNone") },
          ]}
          onChange={(value) => onPatch({ notify_game_news: value })}
        />
      </Group>
      <Group title={t(locale, "notifyAccounts")}>
        <ToggleRow
          label={t(locale, "notifyAccount")}
          sub={t(locale, "notifyAccountHint")}
          on={me.settings.notify_account !== false}
          onChange={(on) => onPatch({ notify_account: on })}
        />
      </Group>
    </>
  );
}
