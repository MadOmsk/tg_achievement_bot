import { useState } from "react";
import {
  adminApi,
  ApiError,
  type AdminAction,
  type AdminCredential,
  type AdminSetting,
  type AdminSettings,
} from "../../api";
import { useApp } from "../../app/context";
import { useLoad } from "../../app/useLoad";
import { ADMIN_SCREENS, type AdminScreen } from "../../core/constants";
import { formatWhen, num } from "../../i18n";
import { Button, Empty, Field, Group, Row, Toggle } from "../../ui/Controls";
import { Face } from "../../ui/Face";
import { Icon } from "../../ui/Icon";
import { Confirm, Page, Sheet } from "../../ui/Page";
import "../settings/Settings.css";
import "../people/People.css";
import "./Admin.css";

export function AdminPage({ screen, onClose, layer }: { screen: AdminScreen | null; onClose: () => void; layer: string }) {
  const { tr } = useApp();
  const title = !screen
    ? tr("admin")
    : screen.name === ADMIN_SCREENS.KEYS
      ? tr("adminKeys")
      : screen.name === ADMIN_SCREENS.SETTINGS
        ? tr("adminSettings")
        : screen.name === ADMIN_SCREENS.USERS || screen.name === ADMIN_SCREENS.USER
          ? tr("adminUsers")
          : tr("adminChats");
  return (
    <Page title={title} onBack={onClose} layer={layer} className="admin">
      {!screen && <AdminHomeView />}
      {screen?.name === ADMIN_SCREENS.KEYS && <KeysView />}
      {screen?.name === ADMIN_SCREENS.SETTINGS && <GlobalSettingsView />}
      {screen?.name === ADMIN_SCREENS.USERS && <UsersView />}
      {screen?.name === ADMIN_SCREENS.USER && <UserView personId={screen.personId} onGone={onClose} />}
      {screen?.name === ADMIN_SCREENS.CHATS && <ChatsView />}
      {screen?.name === ADMIN_SCREENS.CHAT && <ChatView chatId={screen.chatId} onGone={onClose} />}
    </Page>
  );
}

/** A list on its way: a few of its rows, each one block. */
function RowsSkel() {
  return (
    <div className="group" aria-hidden="true">
      <div className="group-items">
        {[0, 1, 2].map((i) => (
          <span key={i} className="row skel" style={{ height: 72 }} />
        ))}
      </div>
    </div>
  );
}

function AdminHomeView() {
  const { me } = useApp();
  // A chat admin's panel is their chats alone (#232).
  return me.is_superadmin ? <AppAdminHomeView /> : <ChatsView />;
}

function AppAdminHomeView() {
  const { data, tr, open, locale, me } = useApp();
  const home = useLoad("admin-home", () => adminApi.fetchHome(data));
  const h = home.data;
  return (
    <>
      {h && (
        <div className="adm-counts">
          {(
            [
              [h.users, tr("adminUsers")],
              [h.xbox_linked, "Xbox"],
              [h.psn_linked, "PlayStation"],
              [h.steam_linked, "Steam"],
              [h.chats, tr("adminChats")],
            ] as const
          ).map(([n, label]) => (
            <div key={label}>
              <b className="t-num">{num(n, locale)}</b>
              <span>{label}</span>
            </div>
          ))}
        </div>
      )}
      {!h && home.loading && (
        <div className="adm-counts" aria-hidden="true">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="skel" />
          ))}
        </div>
      )}
      <Group>
        {me.role === "superadmin" && (
          <Row lead={<Icon name="key" />} title={tr("adminKeys")} sub={tr("adminKeysSub")} chevron onClick={() => open({ kind: "admin", screen: { name: ADMIN_SCREENS.KEYS } })} />
        )}
        <Row lead={<Icon name="settings" />} title={tr("adminSettings")} sub={tr("adminSettingsSub")} chevron onClick={() => open({ kind: "admin", screen: { name: ADMIN_SCREENS.SETTINGS } })} />
        <Row lead={<Icon name="people" />} title={tr("adminUsers")} sub={tr("adminUsersSub")} chevron onClick={() => open({ kind: "admin", screen: { name: ADMIN_SCREENS.USERS } })} />
        <Row lead={<Icon name="share" />} title={tr("adminChats")} sub={tr("adminChatsSub")} chevron onClick={() => open({ kind: "admin", screen: { name: ADMIN_SCREENS.CHATS } })} />
      </Group>
      {h && (
        <Group title={tr("groupGeneral")}>
          {h.credentials.map((c) => (
            <CredentialRow key={c.name} c={c} />
          ))}
          <Row
            lead={<Icon name="mail" />}
            title={h.mail.server ?? tr("emailUnavailable")}
            sub={`${h.mail.hour}/${h.mail.hour_limit} · ${h.mail.day}/${h.mail.day_limit}`}
          />
        </Group>
      )}
      {h && h.usage.length > 0 && (
        <Group title={tr("groupApi")}>
          {h.usage.map((u) => (
            <Row key={u.label} title={u.label} sub={u.value} />
          ))}
        </Group>
      )}
    </>
  );
}

