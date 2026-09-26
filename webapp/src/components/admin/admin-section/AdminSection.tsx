import { Chevron } from "../../shared/lib";
import { useEffect, useState } from "react";
import { fetchAdminHome, type AdminHome as AdminHomeType } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { ADMIN_SCREENS, type AdminScreen } from "../../shared/constants";

/**
 * The super-admin's part of the settings screen: a list of the admin
 * sections (each opens its own screen) and the API usage lines. It sits
 * straight in Settings rather than behind a separate "Admin" entry.
 */
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
    { screen: { name: ADMIN_SCREENS.KEYS }, label: "adminKeys" },
    { screen: { name: ADMIN_SCREENS.LIMITS }, label: "adminLimits" },
    { screen: { name: ADMIN_SCREENS.DEFAULTS }, label: "adminDefaults" },
  ] as const;

  return (
    <>
      <p className="kicker">{t(locale, "admin")}</p>
      <div className="glass-card">
        {sections.map(({ screen, label }) => (
          <button
            key={screen.name}
            type="button"
            className="ios-row"
            onClick={() => onNavigate(screen)}
          >
            <span>{t(locale, label)}</span>
            <span className="ios-value">
              <Chevron />
            </span>
          </button>
        ))}
      </div>
      {home && (
        <div className="glass-card">
          <div className="ios-row">
            <span>{t(locale, "xboxUsage")}</span>
            <span className="ios-value">{home.xbox_usage}</span>
          </div>
          <div className="ios-row">
            <span>{t(locale, "steamUsage")}</span>
            <span className="ios-value">{home.steam_usage}</span>
          </div>
          <div className="ios-row">
            <span>{t(locale, "psnToday")}</span>
            <span className="ios-value">{home.psn_requests}</span>
          </div>
        </div>
      )}
    </>
  );
}
