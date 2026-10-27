import { useEffect, useState } from "react";
import { userApi, type UserSettingsPatch } from "../../api";
import { peopleApi, type ActivityVisible } from "../../api/people/peopleApi";
import { useApp } from "../../app/context";
import { inTelegram, look, PALETTES, setLook } from "../../app/env";
import type { SettingsPaneName } from "../../app/layers";
import { useLoad } from "../../app/useLoad";
import { TIMEZONES } from "../../core/constants";
import { disablePush, enablePush, pushState, quickPushState, type PushState } from "../../core/push";
import { formatOffset, timezoneLabel, type TranslationKey } from "../../i18n";
import { Group, Row, Segmented, Toggle } from "../../ui/Controls";
import { Face } from "../../ui/Face";
import { Icon, type IconName } from "../../ui/Icon";
import { Confirm, Page, Sheet } from "../../ui/Page";
import { AccountsPane } from "./Accounts";
import { InvitesPane } from "./Invites";
import { LoginsPane } from "./Logins";
import { ProfilePane } from "./Profile";
import "./Settings.css";

const TITLES: Record<SettingsPaneName, TranslationKey> = {
  root: "settings",
  profile: "profileLook",
  accounts: "accounts",
  publishing: "publishing",
  privacy: "privacy",
  logins: "logins",
  notifications: "notifications",
  general: "general",
  appearance: "appearance",
  invites: "invites",
};

export function SettingsPage({ pane, onClose, layer }: { pane: SettingsPaneName; onClose: () => void; layer: string }) {
  const { tr } = useApp();
  return (
    <Page title={tr(TITLES[pane])} onBack={onClose} layer={layer} className="settings">
      {pane === "root" && <Root />}
      {pane === "profile" && <ProfilePane />}
      {pane === "accounts" && <AccountsPane />}
      {pane === "publishing" && <PublishingPane />}
      {pane === "privacy" && <PrivacyPane />}
      {pane === "logins" && <LoginsPane />}
      {pane === "notifications" && <NotificationsPane />}
      {pane === "general" && <GeneralPane />}
      {pane === "appearance" && <AppearancePane />}
      {pane === "invites" && <InvitesPane />}
    </Page>
  );
}

/** One way into the app's settings: a person changes one thing and sees it
 * applied, the server's answer replacing `me`. */
export function useSettings() {
  const { data, setMe, toast, tr } = useApp();
  return async (patch: UserSettingsPatch) => {
    try {
      setMe(await userApi.patchSettings(data, patch));
    } catch {
      toast(tr("somethingWrong"), "error");
    }
  };
}

function Lead({ icon, tone = "secondary" }: { icon: IconName; tone?: "secondary" | "primary" | "tertiary" }) {
  return (
    <span className={`set-lead set-lead-${tone} shape-cookie9`}>
      <Icon name={icon} size={20} />
    </span>
  );
}

