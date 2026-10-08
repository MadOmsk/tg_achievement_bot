import { useEffect, useState } from "react";
import {
  fetchAdminChats,
  fetchAdminChatSettings,
  patchAdminChatSetting,
  type AdminChatRow,
  type AdminSettingsGroup,
} from "../../../api";
import { t, type Locale } from "../../../i18n";
import { BackHead, SettingsSkel } from "../../shared/lib";
import { AdminActions } from "../admin-actions/AdminActions";
import { AdminSettingsForm } from "../admin-settings-form/AdminSettingsForm";

/** One chat: its settings and its actions, as the server's registries list
 * them — the bot's chat card shows the same. */
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

          <AdminActions
            data={data}
            scope="chat"
            target={String(chatId)}
            onFlash={onFlash}
            onFail={onFail}
            onDone={() => undefined}
          />
        </>
      )}
    </>
  );
}
