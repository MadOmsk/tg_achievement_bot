import { useEffect, useState } from "react";
import {
  fetchAdminChats,
  patchAdminChat,
  postAdminChatAction,
  type AdminChatRow,
} from "../../../api";
import { digestLabel, formatOffset, t, timezoneLabel, type Locale } from "../../../i18n";
import {
  BackHead,
  ChoiceRow,
  Group,
  NavRow,
  NumberRow,
  SelectRow,
  SettingsSkel,
  ToggleRow,
} from "../../shared/lib";
import {
  ADMIN_CHAT_ACTIONS,
  DIGEST_CHOICES,
  TIMEZONES,
  type AdminChatAction,
} from "../../shared/constants";

export function AdminChatDetail({
  data,
  chatId,
  locale,
  onBack,
  onFlash,
  onFail,
}: {
  data: string;
  chatId: number;
  locale: Locale;
  onBack: () => void;
  onFlash: (message: string) => void;
  onFail: (err: unknown) => void;
}) {
  const [chat, setChat] = useState<AdminChatRow | null>(null);

  useEffect(() => {
    void fetchAdminChats(data)
      .then((r) => setChat(r.chats.find((c) => c.chat_id === chatId) ?? null))
      .catch(onFail);
  }, [chatId, data, onFail]);

  const onPatch = (body: Record<string, unknown>) => {
    if (!chat) return;
    void patchAdminChat(data, chat.chat_id, body).then(setChat).catch(onFail);
  };

  const onAction = (action: AdminChatAction) => {
    if (!chat) return;
    if (action.startsWith("wipe") && !window.confirm(t(locale, "confirmWipe"))) return;
    void postAdminChatAction(data, chat.chat_id, action)
      .then((r) => onFlash(r.preview || `${t(locale, "deleteLast")}: ${r.deleted ?? 0}`))
      .catch(onFail);
  };

  const tz = chat?.tz_offset_min ?? 0;
  const tzOptions = (
    !TIMEZONES.some((z) => z.min === tz) ? [{ min: tz, label: formatOffset(tz, locale) }, ...TIMEZONES] : TIMEZONES
  ).map((z) => ({ value: z.min, label: timezoneLabel(z, locale) }));

  return (
    <>
      <BackHead
        title={chat?.title || String(chat?.chat_id ?? t(locale, "adminChats"))}
        backLabel={t(locale, "back")}
        onBack={onBack}
      />
      {chat == null ? (
        <SettingsSkel groups={[3, 2, 2, 4]} />
      ) : (
        <>
          <Group>
            <ToggleRow
              label={t(locale, "chatEnabled")}
              on={chat.is_active}
              onChange={(on) => onPatch({ is_active: on })}
            />
            <ChoiceRow
              label={t(locale, "language")}
              value={chat.locale === "en" ? "en" : "ru"}
              options={[
                { value: "ru", label: "RU" },
                { value: "en", label: "EN" },
              ]}
              onChange={(v) => onPatch({ locale: v })}
            />
            <SelectRow
              label={t(locale, "timezone")}
              value={tz}
              options={tzOptions}
              onChange={(v) => onPatch({ tz_offset_min: v })}
            />
          </Group>

          <Group title={t(locale, "chatGroupPublishing")}>
            <SelectRow
              label={t(locale, "digest")}
              value={chat.digest_threshold}
              options={DIGEST_CHOICES.map((n) => ({ value: n as number, label: digestLabel(n, locale) }))}
              onChange={(v) => onPatch({ digest_threshold: v })}
            />
            <NumberRow
              label={t(locale, "minScore")}
              value={chat.min_gamerscore}
              min={0}
              onChange={(v) => onPatch({ min_gamerscore: v })}
            />
          </Group>

          <Group title={t(locale, "chatGroupFlood")}>
            <NumberRow
              label={t(locale, "floodLimit")}
              sub={t(locale, "limitZeroOff")}
              value={chat.flood_limit}
              min={0}
              onChange={(v) => onPatch({ flood_limit: v })}
            />
            <NumberRow
              label={t(locale, "floodWindow")}
              value={chat.flood_window_minutes}
              min={1}
              onChange={(v) => onPatch({ flood_window_minutes: v })}
            />
          </Group>

          <Group title={t(locale, "chatGroupMessages")}>
            <NavRow
              label={t(locale, "deleteLast")}
              onClick={() => onAction(ADMIN_CHAT_ACTIONS.DELETE_LAST)}
            />
            <NavRow
              danger
              label={t(locale, "wipe24h")}
              onClick={() => onAction(ADMIN_CHAT_ACTIONS.WIPE_24H)}
            />
            <NavRow
              danger
              label={t(locale, "wipeSystem24h")}
              onClick={() => onAction(ADMIN_CHAT_ACTIONS.WIPE_SYSTEM_24H)}
            />
            <NavRow
              danger
              label={t(locale, "wipeSystemAll")}
              onClick={() => onAction(ADMIN_CHAT_ACTIONS.WIPE_SYSTEM_ALL)}
            />
          </Group>
        </>
      )}
    </>
  );
}
