import { useEffect, useState } from "react";
import {
  fetchAdminChats,
  fetchAdminChatSettings,
  patchAdminChatSetting,
  postAdminChatAction,
  type AdminChatRow,
  type AdminSettingsGroup,
} from "../../../api";
import { t, type Locale } from "../../../i18n";
import { BackHead, Group, NavRow, SettingsSkel } from "../../shared/lib";
import { ADMIN_CHAT_ACTIONS, type AdminChatAction } from "../../shared/constants";
import { AdminSettingsForm } from "../admin-settings-form/AdminSettingsForm";

/** One chat: its settings as the server's registry lists them (the bot's chat
 * card shows the same groups), then the actions on its messages. */
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
  const [groups, setGroups] = useState<AdminSettingsGroup[] | null>(null);

  useEffect(() => {
    void fetchAdminChats(data)
      .then((r) => setChat(r.chats.find((c) => c.chat_id === chatId) ?? null))
      .catch(onFail);
    void fetchAdminChatSettings(data, chatId)
      .then((r) => setGroups(r.groups))
      .catch(onFail);
  }, [chatId, data, onFail]);

  const onAction = (action: AdminChatAction) => {
    if (action.startsWith("wipe") && !window.confirm(t(locale, "confirmWipe"))) return;
    void postAdminChatAction(data, chatId, action)
      .then((r) => onFlash(r.preview || `${t(locale, "deleteLast")}: ${r.deleted ?? 0}`))
      .catch(onFail);
  };

  return (
    <>
      <BackHead
        title={chat?.title || String(chat?.chat_id ?? t(locale, "adminChats"))}
        backLabel={t(locale, "back")}
        onBack={onBack}
      />
      {groups == null ? (
        <SettingsSkel groups={[3, 1, 2, 2, 4]} />
      ) : (
        <>
          <AdminSettingsForm
            groups={groups}
            locale={locale}
            onChange={(key, value) =>
              void patchAdminChatSetting(data, chatId, key, value)
                .then((r) => setGroups(r.groups))
                .catch(onFail)
            }
          />

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