function Root() {
  const { me, tr, open, signOut, data, toast } = useApp();
  const [askDelete, setAskDelete] = useState(0);
  const accounts = [me.xbox.linked && "Xbox", me.psn.linked && "PlayStation", me.steam.linked && "Steam"].filter(Boolean).join(" · ");
  return (
    <>
      <button type="button" className="set-me" onClick={() => open({ kind: "settings", pane: "profile" })}>
        <Face personId={me.person_id} name={me.handle?.display ?? ""} size={64} />
        <span className="row-text">
          <span className="set-me-name clamp-1">{me.handle?.display}</span>
          <span className="row-sub">{tr("profileLookSub")}</span>
        </span>
        <Icon name="forward" size={20} />
      </button>
      <Group>
        <Row lead={<Lead icon="gamepad" tone="primary" />} title={tr("accounts")} sub={accounts || tr("noPlatforms")} chevron onClick={() => open({ kind: "settings", pane: "accounts" })} />
        <Row lead={<Lead icon="share" />} title={tr("publishing")} sub={tr("publishingSub")} chevron onClick={() => open({ kind: "settings", pane: "publishing" })} />
        <Row lead={<Lead icon="bell" />} title={tr("notifications")} sub={tr("notificationsSub")} chevron onClick={() => open({ kind: "settings", pane: "notifications" })} />
      </Group>
      <Group>
        <Row lead={<Lead icon="shield" />} title={tr("privacy")} sub={tr("privacySub")} chevron onClick={() => open({ kind: "settings", pane: "privacy" })} />
        <Row lead={<Lead icon="key" />} title={tr("logins")} sub={tr("loginsSub")} chevron onClick={() => open({ kind: "settings", pane: "logins" })} />
        <Row lead={<Lead icon="palette" />} title={tr("appearance")} sub={tr("appearanceSub")} chevron onClick={() => open({ kind: "settings", pane: "appearance" })} />
        <Row lead={<Lead icon="globe" />} title={tr("general")} sub={tr("generalSub")} chevron onClick={() => open({ kind: "settings", pane: "general" })} />
      </Group>
      <Group>
        <Row lead={<Lead icon="gift" tone="tertiary" />} title={tr("invites")} sub={tr("invitesSub")} chevron onClick={() => open({ kind: "settings", pane: "invites" })} />
        {me.is_superadmin && (
          <Row lead={<Lead icon="settings" tone="tertiary" />} title={tr("admin")} chevron onClick={() => open({ kind: "admin", screen: null })} />
        )}
      </Group>
      <Group>
        {!inTelegram() && (
          <Row
            lead={<Lead icon="logout" />}
            title={tr("logout")}
            onClick={() => {
              void userApi.logout().finally(signOut);
            }}
          />
        )}
        <Row lead={<Lead icon="trash" />} title={tr("deleteAccount")} danger onClick={() => setAskDelete(1)} />
      </Group>
      {askDelete === 1 && (
        <Confirm text={tr("deleteWarning")} yes={tr("deleteAccount")} no={tr("cancel")} danger onYes={() => setAskDelete(2)} onNo={() => setAskDelete(0)} />
      )}
      {askDelete === 2 && (
        <Confirm
          text={tr("deleteSure")}
          yes={tr("deleteAccount")}
          no={tr("cancel")}
          danger
          onYes={async () => {
            setAskDelete(0);
            try {
              await userApi.deleteAccount(data);
              toast(tr("deleteDone"));
              if (inTelegram()) window.Telegram?.WebApp?.close?.();
              else signOut();
            } catch {
              toast(tr("somethingWrong"), "error");
            }
          }}
          onNo={() => setAskDelete(0)}
        />
      )}
    </>
  );
}

const PALETTE_NAMES = {
  violet: "paletteViolet",
  mint: "paletteMint",
  ember: "paletteEmber",
  ocean: "paletteOcean",
  rose: "paletteRose",
} as const;

function AppearancePane() {
  const { tr } = useApp();
  const [view, setView] = useState(look);
  const pick = (next: Partial<ReturnType<typeof look>>) => {
    setLook(next);
    setView(look());
  };
  return (
    <>
      <Group>
        <div className="set-pad set-look">
          <div className="swatches" role="radiogroup" aria-label={tr("appearance")}>
            {PALETTES.map((p) => (
              <button
                key={p}
                type="button"
                role="radio"
                aria-checked={view.palette === p}
                className={`swatch swatch-${p}${view.palette === p ? " swatch-on" : ""}`}
                onClick={() => pick({ palette: p })}
              >
                <span className="swatch-dot shape-cookie9">{view.palette === p && <Icon name="check" size={18} />}</span>
                <span>{tr(PALETTE_NAMES[p])}</span>
              </button>
            ))}
          </div>
          <Segmented
            options={[
              { value: "auto", label: tr("modeAuto") },
              { value: "light", label: tr("modeLight") },
              { value: "dark", label: tr("modeDark") },
            ]}
            value={view.mode}
            onChange={(v) => pick({ mode: v })}
          />
        </div>
      </Group>
    </>
  );
}