function CredentialRow({ c, onClick }: { c: AdminCredential; onClick?: () => void }) {
  const { tr, locale } = useApp();
  const state = !c.configured ? tr("keyUnset") : c.status === "invalid" ? tr("keyDead") : tr("keySet");
  return (
    <Row
      lead={<span className={`adm-dot${!c.configured ? "" : c.status === "invalid" ? " adm-dot-bad" : " adm-dot-ok"}`} />}
      title={c.label}
      sub={`${state}${c.checked_at ? ` · ${formatWhen(c.checked_at, locale)}` : ""}`}
      chevron={Boolean(onClick)}
      onClick={onClick}
    />
  );
}

function KeysView() {
  const { data, tr, toast, locale, open } = useApp();
  const keys = useLoad("admin-keys", () => adminApi.fetchKeys(data));
  const [edit, setEdit] = useState<AdminCredential | null>(null);
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [clear, setClear] = useState<AdminCredential | null>(null);
  return (
    <>
      <Group>
        {(keys.data?.keys ?? []).map((c) => (
          <CredentialRow
            key={c.name}
            c={c}
            onClick={() => {
              setEdit(c);
              setValue("");
              setError(null);
            }}
          />
        ))}
      </Group>
      {keys.data?.psn_tokens && (
        <Group title={tr("adminPsnTokens")}>
          {keys.data.psn_tokens.accounts.map((t) => (
            <Row
              key={t.account_id}
              lead={<span className={`adm-dot ${t.status === "active" ? "adm-dot-ok" : "adm-dot-bad"}`} />}
              title={t.name}
              sub={`${t.who} · ${t.status === "active" ? `${tr("psnTokenChecked")} ${formatWhen(t.checked_at ?? "", locale)}` : `${tr("psnTokenDeadSince")} ${formatWhen(t.dead_at ?? "", locale)}`}`}
              chevron
              onClick={() => open({ kind: "admin", screen: { name: ADMIN_SCREENS.USER, personId: t.person_id } })}
            />
          ))}
          <Row title={tr("adminPsnTokensShared").replace("{count}", String(keys.data.psn_tokens.shared))} sub={tr("adminPsnTokensNote")} />
        </Group>
      )}
      {edit && (
        <Sheet title={edit.label} onClose={() => setEdit(null)} layer="key">
          <form
            className="adm-sheet"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError(null);
              try {
                keys.set(await adminApi.putKey(data, edit.name, value.trim()));
                setEdit(null);
              } catch (err) {
                setError(err instanceof ApiError && err.status === 400 ? tr("keyInvalid") : tr("keySetupError"));
              } finally {
                setBusy(false);
              }
            }}
          >
            <p className="t-body">
              {!edit.configured ? tr("keyUnset") : edit.status === "invalid" ? tr("keyDead") : tr("keySet")}
              {edit.checked_at ? ` · ${formatWhen(edit.checked_at, locale)}` : ""}
            </p>
            {edit.usage && <p className="t-meta">{`${tr("adminKeyRequests")}: ${edit.usage}`}</p>}
            <p className="t-body">{edit.hint}</p>
            <Field
              type="password"
              autoComplete="off"
              placeholder={tr("keyNew")}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              hint={tr("pasteKey")}
              error={error}
            />
            <div className="set-buttons">
              {edit.configured && (
                <Button
                  variant="text"
                  onClick={() => {
                    setClear(edit);
                    setEdit(null);
                  }}
                >
                  {tr("clearKey")}
                </Button>
              )}
              <Button type="submit" busy={busy} disabled={!value.trim()}>
                {tr("setKey")}
              </Button>
            </div>
          </form>
        </Sheet>
      )}
      {clear && (
        <Confirm
          text={`${tr("confirmClear")}\n${clear.label}`}
          yes={tr("clearKey")}
          no={tr("cancel")}
          danger
          onYes={async () => {
            const c = clear;
            setClear(null);
            try {
              keys.set(await adminApi.deleteKey(data, c.name));
            } catch {
              toast(tr("somethingWrong"), "error");
            }
          }}
          onNo={() => setClear(null)}
        />
      )}
    </>
  );
}

