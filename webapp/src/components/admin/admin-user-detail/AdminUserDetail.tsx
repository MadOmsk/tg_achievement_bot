import { useEffect, useState } from "react";
import {
  fetchAdminUser,
  patchAdminUser,
  type AdminUserCard as AdminUserCardType,
} from "../../../api";
import { t, type Locale } from "../../../i18n";
import { BackHead, GlassWait, Chevron } from "../../shared/lib";
import { ADMIN_USER_PLATFORMS } from "../../shared/constants";

export function AdminUserDetail({
  data,
  tgId,
  locale,
  onBack,
  onFail,
}: {
  data: string;
  tgId: number;
  locale: Locale;
  onBack: () => void;
  onFail: (err: unknown) => void;
}) {
  const [user, setUser] = useState<AdminUserCardType | null>(null);

  useEffect(() => {
    void fetchAdminUser(data, tgId).then(setUser).catch(onFail);
  }, [data, onFail, tgId]);

  return (
    <>
      <BackHead
        title={user?.name ?? t(locale, "adminUsers")}
        backLabel={t(locale, "back")}
        onBack={onBack}
      />
      {user == null ? (
        <GlassWait />
      ) : (
        <>
          <div className="glass-card">
            <div className="ios-row">
              <span>Telegram</span>
              <span className="ios-value">
                {user.username ? `${user.username} · ` : ""}id{user.tg_id}
              </span>
            </div>
            {user.xbox && (
              <div className="ios-row">
                <span>Xbox</span>
                <span className="ios-value">{String(user.xbox.name ?? "—")}</span>
              </div>
            )}
            {user.psn && (
              <div className="ios-row">
                <span>PSN</span>
                <span className="ios-value">{String(user.psn.name ?? "—")}</span>
              </div>
            )}
            {user.steam && (
              <div className="ios-row">
                <span>Steam</span>
                <span className="ios-value">{String(user.steam.name ?? "—")}</span>
              </div>
            )}
            <div className="ios-row">
              <span>{t(locale, "myChats")}</span>
              <span className="ios-value">
                {user.chats.join(", ") || t(locale, "notSubscribed")}
              </span>
            </div>
          </div>

          <div className="glass-card">
            {ADMIN_USER_PLATFORMS.map((platform) =>
              user[platform] && (
                <button
                  key={`sync-${platform}`}
                  type="button"
                  className="ios-row"
                  onClick={() =>
                    void patchAdminUser(data, user.tg_id, {
                      action: "sync",
                      platform,
                    })
                      .then(setUser)
                      .catch(onFail)
                  }
                >
                  <span>
                    {t(locale, "refresh")} {platform}
                  </span>
                  <span className="ios-value">
                    <Chevron />
                  </span>
                </button>
              ),
            )}
          </div>

          <div className="glass-card">
            {ADMIN_USER_PLATFORMS.map((platform) =>
              user[platform] && (
                <button
                  key={`reset-${platform}`}
                  type="button"
                  className="ios-row danger"
                  onClick={() => {
                    if (!window.confirm(t(locale, "confirmReset"))) return;
                    void patchAdminUser(data, user.tg_id, {
                      action: "reset",
                      platform,
                    })
                      .then(setUser)
                      .catch(onFail);
                  }}
                >
                  <span>
                    {t(locale, "reset")} {platform}
                  </span>
                </button>
              ),
            )}
            <button
              type="button"
              className="ios-row danger"
              onClick={() => {
                if (
                  !user.is_excluded &&
                  !window.confirm(t(locale, "confirmExclude"))
                )
                  return;
                void patchAdminUser(data, user.tg_id, {
                  excluded: !user.is_excluded,
                })
                  .then(setUser)
                  .catch(onFail);
              }}
            >
              <span>
                {user.is_excluded
                  ? t(locale, "restore")
                  : t(locale, "exclude")}
              </span>
            </button>
          </div>
        </>
      )}
    </>
  );
}
