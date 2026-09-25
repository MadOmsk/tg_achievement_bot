import { Chevron } from "../../shared/lib";
import { useEffect, useState } from "react";
import { fetchAdminHome, type AdminHome as AdminHomeType } from "../../../api";
import { t, type Locale } from "../../../i18n";
import type { AdminScreen } from "../../shared/constants";

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
    { screen: { name: "users" }, label: "adminUsers" },
    { screen: { name: "chats" }, label: "adminChats" },
    { screen: { name: "keys" }, label: "adminKeys" },
    { screen: { name: "limits" }, label: "adminLimits" },
    { screen: { name: "defaults" }, label: "adminDefaults" },
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
