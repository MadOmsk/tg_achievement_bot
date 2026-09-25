import { useState } from "react";
import { t, type Locale } from "../../i18n";
import type { AdminScreen } from "../../components/shared/constants";
import {
  AdminChatDetail,
  AdminChats,
  AdminDefaults,
  AdminKeys,
  AdminLimits,
  AdminUserDetail,
  AdminUsers,
} from "../../components/admin";
import "./Admin.css";

/**
 * The admin sub-screens. They are entered from the list in Settings
 * (`initial` says which one); "back" from a top-level one returns there.
 */
export function Admin({
  locale,
  data,
  initial,
  onBack,
  onFlash,
}: {
  locale: Locale;
  data: string;
  initial: AdminScreen;
  onBack: () => void;
  onFlash: (message: string) => void;
}) {
  const [screen, setScreen] = useState<AdminScreen>(initial);

  const fail = (err: unknown) =>
    onFlash(`${t(locale, "error")}: ${String(err)}`);

  switch (screen.name) {
    case "keys":
      return (
        <AdminKeys data={data} locale={locale} onBack={onBack} onFail={fail} />
      );
    case "limits":
      return (
        <AdminLimits data={data} locale={locale} onBack={onBack} onFail={fail} />
      );
    case "defaults":
      return (
        <AdminDefaults
          data={data}
          locale={locale}
          onBack={onBack}
          onFail={fail}
        />
      );
    case "users":
      return (
        <AdminUsers
          data={data}
          locale={locale}
          onSelectUser={(tgId) => setScreen({ name: "user", tgId })}
          onBack={onBack}
          onFail={fail}
        />
      );
    case "user":
      return (
        <AdminUserDetail
          data={data}
          tgId={screen.tgId}
          locale={locale}
          onBack={() => setScreen({ name: "users" })}
          onFail={fail}
        />
      );
    case "chats":
      return (
        <AdminChats
          data={data}
          locale={locale}
          onSelectChat={(chatId) => setScreen({ name: "chat", chatId })}
          onBack={onBack}
          onFail={fail}
        />
      );
    case "chat":
      return (
        <AdminChatDetail
          data={data}
          chatId={screen.chatId}
          locale={locale}
          onBack={() => setScreen({ name: "chats" })}
          onFlash={onFlash}
          onFail={fail}
        />
      );
    default:
      return null;
  }
}
