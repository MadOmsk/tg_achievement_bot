import { useEffect, useState } from "react";
import { fetchAdminHome, type AdminHome as AdminHomeType } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { Group, InfoRow, NavRow } from "../../shared/lib";
import { ADMIN_SCREENS, type AdminScreen } from "../../shared/constants";

/** The super-admin's part of Settings: the admin sections, then the API load. */
export function AdminSection({
  data,
  locale,
  onNavigate,
  onFail,
}: {
  data: string;
  locale: Locale;
  onNavigate: (screen: AdminScreen) => void;
  onFail: (err: unknown) => void;
}) {
  const [home, setHome] = useState<AdminHomeType | null>(null);

  useEffect(() => {
    void fetchAdminHome(data).then(setHome).catch(onFail);
  }, [data, onFail]);

  const sections = [
    { screen: { name: ADMIN_SCREENS.USERS }, label: "adminUsers" },
    { screen: { name: ADMIN_SCREENS.CHATS }, label: "adminChats" },
    { screen: { name: ADMIN_SCREENS.DEFAULTS }, label: "adminDefaults" },
    { screen: { name: ADMIN_SCREENS.LIMITS }, label: "adminLimits" },
    { screen: { name: ADMIN_SCREENS.KEYS }, label: "adminKeys" },
  ] as const;

  return (
    <>
      <Group title={t(locale, "admin")}>
        {sections.map(({ screen, label }) => (
          <NavRow key={screen.name} label={t(locale, label)} onClick={() => onNavigate(screen)} />
        ))}
      </Group>
      <Group title={t(locale, "groupApi")}>
        <InfoRow label={t(locale, "xboxUsage")} value={home?.xbox_usage ?? "…"} />
        <InfoRow label={t(locale, "steamUsage")} value={home?.steam_usage ?? "…"} />
        <InfoRow label={t(locale, "psnToday")} value={home?.psn_requests ?? "…"} />
      </Group>
    </>
  );
}
