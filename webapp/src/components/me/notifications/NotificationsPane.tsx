import { useEffect, useState } from "react";
import type { MeResponse } from "../../../api";
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

type Channel = "notify_push_on" | "notify_telegram_on";

/** A channel's tokens: a kind's key, with its choice after a colon where it has
 * one (`new_post:friends`, `game_news:patch`). */
function choiceOf(tokens: string[], kind: string): string | null {
  for (const token of tokens) {
    const [key, choice = ""] = token.split(":");
    if (key === kind) return choice;
  }
  return null;
}

function withChoice(tokens: string[], kind: string, choice: string | null): string[] {
  const rest = tokens.filter((token) => token.split(":")[0] !== kind);
  return choice === null ? rest : [...rest, choice ? `${kind}:${choice}` : kind];
}

/** Settings → «Уведомления» (#164; owner, 2026-10-06): every notice is kept in
 * the bell's list; push and Telegram are two blocks with the same rows — whose
 * posts, followers, friends, which game news (and, for push, the Xbox sign-in;
 * its Telegram message is the reminder's own) —, none on by default, shown
 * under the channel's own switch while it is on. */
export function NotificationsPane({
  me,
  locale,
  data,
  onBack,
  onPatch,
  onFlash,
}: {
  me: MeResponse;
  locale: Locale;
  data: string;
  onBack: () => void;
  onPatch: (body: {
    notify_push?: boolean;
    notify_telegram?: boolean;
    notify_push_on?: string[];
    notify_telegram_on?: string[];
  }) => void;
  onFlash: (message: string) => void;
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
  const pushReady = device === "on" && pushOn;
  const telegramReady = hasTelegram && me.settings.notify_telegram !== false;
  const channelRows = (channel: Channel, withAccount: boolean) => {
    const tokens = me.settings[channel] ?? [];
    const set = (kind: string, choice: string | null) => onPatch({ [channel]: withChoice(tokens, kind, choice) });
    const toggle = (kind: string, label: TranslationKey) => (
      <ToggleRow
        label={t(locale, label)}
        on={choiceOf(tokens, kind) !== null}
        onChange={(on) => set(kind, on ? "" : null)}
      />
    );
    return (
      <>
        <SelectRow<string>
          label={t(locale, "notifyPosts")}
          value={choiceOf(tokens, "new_post") ?? "off"}
          options={[
            { value: "off", label: t(locale, "notifyOff") },
            { value: "friends", label: t(locale, "notifyPostsFriends") },
            { value: "following", label: t(locale, "notifyPostsFollowing") },
          ]}
          onChange={(value) => set("new_post", value === "off" ? null : value)}
        />
        {toggle("new_follower", "notifyFollowers")}
        {toggle("new_friend", "notifyFriends")}
        <SelectRow<string>
          label={t(locale, "notifyGameNews")}
          value={choiceOf(tokens, "game_news") ?? "off"}
          options={[
            { value: "off", label: t(locale, "notifyOff") },
            { value: "all", label: t(locale, "postsAll") },
            { value: "patch", label: t(locale, "notifyGameNewsPatch") },
            { value: "news", label: t(locale, "notifyGameNewsNews") },
          ]}
          onChange={(value) => set("game_news", value === "off" ? null : value)}
        />
        {withAccount && toggle("xbox_login_dead", "notifyAccount")}
      </>
    );
  };

  return (
    <>
      <BackHead title={t(locale, "notifications")} backLabel={t(locale, "back")} onBack={onBack} />
      {/* Push on this device: its switch, then the kinds it carries. A device
          that cannot get pushes says why instead of a switch. */}
      <Group title={t(locale, "notifyPushGroup")}>
        {device === "on" || device === "off" ? (
          <ToggleRow
            label={t(locale, "notifyPush")}
            sub={t(locale, "notifyPushHint")}
            on={pushReady}
            onChange={(on) => void toggleDevice(on)}
          />
        ) : (
          <InfoRow label={t(locale, "notifyPush")} sub={hint ? t(locale, hint) : t(locale, "notifyPushHint")} />
        )}
        {pushReady && channelRows("notify_push_on", true)}
      </Group>
      {/* Only with Telegram linked (Settings → «Вход» links it). */}
      {hasTelegram && (
        <Group title={t(locale, "notifyTelegramGroup")}>
          <ToggleRow
            label={t(locale, "notifyTelegram")}
            sub={t(locale, "notifyTelegramHint")}
            on={telegramReady}
            onChange={(on) => onPatch({ notify_telegram: on })}
          />
          {telegramReady && channelRows("notify_telegram_on", false)}
        </Group>
      )}
    </>
  );
}