function GeneralPane() {
  const { me, tr, locale } = useApp();
  const save = useSettings();
  const [tz, setTz] = useState(false);
  const offset = me.settings.tz_offset_min;
  const known = TIMEZONES.find((z) => z.min === offset);
  return (
    <>
      <Group title={tr("language")}>
        <div className="set-pad">
          <Segmented
            options={[
              { value: "ru", label: "Русский" },
              { value: "en", label: "English" },
            ]}
            value={locale}
            onChange={(v) => void save({ locale: v })}
          />
        </div>
      </Group>
      <Group>
        <Row
          lead={<Icon name="clock" />}
          title={tr("timezone")}
          sub={known ? timezoneLabel(known, locale) : formatOffset(offset, locale)}
          chevron
          onClick={() => setTz(true)}
        />
        <Row
          lead={<Icon name="lock" />}
          title={tr("showSecrets")}
          sub={tr("showSecretsHint")}
          trail={<Toggle checked={me.settings.show_secrets} label={tr("showSecrets")} onChange={(v) => void save({ show_secrets: v })} />}
        />
      </Group>
      {tz && (
        <Sheet title={tr("timezone")} onClose={() => setTz(false)} layer="tz">
          <div className="set-list">
            {TIMEZONES.map((z) => (
              <button
                key={z.min}
                type="button"
                className={`set-pick${z.min === offset ? " set-pick-on" : ""}`}
                onClick={() => {
                  setTz(false);
                  void save({ tz_offset_min: z.min });
                }}
              >
                {timezoneLabel(z, locale)}
                {z.min === offset && <Icon name="check" size={20} />}
              </button>
            ))}
          </div>
        </Sheet>
      )}
    </>
  );
}

function PrivacyPane() {
  const { data, tr, open, toast } = useApp();
  const privacy = useLoad("privacy", () => peopleApi.privacy(data));
  const set = async (value: ActivityVisible) => {
    try {
      privacy.set(await peopleApi.setPrivacy(data, value));
    } catch {
      toast(tr("somethingWrong"), "error");
    }
  };
  return (
    <>
      <Group title={tr("privacyWho")}>
        <div className="set-pad">
          <Segmented
            options={[
              { value: "all", label: tr("privacyAll") },
              { value: "friends", label: tr("privacyFriends") },
              { value: "nobody", label: tr("privacyNobody") },
            ]}
            value={privacy.data?.activity_visible ?? "all"}
            onChange={(v) => void set(v as ActivityVisible)}
          />
          <p className="set-hint">{tr("privacyHint")}</p>
        </div>
      </Group>
      <Group>
        <Row lead={<Icon name="block" />} title={tr("blockedTitle")} chevron onClick={() => open({ kind: "follows", personId: null, which: "blocked" })} />
      </Group>
    </>
  );
}

