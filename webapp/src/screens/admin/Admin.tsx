import { useState } from "react";
import { t, type Locale } from "../../i18n";
import { ADMIN_SCREENS, type AdminScreen } from "../../components/shared/constants";
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
    case ADMIN_SCREENS.KEYS:
      return (
        <AdminKeys data={data} locale={locale} onBack={onBack} onFail={fail} />
      );
    case ADMIN_SCREENS.LIMITS:
      return (
        <AdminLimits data={data} locale={locale} onBack={onBack} onFail={fail} />
      );
    case ADMIN_SCREENS.DEFAULTS:
      return (
        <AdminDefaults
          data={data}
          locale={locale}
          onBack={onBack}
          onFail={fail}
        />
      );
    case ADMIN_SCREENS.USERS:
      return (
        <AdminUsers
          data={data}
          locale={locale}
          onSelectUser={(tgId) => setScreen({ name: ADMIN_SCREENS.USER, tgId })}
          onBack={onBack}
          onFail={fail}
        />
      );
    case ADMIN_SCREENS.USER:
      return (
        <AdminUserDetail
          data={data}
          tgId={screen.tgId}
          locale={locale}
          onBack={() => setScreen({ name: ADMIN_SCREENS.USERS })}
          onFail={fail}
        />
      );
    case ADMIN_SCREENS.CHATS:
      return (
        <AdminChats
          data={data}
          locale={locale}
          onSelectChat={(chatId) => setScreen({ name: ADMIN_SCREENS.CHAT, chatId })}
          onBack={onBack}
          onFail={fail}
        />
      );
    case ADMIN_SCREENS.CHAT:
      return (
        <AdminChatDetail
          data={data}
          chatId={screen.chatId}
          locale={locale}
          onBack={() => setScreen({ name: ADMIN_SCREENS.CHATS })}
          onFlash={onFlash}
          onFail={fail}
        />
      );
    default:
      return null;
  }
}
