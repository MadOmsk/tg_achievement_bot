import { t, type Locale } from "../../../i18n";
import { Group, NavRow, RowGlyph } from "../../shared/lib";
import { ADMIN_SCREENS, type AdminScreen } from "../../shared/constants";

/** The super-admin's part of Settings: one row per admin screen. The API load
 * lives on the keys screen, beside the keys it is about. */
export function AdminSection({
  locale,
  onNavigate,
}: {
  locale: Locale;
  onNavigate: (screen: AdminScreen) => void;
}) {
  const sections = [
    { screen: { name: ADMIN_SCREENS.USERS }, icon: "people", label: "adminUsers", sub: "adminUsersSub" },
    { screen: { name: ADMIN_SCREENS.CHATS }, icon: "chat", label: "adminChats", sub: "adminChatsSub" },
    { screen: { name: ADMIN_SCREENS.SETTINGS }, icon: "gauge", label: "adminSettings", sub: "adminSettingsSub" },
    { screen: { name: ADMIN_SCREENS.KEYS }, icon: "key", label: "adminKeys", sub: "adminKeysSub" },
  ] as const;

  return (
    <Group title={t(locale, "admin")}>
      {sections.map(({ screen, icon, label, sub }) => (
        <NavRow
          key={screen.name}
          lead={<RowGlyph name={icon} />}
          label={t(locale, label)}
          sub={t(locale, sub)}
          onClick={() => onNavigate(screen)}
        />
      ))}
    </Group>
  );
}
