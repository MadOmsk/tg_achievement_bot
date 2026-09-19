import { useEffect, useState } from "react";
import {
  deleteAdminKey,
  fetchAdminChats,
  fetchAdminDefaults,
  fetchAdminHome,
  fetchAdminKeys,
  fetchAdminLimits,
  fetchAdminUser,
  fetchAdminUsers,
  patchAdminChat,
  patchAdminDefaults,
  patchAdminLimit,
  patchAdminUser,
  postAdminChatAction,
  putAdminKey,
  type AdminChatRow,
  type AdminDefaults,
  type AdminHome,
  type AdminKeys,
  type AdminLimit,
  type AdminUserCard,
  type AdminUserRow,
} from "./api";
import { formatOffset, rarityLabel, t, type Locale } from "./i18n";
import { TIMEZONES } from "./Me";
import { BackHead, GlassWait, PlatformLogo, Toggle } from "./ui";

type AdminScreen =
  | { name: "home" }
  | { name: "keys" }
  | { name: "limits" }
  | { name: "defaults" }
  | { name: "users" }
  | { name: "user"; tgId: number }
  | { name: "chats" }
  | { name: "chat"; chatId: number };

export function Admin({
  locale,
  data,
  onBack,
  onFlash,
}: {
  locale: Locale;
  data: string;
  onBack?: () => void;
  onFlash: (message: string) => void;
}) {
  const [screen, setScreen] = useState<AdminScreen>({ name: "home" });
  const [home, setHome] = useState<AdminHome | null>(null);
  const [keys, setKeys] = useState<AdminKeys | null>(null);
  const [limits, setLimits] = useState<AdminLimit[]>([]);
  const [defaults, setDefaults] = useState<AdminDefaults | null>(null);
  const [users, setUsers] = useState<AdminUserRow[] | null>(null);
  const [userChats, setUserChats] = useState<Array<{ chat_id: number; title: string | null }>>([]);
  const [peopleChat, setPeopleChat] = useState("");
  const [user, setUser] = useState<AdminUserCard | null>(null);
  const [chats, setChats] = useState<AdminChatRow[] | null>(null);
  const [chat, setChat] = useState<AdminChatRow | null>(null);
  const [secret, setSecret] = useState("");
  const [keyName, setKeyName] = useState<"steam" | "psn" | "anthropic" | null>(null);

  const fail = (err: unknown) => onFlash(`${t(locale, "error")}: ${String(err)}`);

  useEffect(() => {
    void fetchAdminHome(data).then(setHome).catch(fail);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  useEffect(() => {
    if (screen.name === "keys") {
      setKeys(null);
      setKeyName(null);
      setSecret("");
      void fetchAdminKeys(data).then(setKeys).catch(fail);
    }
    if (screen.name === "limits") {
      void fetchAdminLimits(data)
        .then((r) => setLimits(r.items))
        .catch(fail);
    }
    if (screen.name === "defaults") {
      setDefaults(null);
      void fetchAdminDefaults(data).then(setDefaults).catch(fail);
    }
    if (screen.name === "users") {
      setUsers(null);
      void fetchAdminUsers(data)
        .then((r) => {
          setUsers(r.users);
          setUserChats(r.chats ?? []);
        })
        .catch(fail);
    }
    if (screen.name === "user") {
      setUser(null);
      void fetchAdminUser(data, screen.tgId).then(setUser).catch(fail);
    }
    if (screen.name === "chats") {
      setChats(null);
      void fetchAdminChats(data)
        .then((r) => setChats(r.chats))
        .catch(fail);
    }
    if (screen.name === "chat") {
      setChat(null);
      void fetchAdminChats(data)
        .then((r) => setChat(r.chats.find((c) => c.chat_id === screen.chatId) ?? null))
        .catch(fail);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screen, data]);

  const title =
    screen.name === "home"
      ? t(locale, "adminHome")
      : screen.name === "keys"
        ? t(locale, "adminKeys")
        : screen.name === "limits"
          ? t(locale, "adminLimits")
          : screen.name === "defaults"
            ? t(locale, "adminDefaults")
            : screen.name === "users"
              ? t(locale, "adminUsers")
              : screen.name === "user"
                ? (user?.name ?? t(locale, "adminUsers"))
                : screen.name === "chats"
                  ? t(locale, "adminChats")
                  : (chat?.title || String(chat?.chat_id ?? t(locale, "adminChats")));

  const goBack = () => {
    if (screen.name === "home") onBack?.();
    else if (screen.name === "user") setScreen({ name: "users" });
    else if (screen.name === "chat") setScreen({ name: "chats" });
    else setScreen({ name: "home" });
  };

  return (
    <>
      <BackHead title={title} backLabel={t(locale, "back")} onBack={goBack} />
      {screen.name === "home" ? (
        <>
          <p className="kicker">{t(locale, "general")}</p>
          <div className="glass-card">
            <button type="button" className="ios-row" onClick={() => setScreen({ name: "users" })}>
              <span>{t(locale, "adminUsers")}</span>
              <span className="ios-value">›</span>
            </button>
            <button type="button" className="ios-row" onClick={() => setScreen({ name: "chats" })}>
              <span>{t(locale, "adminChats")}</span>
              <span className="ios-value">›</span>
            </button>
            <button type="button" className="ios-row" onClick={() => setScreen({ name: "keys" })}>
              <span>{t(locale, "adminKeys")}</span>
              <span className="ios-value">›</span>
            </button>
            <button type="button" className="ios-row" onClick={() => setScreen({ name: "limits" })}>
              <span>{t(locale, "adminLimits")}</span>
              <span className="ios-value">›</span>
            </button>
            <button type="button" className="ios-row" onClick={() => setScreen({ name: "defaults" })}>
              <span>{t(locale, "adminDefaults")}</span>
              <span className="ios-value">›</span>
            </button>
          </div>
          {home ? (
            <>
              <p className="kicker">{t(locale, "usage")}</p>
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
            </>
          ) : null}
        </>
      ) : null}

      {screen.name === "keys" ? (
        keys == null ? (
          <GlassWait />
        ) : (
        <>
          <div className="glass-card">
            {(["steam", "psn", "anthropic"] as const).map((name) => (
              <button
                key={name}
                type="button"
                className="ios-row"
                onClick={() => {
                  setKeyName(name);
                  setSecret("");
                }}
              >
                <span>
                  {t(
                    locale,
                    name === "steam" ? "keySteam" : name === "psn" ? "keyPsn" : "keyAnthropic",
                  )}
                </span>
                <span className="ios-value">
                  {keys[name] ? t(locale, "keySet") : t(locale, "keyUnset")} ›
                </span>
              </button>
            ))}
          </div>
          {keyName ? (
            <div className="glass-card">
              <div className="ios-row">
                <span className="admin-limit-copy">
                  <strong>
                    {t(
                      locale,
                      keyName === "steam"
                        ? "keySteam"
                        : keyName === "psn"
                          ? "keyPsn"
                          : "keyAnthropic",
                    )}
                  </strong>
                  <small>{t(locale, "pasteKey")}</small>
                </span>
              </div>
              <label className="ios-row">
                <input
                  className="admin-secret-input"
                  value={secret}
                  onChange={(e) => setSecret(e.target.value)}
                  autoComplete="off"
                  aria-label={t(locale, "pasteKey")}
                />
              </label>
              <button
                type="button"
                className="ios-row"
                disabled={!secret.trim()}
                onClick={() => {
                  void putAdminKey(data, keyName, secret.trim())
                    .then((next) => {
                      setKeys(next);
                      setSecret("");
                      setKeyName(null);
                    })
                    .catch(fail);
                }}
              >
                <span>{t(locale, "save")}</span>
                <span className="ios-value">›</span>
              </button>
              {keys[keyName] ? (
                <button
                  type="button"
                  className="ios-row danger"
                  onClick={() => {
                    if (!window.confirm(t(locale, "confirmClear"))) return;
                    void deleteAdminKey(data, keyName)
                      .then((next) => {
                        setKeys(next);
                        setKeyName(null);
                        setSecret("");
                      })
                      .catch(fail);
                  }}
                >
                  <span>{t(locale, "clearKey")}</span>
                </button>
              ) : null}
              <button
                type="button"
                className="ios-row"
                onClick={() => {
                  setKeyName(null);
                  setSecret("");
                }}
              >
                <span>{t(locale, "cancel")}</span>
              </button>
            </div>
          ) : null}
        </>
        )
      ) : null}

      {screen.name === "limits" ? (
        <div className="glass-card admin-limits">
          {limits.map((item) => {
            const hint =
              item.zero_means === "unlimited"
                ? t(locale, "limitZeroUnlimited")
                : item.zero_means === "off"
                  ? t(locale, "limitZeroOff")
                  : null;
            return (
              <label key={item.key} className="ios-row admin-limit-row">
                <span className="admin-limit-copy">
                  <strong>{item.label}</strong>
                  {hint ? <small>{hint}</small> : null}
                </span>
                <input
                  className="admin-limit-input"
                  type="number"
                  defaultValue={String(item.value)}
                  min={item.min}
                  max={item.max}
                  inputMode="numeric"
                  key={`${item.key}:${item.value}`}
                  onBlur={(e) => {
                    const n = Number(e.target.value);
                    if (Number.isNaN(n) || n === item.value) return;
                    const clamped = Math.min(item.max, Math.max(item.min, Math.trunc(n)));
                    void patchAdminLimit(data, item.key, clamped)
                      .then((r) => setLimits(r.items))
                      .catch(fail);
                  }}
                />
              </label>
            );
          })}
        </div>
      ) : null}

      {screen.name === "defaults" ? (
        defaults == null ? (
          <GlassWait />
        ) : (
          <div className="glass-card">
            <label className="ios-row">
              <span>{t(locale, "defaultsRarity")}</span>
              <select
                className="tz-select"
                value={defaults.rarity_mode}
                aria-label={t(locale, "defaultsRarity")}
                onChange={(e) =>
                  void patchAdminDefaults(data, { rarity_mode: e.target.value })
                    .then(setDefaults)
                    .catch(fail)
                }
              >
                <option value="all">{rarityLabel("all", locale)}</option>
                <option value="rare">{rarityLabel("rare", locale)}</option>
                <option value="hidden">{rarityLabel("hidden", locale)}</option>
              </select>
            </label>
            <div className="ios-row">
              <span>{t(locale, "defaultsLinks")}</span>
              <Toggle
                on={defaults.show_profile_links}
                label={t(locale, "defaultsLinks")}
                onClick={() =>
                  void patchAdminDefaults(data, {
                    show_profile_links: !defaults.show_profile_links,
                  })
                    .then(setDefaults)
                    .catch(fail)
                }
              />
            </div>
          </div>
        )
      ) : null}

      {screen.name === "users" ? (
        users == null ? (
          <GlassWait />
        ) : (
          <>
            {userChats.length > 0 ? (
              <div className="glass-card">
                <label className="ios-row">
                  <span>{t(locale, "adminChats")}</span>
                  <select
                    className="tz-select"
                    value={peopleChat}
                    onChange={(e) => setPeopleChat(e.target.value)}
                    aria-label={t(locale, "adminChats")}
                  >
                    <option value="">{t(locale, "allChats")}</option>
                    {userChats.map((c) => (
                      <option key={c.chat_id} value={c.chat_id}>
                        {c.title || `chat ${c.chat_id}`}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            ) : null}
            {users.filter((row) =>
              peopleChat === "" ? true : (row.chat_ids ?? []).includes(Number(peopleChat)),
            ).length === 0 ? (
              <p className="empty">{t(locale, "noUsers")}</p>
            ) : (
              <div className="glass-card">
                {users
                  .filter((row) =>
                    peopleChat === "" ? true : (row.chat_ids ?? []).includes(Number(peopleChat)),
                  )
                  .map((row) => (
                    <button
                      key={row.tg_id}
                      type="button"
                      className="ios-row admin-user-row"
                      onClick={() => setScreen({ name: "user", tgId: row.tg_id })}
                    >
                      <span className="admin-limit-copy">
                        <strong>{row.name}</strong>
                        <small>
                          {row.today} / {row.month}
                          {row.is_excluded ? ` · ${t(locale, "excluded")}` : ""}
                        </small>
                      </span>
                      <span className="admin-plats">
                        {row.xbox ? <PlatformLogo platform="xbox" size={18} /> : null}
                        {row.psn ? <PlatformLogo platform="psn" size={18} /> : null}
                        {row.steam ? <PlatformLogo platform="steam" size={18} /> : null}
                        <span className="ios-value">›</span>
                      </span>
                    </button>
                  ))}
              </div>
            )}
          </>
        )
      ) : null}

      {screen.name === "user" ? (
        user == null ? (
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
            {user.xbox ? (
              <div className="ios-row">
                <span>Xbox</span>
                <span className="ios-value">{String(user.xbox.name ?? "—")}</span>
              </div>
            ) : null}
            {user.psn ? (
              <div className="ios-row">
                <span>PSN</span>
                <span className="ios-value">{String(user.psn.name ?? "—")}</span>
              </div>
            ) : null}
            {user.steam ? (
              <div className="ios-row">
                <span>Steam</span>
                <span className="ios-value">{String(user.steam.name ?? "—")}</span>
              </div>
            ) : null}
            <div className="ios-row">
              <span>{t(locale, "myChats")}</span>
              <span className="ios-value">{user.chats.join(", ") || t(locale, "notSubscribed")}</span>
            </div>
          </div>
          <div className="glass-card">
            {(["xbox", "psn", "steam"] as const).map((platform) =>
              user[platform] ? (
                <button
                  key={`sync-${platform}`}
                  type="button"
                  className="ios-row"
                  onClick={() =>
                    void patchAdminUser(data, user.tg_id, { action: "sync", platform })
                      .then(setUser)
                      .catch(fail)
                  }
                >
                  <span>
                    {t(locale, "refresh")} {platform}
                  </span>
                  <span className="ios-value">›</span>
                </button>
              ) : null,
            )}
          </div>
          <div className="glass-card">
            {(["xbox", "psn", "steam"] as const).map((platform) =>
              user[platform] ? (
                <button
                  key={`reset-${platform}`}
                  type="button"
                  className="ios-row danger"
                  onClick={() => {
                    if (!window.confirm(t(locale, "confirmReset"))) return;
                    void patchAdminUser(data, user.tg_id, { action: "reset", platform })
                      .then(setUser)
                      .catch(fail);
                  }}
                >
                  <span>
                    {t(locale, "reset")} {platform}
                  </span>
                </button>
              ) : null,
            )}
            <button
              type="button"
              className="ios-row danger"
              onClick={() => {
                if (!user.is_excluded && !window.confirm(t(locale, "confirmExclude"))) return;
                void patchAdminUser(data, user.tg_id, { excluded: !user.is_excluded })
                  .then(setUser)
                  .catch(fail);
              }}
            >
              <span>{user.is_excluded ? t(locale, "restore") : t(locale, "exclude")}</span>
            </button>
          </div>
        </>
        )
      ) : null}

      {screen.name === "chats" ? (
        chats == null ? (
          <GlassWait />
        ) : chats.length === 0 ? (
          <p className="empty">{t(locale, "noChats")}</p>
        ) : (
          <div className="glass-card">
            {chats.map((row) => (
              <button
                key={row.chat_id}
                type="button"
                className={`ios-row admin-user-row${row.is_active ? "" : " is-off"}`}
                onClick={() => setScreen({ name: "chat", chatId: row.chat_id })}
              >
                <span className="admin-limit-copy">
                  <strong>{row.title || row.chat_id}</strong>
                  <small>
                    {row.subscribers} {t(locale, "subscribers")} · {row.rare_threshold_percent}%
                  </small>
                </span>
                <span className={`admin-chat-state${row.is_active ? " is-on" : ""}`}>
                  {row.is_active ? t(locale, "on") : t(locale, "off")}
                </span>
                <span className="ios-value">›</span>
              </button>
            ))}
          </div>
        )
      ) : null}

      {screen.name === "chat" ? (
        chat == null ? (
          <GlassWait />
        ) : (
        <AdminChatCard
          chat={chat}
          locale={locale}
          onPatch={(body) =>
            void patchAdminChat(data, chat.chat_id, body).then(setChat).catch(fail)
          }
          onAction={(action) => {
            if (action.startsWith("wipe") && !window.confirm(t(locale, "confirmWipe"))) return;
            void postAdminChatAction(data, chat.chat_id, action)
              .then((r) => onFlash(r.preview || `${t(locale, "deleteLast")}: ${r.deleted ?? 0}`))
              .catch(fail);
          }}
        />
        )
      ) : null}
    </>
  );
}

function AdminChatCard({
  chat,
  locale,
  onPatch,
  onAction,
}: {
  chat: AdminChatRow;
  locale: Locale;
  onPatch: (body: Record<string, unknown>) => void;
  onAction: (action: string) => void;
}) {
  const tz = chat.tz_offset_min;
  const tzOptions =
    tz != null && !TIMEZONES.some((z) => z.min === tz)
      ? [{ min: tz, ru: formatOffset(tz, "ru"), en: formatOffset(tz, "en") }, ...TIMEZONES]
      : TIMEZONES;

  return (
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
            onChange={(e) => onPatch({ tz_offset_min: Number(e.target.value) })}
          >
            {tzOptions.map((z) => (
              <option key={z.min} value={z.min}>
                {locale === "en" ? z.en : z.ru}
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
              if (!Number.isNaN(n) && n !== chat.flood_limit) onPatch({ flood_limit: n });
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
              if (!Number.isNaN(n) && n !== chat.min_gamerscore) onPatch({ min_gamerscore: n });
            }}
          />
        </label>
      </div>
      <div className="glass-card">
        <button type="button" className="ios-row" onClick={() => onAction("delete_last")}>
          <span>{t(locale, "deleteLast")}</span>
          <span className="ios-value">›</span>
        </button>
        <button type="button" className="ios-row danger" onClick={() => onAction("wipe_24h")}>
          <span>{t(locale, "wipe24h")}</span>
        </button>
        <button type="button" className="ios-row danger" onClick={() => onAction("wipe_system_24h")}>
          <span>{t(locale, "wipeSystem24h")}</span>
        </button>
        <button type="button" className="ios-row danger" onClick={() => onAction("wipe_system_all")}>
          <span>{t(locale, "wipeSystemAll")}</span>
        </button>
      </div>
    </>
  );
}
