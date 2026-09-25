import { useEffect, useState } from "react";
import {
  fetchAdminChats,
  patchAdminChat,
  postAdminChatAction,
  type AdminChatRow,
} from "../../../api";
import { formatOffset, t, timezoneLabel, type Locale } from "../../../i18n";
import { BackHead, GlassWait, Toggle, Chevron } from "../../shared/lib";
import {
  ADMIN_CHAT_ACTIONS,
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
      .then((r) =>
        setChat(r.chats.find((c) => c.chat_id === chatId) ?? null),
      )
      .catch(onFail);
  }, [chatId, data, onFail]);

  const onPatch = (body: Record<string, unknown>) => {
    if (!chat) return;
    void patchAdminChat(data, chat.chat_id, body).then(setChat).catch(onFail);
  };

  const onAction = (action: AdminChatAction) => {
    if (!chat) return;
    if (action.startsWith("wipe") && !window.confirm(t(locale, "confirmWipe"))) {
      return;
    }
    void postAdminChatAction(data, chat.chat_id, action)
      .then((r) =>
        onFlash(r.preview || `${t(locale, "deleteLast")}: ${r.deleted ?? 0}`),
      )
      .catch(onFail);
  };

  const tz = chat?.tz_offset_min;
  const tzOptions =
    tz != null && !TIMEZONES.some((z) => z.min === tz)
      ? [
          { min: tz, label: formatOffset(tz, locale) },
          ...TIMEZONES,
        ]
      : TIMEZONES;

  const title =
    chat?.title || String(chat?.chat_id ?? t(locale, "adminChats"));

  return (
    <>
      <BackHead title={title} backLabel={t(locale, "back")} onBack={onBack} />
      {chat == null ? (
        <GlassWait />
      ) : (
        <>
          <div className="glass-card">
            <div className="ios-row">
              <span>{t(locale, "chatEnabled")}</span>
              <Toggle
                on={chat.is_active}
                label={t(locale, "chatEnabled")}
                onClick={() => onPatch({ is_active: !chat.is_active })}
              />
            </div>
            <div className="ios-row">
              <span>{t(locale, "language")}</span>
              <div className="segment">
                <button
                  type="button"
                  className={chat.locale === "ru" ? "is-on" : undefined}
                  onClick={() => onPatch({ locale: "ru" })}
                >
                  RU
                </button>
                <button
                  type="button"
                  className={chat.locale === "en" ? "is-on" : undefined}
                  onClick={() => onPatch({ locale: "en" })}
                >
                  EN
                </button>
              </div>
            </div>
            <label className="ios-row">
              <span>{t(locale, "timezone")}</span>
              <select
                className="tz-select"
                value={tz}
                aria-label={t(locale, "timezone")}
                onChange={(e) =>
                  onPatch({ tz_offset_min: Number(e.target.value) })
                }
              >
                {tzOptions.map((z) => (
                  <option key={z.min} value={z.min}>
                    {timezoneLabel(z, locale)}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="glass-card admin-limits">
            <label className="ios-row admin-limit-row">
              <span className="admin-limit-copy">
                <strong>{t(locale, "threshold")}</strong>
              </span>
              <input
                className="admin-limit-input"
                defaultValue={String(chat.rare_threshold_percent)}
                inputMode="decimal"
                key={`thr:${chat.rare_threshold_percent}`}
                onBlur={(e) => {
                  const n = Number(e.target.value.replace(",", "."));
                  if (!Number.isNaN(n) && n !== chat.rare_threshold_percent) {
                    onPatch({ rare_threshold_percent: n });
                  }
                }}
              />
            </label>
            <label className="ios-row admin-limit-row">
              <span className="admin-limit-copy">
                <strong>{t(locale, "flood")}</strong>
                <small>{t(locale, "limitZeroOff")}</small>
              </span>
              <input
                className="admin-limit-input"
                defaultValue={String(chat.flood_limit)}
                inputMode="numeric"
                key={`flood:${chat.flood_limit}`}
                onBlur={(e) => {
                  const n = Number(e.target.value);
                  if (!Number.isNaN(n) && n !== chat.flood_limit) {
                    onPatch({ flood_limit: n });
                  }
                }}
              />
            </label>
            <label className="ios-row admin-limit-row">
              <span className="admin-limit-copy">
                <strong>{t(locale, "floodWindow")}</strong>
              </span>
              <input
                className="admin-limit-input"
                defaultValue={String(chat.flood_window_minutes)}
                inputMode="numeric"
                key={`win:${chat.flood_window_minutes}`}
                onBlur={(e) => {
                  const n = Number(e.target.value);
                  if (!Number.isNaN(n) && n !== chat.flood_window_minutes) {
                    onPatch({ flood_window_minutes: n });
                  }
                }}
              />
            </label>
            <label className="ios-row admin-limit-row">
              <span className="admin-limit-copy">
                <strong>{t(locale, "minScore")}</strong>
              </span>
              <input
                className="admin-limit-input"
                defaultValue={String(chat.min_gamerscore)}
                inputMode="numeric"
                key={`min:${chat.min_gamerscore}`}
                onBlur={(e) => {
                  const n = Number(e.target.value);
                  if (!Number.isNaN(n) && n !== chat.min_gamerscore) {
                    onPatch({ min_gamerscore: n });
                  }
                }}
              />
            </label>
          </div>

          <div className="glass-card">
            <button
              type="button"
              className="ios-row"
              onClick={() => onAction(ADMIN_CHAT_ACTIONS.DELETE_LAST)}
            >
              <span>{t(locale, "deleteLast")}</span>
              <span className="ios-value">
                <Chevron />
              </span>
            </button>
            <button
              type="button"
              className="ios-row danger"
              onClick={() => onAction(ADMIN_CHAT_ACTIONS.WIPE_24H)}
            >
              <span>{t(locale, "wipe24h")}</span>
            </button>
            <button
              type="button"
              className="ios-row danger"
              onClick={() => onAction(ADMIN_CHAT_ACTIONS.WIPE_SYSTEM_24H)}
            >
              <span>{t(locale, "wipeSystem24h")}</span>
            </button>
            <button
              type="button"
              className="ios-row danger"
              onClick={() => onAction(ADMIN_CHAT_ACTIONS.WIPE_SYSTEM_ALL)}
            >
              <span>{t(locale, "wipeSystemAll")}</span>
            </button>
          </div>
        </>
      )}
    </>
  );
}