function PublishingPane() {
  const { me, data, tr, setMe, toast, open } = useApp();
  const save = useSettings();
  const [chats, setChats] = useState(me.chats);
  useEffect(() => setChats(me.chats), [me.chats]);
  const toggleChat = async (chatId: number, on: boolean) => {
    setChats((cs) => cs.map((c) => (c.chat_id === chatId ? { ...c, is_subscribed: on } : c)));
    try {
      await userApi.patchChat(data, chatId, { action: on ? "subscribe" : "unsubscribe" });
    } catch {
      setChats(me.chats);
      toast(tr("somethingWrong"), "error");
    }
  };
  const setPublishes = async (platform: "xbox" | "psn" | "steam", on: boolean, accountId?: string) => {
    try {
      setMe(await userApi.setAccountPublishes(data, platform, on, accountId));
    } catch {
      toast(tr("somethingWrong"), "error");
    }
  };
  const accounts: Array<{ key: string; label: string; on: boolean; set: (on: boolean) => void }> = [];
  if (me.xbox.linked) accounts.push({ key: "xbox", label: `Xbox · ${me.xbox.gamertag_modern ?? me.xbox.gamertag ?? ""}`, on: me.xbox.publishes !== false, set: (on) => void setPublishes("xbox", on) });
  if (me.psn.linked) {
    for (const a of me.psn.accounts ?? []) {
      accounts.push({ key: `psn:${a.account_id}`, label: `PlayStation · ${a.name}`, on: a.publishes, set: (on) => void setPublishes("psn", on, a.account_id) });
    }
  }
  if (me.steam.linked) accounts.push({ key: "steam", label: `Steam · ${me.steam.display_name ?? ""}`, on: me.steam.publishes !== false, set: (on) => void setPublishes("steam", on) });

  return (
    <>
      <p className="set-intro">{tr("publishingHint")}</p>
      <Group title={tr("publishingWhich")}>
        <div className="set-pad">
          <Segmented
            options={[
              { value: "all", label: tr("publishAll") },
              { value: "rare", label: tr("publishRare") },
              { value: "hidden", label: tr("publishNone") },
            ]}
            value={me.settings.rarity_mode}
            onChange={(v) => void save({ rarity_mode: v })}
          />
          <p className="set-hint">{tr("publishingWhatHint")}</p>
        </div>
      </Group>
      <Group title={tr("publishingChats")}>
        {me.tg_id == null ? (
          <Row lead={<Icon name="link" />} title={tr("publishingNeedsTelegram")} chevron onClick={() => open({ kind: "settings", pane: "logins" })} />
        ) : chats.length === 0 ? (
          <Row title={tr("noChatsShort")} sub={tr("myChatsHint")} />
        ) : (
          chats.map((c) => (
            <Row
              key={c.chat_id}
              title={c.title ?? String(c.chat_id)}
              trail={<Toggle checked={c.is_subscribed} label={c.title ?? ""} onChange={(on) => void toggleChat(c.chat_id, on)} />}
            />
          ))
        )}
      </Group>
      {accounts.length > 0 && (
        <Group title={tr("publishingAccounts")}>
          {accounts.map((a) => (
            <Row key={a.key} title={a.label} trail={<Toggle checked={a.on} label={a.label} onChange={a.set} />} />
          ))}
        </Group>
      )}
    </>
  );
}

const POST_CHOICES = ["off", "friends", "following"] as const;
const NEWS_CHOICES = ["off", "all", "patch", "news", "favorites"] as const;

/** A channel's kinds as the server keeps them: `new_post:friends`,
 * `game_news:patch`, `new_follower`… */
function readChannel(tokens: string[] | undefined) {
  const list = tokens ?? [];
  const pick = (kind: string) => {
    const t = list.find((x) => x === kind || x.startsWith(`${kind}:`));
    if (!t) return "off";
    return t.split(":")[1] ?? "all";
  };
  return {
    post: pick("new_post"),
    news: pick("game_news"),
    follower: list.includes("new_follower"),
    friend: list.includes("new_friend"),
    xbox: list.includes("xbox_login_dead"),
  };
}

function writeChannel(c: ReturnType<typeof readChannel>, push: boolean): string[] {
  const out: string[] = [];
  if (c.post !== "off") out.push(`new_post:${c.post}`);
  if (c.news !== "off") out.push(`game_news:${c.news}`);
  if (c.follower) out.push("new_follower");
  if (c.friend) out.push("new_friend");
  if (push && c.xbox) out.push("xbox_login_dead");
  return out;
}