/** One setting of the server's registry, drawn by its kind. */
function SettingRow({ s, onSave }: { s: AdminSetting; onSave: (value: AdminSetting["value"]) => Promise<void> }) {
  const { tr } = useApp();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(String(s.value));
  const [error, setError] = useState<string | null>(null);
  const shown =
    s.options.find((o) => o.value === s.value)?.label ??
    (s.value === 0 && s.zero_means
      ? tr(s.zero_means === "unlimited" ? "limitZeroUnlimited" : s.zero_means === "off" ? "limitZeroOff" : "limitZeroNoDelay")
      : String(s.value));
  if (s.kind === "bool") {
    return <Row title={s.label} sub={s.hint} trail={<Toggle checked={Boolean(s.value)} label={s.label} onChange={(v) => void onSave(v)} />} />;
  }
  const options =
    s.options.length > 0
      ? s.options
      : s.kind === "hour"
        ? Array.from({ length: 24 }, (_, h) => ({ value: h, label: `${String(h).padStart(2, "0")}:00` }))
        : null;
  return (
    <>
      <Row title={s.label} sub={s.hint} trail={<span className="adm-value">{shown}</span>} chevron onClick={() => setOpen(true)} />
      {open && (
        <Sheet title={s.label} onClose={() => setOpen(false)} layer={`set:${s.key}`}>
          {options ? (
            <div className="set-list">
              {options.map((o) => (
                <button
                  key={String(o.value)}
                  type="button"
                  className={`set-pick${o.value === s.value ? " set-pick-on" : ""}`}
                  onClick={async () => {
                    setOpen(false);
                    await onSave(o.value);
                  }}
                >
                  {o.label}
                  {o.value === s.value && <Icon name="check" size={20} />}
                </button>
              ))}
            </div>
          ) : (
            <form
              className="adm-sheet"
              onSubmit={async (e) => {
                e.preventDefault();
                const n = Number(text.replace(",", "."));
                if (!text.trim() || Number.isNaN(n)) return setError(tr("valueInvalid"));
                try {
                  await onSave(s.kind === "int" ? Math.round(n) : n);
                  setOpen(false);
                } catch {
                  setError(tr("valueInvalid"));
                }
              }}
            >
              {s.hint && <p className="t-body">{s.hint}</p>}
              <Field
                inputMode="decimal"
                value={text}
                onChange={(e) => setText(e.target.value)}
                error={error}
                hint={[
                  s.min != null || s.max != null ? `${s.min ?? ""}…${s.max ?? ""}` : null,
                  s.zero_means
                    ? tr(s.zero_means === "unlimited" ? "limitZeroUnlimited" : s.zero_means === "off" ? "limitZeroOff" : "limitZeroNoDelay")
                    : null,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              />
              <Button type="submit">{tr("save")}</Button>
            </form>
          )}
        </Sheet>
      )}
    </>
  );
}

function SettingsGroups({ settings, save }: { settings: AdminSettings; save: (key: string, value: AdminSetting["value"]) => Promise<void> }) {
  return (
    <>
      {settings.groups.map((g) => (
        <Group key={g.id} title={g.title}>
          {g.items.map((s) => (
            <SettingRow key={s.key} s={s} onSave={(v) => save(s.key, v)} />
          ))}
        </Group>
      ))}
    </>
  );
}

function GlobalSettingsView() {
  const { data, tr, toast } = useApp();
  const settings = useLoad("admin-settings", () => adminApi.fetchSettings(data));
  const actions = useLoad("admin-actions-global", () => adminApi.fetchActions(data, "global", "all"));
  if (!settings.data) return settings.loading ? <RowsSkel /> : <Empty icon="refresh" title={tr("loadFailed")} />;
  return (
    <>
      <SettingsGroups
        settings={settings.data}
        save={async (key, value) => {
          try {
            settings.set(await adminApi.patchSetting(data, key, value));
          } catch (err) {
            toast(tr("somethingWrong"), "error");
            throw err;
          }
        }}
      />
      {(actions.data?.actions.length ?? 0) > 0 && <Actions actions={actions.data!.actions} onDone={actions.reload} onGone={() => undefined} />}
    </>
  );
}

function UsersView() {
  const { data, tr, open, locale } = useApp();
  const users = useLoad("admin-users", () => adminApi.fetchUsers(data));
  const [q, setQ] = useState("");
  const list = (users.data?.users ?? []).filter((u) => !q || u.name.toLowerCase().includes(q.toLowerCase()));
  return (
    <>
      <div className="fl-search">
        <Field icon="search" placeholder={tr("searchPeople")} value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {!users.data && users.loading && <RowsSkel />}
      {users.data && list.length === 0 && <Empty icon="people" title={tr("noUsers")} />}
      <Group>
        {list.map((u) => (
          <Row
            key={u.person_id}
            lead={<Face personId={u.person_id} name={u.name} size={40} dim={u.is_excluded} />}
            title={u.role === "superadmin" ? `${u.name} 👑` : u.role === "admin" ? `${u.name} ⭐` : u.name}
            sub={[
              [u.xbox && "Xbox", u.psn && "PS", u.steam && "Steam"].filter(Boolean).join(" · ") || tr("noPlatformsShort"),
              `${tr("usersToday")} ${u.today} · ${tr("usersMonth")} ${u.month}`,
              u.last_online_at ? formatWhen(u.last_online_at, locale) : null,
            ]
              .filter(Boolean)
              .join(" · ")}
            chevron
            onClick={() => open({ kind: "admin", screen: { name: ADMIN_SCREENS.USER, personId: u.person_id } })}
          />
        ))}
      </Group>
    </>
  );
}

function UserView({ personId, onGone }: { personId: number; onGone: () => void }) {
  const { data, tr, locale } = useApp();
  const card = useLoad(`admin-user:${personId}`, () => adminApi.fetchUser(data, personId));
  const actions = useLoad(`admin-actions-user:${personId}`, () => adminApi.fetchActions(data, "user", `p${personId}`));
  const c = card.data;
  if (!c) return card.loading ? <RowsSkel /> : <Empty icon="refresh" title={tr("loadFailed")} />;
  const platform = (label: string, info: Record<string, unknown> | null) =>
    info ? (
      <Group key={label} title={label}>
        {Object.entries(info)
          .filter(([, v]) => v !== null && v !== "" && typeof v !== "object")
          .map(([k, v]) => (
            <Row key={k} title={String(v)} sub={k} />
          ))}
      </Group>
    ) : null;
  return (
    <>
      <div className="adm-person">
        <Face personId={c.person_id} name={c.name} size={72} dim={c.is_excluded} />
        <p className="t-title">{c.name}</p>
        <p className="t-meta">id {c.person_id}</p>
      </div>
      <Group title={tr("adminLoginsGroup")}>
        {c.logins.map((l) => (
          <Row key={l.kind} title={l.label} sub={l.linked ? (l.value ?? tr("telegramLinked")) : "— " + tr("keyUnset")} />
        ))}
      </Group>
      {platform("Xbox", c.xbox)}
      {platform("PlayStation", c.psn)}
      {Array.isArray(c.psn?.accounts) && (
        <Group title={tr("adminPsnTokens")}>
          {(c.psn.accounts as Array<{ external_id: string; name: string | null; token?: string | null; token_checked_at?: string | null }>).map((a) => (
            <Row
              key={a.external_id}
              lead={<Icon name="key" />}
              title={a.name ?? a.external_id}
              sub={a.token === "active" ? `${tr("psnTokenOwn")} · ${formatWhen(a.token_checked_at ?? "", locale)}` : a.token === "dead" ? tr("psnTokenDeadShort") : tr("psnTokenShared")}
            />
          ))}
        </Group>
      )}
      {platform("Steam", c.steam)}
      <Group title={tr("publishing")}>
        <Row title={c.rarity.title} sub={c.rarity.value} />
        {c.chats.map((name) => (
          <Row key={name} title={name} />
        ))}
      </Group>
      {actions.data && <Actions actions={actions.data.actions} onGone={onGone} onDone={card.reload} />}
    </>
  );
}

function ChatsView() {
  const { data, tr, open } = useApp();
  const chats = useLoad("admin-chats", () => adminApi.fetchChats(data));
  return (
    <>
      {!chats.data && chats.loading && <RowsSkel />}
      <Group>
        {(chats.data?.chats ?? []).map((c) => (
          <Row
            key={c.chat_id}
            lead={<span className={`adm-dot${c.is_active ? " adm-dot-ok" : ""}`} />}
            title={c.title ?? String(c.chat_id)}
            sub={`${c.is_active ? tr("chatActive") : tr("chatInactive")} · ${c.subscribers} ${tr("subscribers")}`}
            chevron
            onClick={() => open({ kind: "admin", screen: { name: ADMIN_SCREENS.CHAT, chatId: c.chat_id } })}
          />
        ))}
      </Group>
    </>
  );
}

function ChatView({ chatId, onGone }: { chatId: number; onGone: () => void }) {
  const { data, tr, toast } = useApp();
  const settings = useLoad(`admin-chat:${chatId}`, () => adminApi.fetchChatSettings(data, chatId));
  const actions = useLoad(`admin-actions-chat:${chatId}`, () => adminApi.fetchActions(data, "chat", String(chatId)));
  return (
    <>
      {!settings.data && settings.loading && <RowsSkel />}
      {settings.data && (
        <SettingsGroups
          settings={settings.data}
          save={async (key, value) => {
            try {
              settings.set(await adminApi.patchChatSetting(data, chatId, key, value));
            } catch (err) {
              toast(tr("somethingWrong"), "error");
              throw err;
            }
          }}
        />
      )}
      <ChatAdminGroup chatId={chatId} onGone={onGone} />
      {actions.data && <Actions actions={actions.data.actions} onGone={onGone} />}
    </>
  );
}

/** The chat's one admin (#232): an app admin appoints or removes; the chat admin hands the role on. */
function ChatAdminGroup({ chatId, onGone }: { chatId: number; onGone: () => void }) {
  const { data, tr, toast } = useApp();
  const state = useLoad(`admin-chat-admin:${chatId}`, () => adminApi.fetchChatAdmin(data, chatId));
  const [picking, setPicking] = useState(false);
  const [ask, setAsk] = useState<{ tgId: number; name: string } | null>(null);
  const [remove, setRemove] = useState(false);
  const s = state.data;
  if (!s) return null;
  const give = async (tgId: number) => {
    try {
      const res = await adminApi.putChatAdmin(data, chatId, tgId);
      toast(tr("chatAdminDone"));
      if (!res.still) onGone();
      else state.reload();
    } catch {
      toast(tr("somethingWrong"), "error");
    }
  };
  return (
    <>
      <Group title={tr("chatAdmin")}>
        <Row lead={<Icon name="people" />} title={s.admin?.name ?? tr("chatAdminNone")} />
        <Row
          title={s.hand_on ? tr("chatAdminHandOn") : tr("chatAdminAppoint")}
          sub={s.hand_on ? tr("chatAdminHandOnSub") : undefined}
          chevron
          onClick={() => setPicking(true)}
        />
        {s.can_remove && <Row title={tr("chatAdminRemove")} danger onClick={() => setRemove(true)} />}
      </Group>
      {picking && (
        <Sheet title={tr("chatAdminPick")} onClose={() => setPicking(false)} layer="chat-admin">
          {s.candidates.length === 0 ? (
            <Empty title={tr("chatAdminNobody")} />
          ) : (
            <Group>
              {s.candidates.map((c) => (
                <Row
                  key={c.tg_id}
                  lead={<Face personId={c.person_id} name={c.name} size={36} />}
                  title={c.name}
                  onClick={() => {
                    setPicking(false);
                    setAsk({ tgId: c.tg_id, name: c.name });
                  }}
                />
              ))}
            </Group>
          )}
        </Sheet>
      )}
      {ask && (
        <Confirm
          text={(s.hand_on ? tr("chatAdminConfirmHandOn") : tr("chatAdminConfirm")).replace("{name}", ask.name)}
          yes={tr("yes")}
          no={tr("cancel")}
          danger={s.hand_on}
          onYes={() => {
            const a = ask;
            setAsk(null);
            void give(a.tgId);
          }}
          onNo={() => setAsk(null)}
        />
      )}
      {remove && (
        <Confirm
          text={tr("chatAdminConfirmRemove")}
          yes={tr("yes")}
          no={tr("cancel")}
          danger
          onYes={async () => {
            setRemove(false);
            try {
              state.set(await adminApi.deleteChatAdmin(data, chatId));
            } catch {
              toast(tr("somethingWrong"), "error");
            }
          }}
          onNo={() => setRemove(false)}
        />
      )}
    </>
  );
}

/** A card's actions, grouped by section; each asks as many times as the server says. */
function Actions({ actions, onGone, onDone }: { actions: AdminAction[]; onGone: () => void; onDone?: () => void }) {
  const { data, tr, toast } = useApp();
  const [ask, setAsk] = useState<{ action: AdminAction; text: string; yes: string; step: number } | null>(null);
  const run = async (action: AdminAction, step: number) => {
    try {
      const res = await adminApi.postAction(data, { scope: action.scope, target: action.target, action: action.id, step });
      if (res.confirm) {
        setAsk({ action, text: res.confirm.text, yes: res.confirm.yes, step: res.confirm.step });
        return;
      }
      if (res.done?.text) toast(res.done.text, res.done.ok ? "info" : "error");
      if (res.done?.gone) onGone();
      else onDone?.();
    } catch {
      toast(tr("somethingWrong"), "error");
    }
  };
  const sections = new Map<string, AdminAction[]>();
  for (const a of actions) {
    const key = a.section_title ?? "";
    sections.set(key, [...(sections.get(key) ?? []), a]);
  }
  return (
    <>
      {[...sections.entries()].map(([title, list]) => (
        <Group key={title} title={title || undefined}>
          {list.map((a) => (
            <Row key={`${a.scope}:${a.target}:${a.id}`} title={a.label} danger={a.danger} onClick={() => void run(a, 0)} />
          ))}
        </Group>
      ))}
      {ask && (
        <Confirm
          text={ask.text}
          yes={ask.yes}
          no={tr("cancel")}
          danger={ask.action.danger}
          onYes={() => {
            const a = ask;
            setAsk(null);
            void run(a.action, a.step);
          }}
          onNo={() => setAsk(null)}
        />
      )}
    </>
  );
}