function NotificationsPane() {
  const { me, data, tr } = useApp();
  const save = useSettings();
  const [push, setPush] = useState<PushState>(quickPushState);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    void pushState(data).then(setPush);
  }, [data]);
  const pushOn = push === "on" && me.settings.notify_push !== false;
  const pushWhy: Partial<Record<PushState, TranslationKey>> = {
    telegram: "pushInTelegram",
    "ios-install": "pushIosInstall",
    unsupported: "pushUnsupported",
    unavailable: "pushUnavailable",
    denied: "pushDenied",
  };
  const why = pushWhy[push];

  const togglePush = async (on: boolean) => {
    setBusy(true);
    try {
      const next = on ? await enablePush(data) : await disablePush(data);
      setPush(next);
      await save({ notify_push: next === "on" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Group title={tr("notifyPushGroup")}>
        <Row
          lead={<Icon name="bell" />}
          title={tr("notifyPush")}
          sub={why ? tr(why) : tr("notifyPushHint")}
          trail={why ? null : <Toggle checked={pushOn} disabled={busy} label={tr("notifyPush")} onChange={(v) => void togglePush(v)} />}
        />
      </Group>
      {pushOn && (
        <ChannelChoices tokens={me.settings.notify_push_on} push onSave={(t) => void save({ notify_push_on: t })} />
      )}
      <Group title={tr("notifyTelegramGroup")}>
        <Row
          lead={<Icon name="share" />}
          title={tr("notifyTelegram")}
          sub={me.tg_id == null ? tr("telegramNotLinked") : tr("notifyTelegramHint")}
          trail={
            me.tg_id == null ? null : (
              <Toggle checked={me.settings.notify_telegram !== false} label={tr("notifyTelegram")} onChange={(v) => void save({ notify_telegram: v })} />
            )
          }
        />
      </Group>
      {me.tg_id != null && me.settings.notify_telegram !== false && (
        <ChannelChoices tokens={me.settings.notify_telegram_on} push={false} onSave={(t) => void save({ notify_telegram_on: t })} />
      )}
    </>
  );
}

function ChannelChoices({ tokens, push, onSave }: { tokens: string[] | undefined; push: boolean; onSave: (tokens: string[]) => void }) {
  const { tr } = useApp();
  const c = readChannel(tokens);
  const set = (patch: Partial<typeof c>) => onSave(writeChannel({ ...c, ...patch }, push));
  const postLabel: Record<string, TranslationKey> = { off: "notifyOff", friends: "notifyPostsFriends", following: "notifyPostsFollowing" };
  const newsLabel: Record<string, TranslationKey> = {
    off: "notifyOff",
    all: "postsAll",
    patch: "notifyGameNewsPatch",
    news: "notifyGameNewsNews",
    favorites: "notifyGameNewsFavorites",
  };
  return (
    <div className="set-choices">
      <p className="set-label">{tr("notifyPosts")}</p>
      <div className="set-chips">
        {POST_CHOICES.map((v) => (
          <button key={v} type="button" className={`set-chip${c.post === v ? " on" : ""}`} onClick={() => set({ post: v })}>
            {tr(postLabel[v])}
          </button>
        ))}
      </div>
      <p className="set-label">{tr("notifyGameNews")}</p>
      <div className="set-chips">
        {NEWS_CHOICES.map((v) => (
          <button key={v} type="button" className={`set-chip${c.news === v ? " on" : ""}`} onClick={() => set({ news: v })}>
            {tr(newsLabel[v])}
          </button>
        ))}
      </div>
      <Group>
        <Row title={tr("notifyFollowers")} trail={<Toggle checked={c.follower} label={tr("notifyFollowers")} onChange={(v) => set({ follower: v })} />} />
        <Row title={tr("notifyFriends")} trail={<Toggle checked={c.friend} label={tr("notifyFriends")} onChange={(v) => set({ friend: v })} />} />
        {push && <Row title={tr("notifyAccount")} trail={<Toggle checked={c.xbox} label={tr("notifyAccount")} onChange={(v) => set({ xbox: v })} />} />}
      </Group>
    </div>
  );
}
