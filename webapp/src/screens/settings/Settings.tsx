import { useEffect, useState } from "react";
import { userApi, type TimeZoneChoice, type UserSettingsPatch } from "../../api";
import { peopleApi, type ActivityVisible } from "../../api/people/peopleApi";
import { useApp } from "../../app/context";
import { inTelegram, look, PALETTES, setLook } from "../../app/env";
import { PALETTE_NAMES, paletteLevel, paletteOpen, usePass } from "../../core/season-pass";
import type { SettingsPaneName } from "../../app/layers";
import { useLoad } from "../../app/useLoad";
import { disablePush, enablePush, pushState, quickPushState, type PushState } from "../../core/push";
import { formatOffset, type TranslationKey } from "../../i18n";
import { Field, Group, Row, Segmented, Toggle } from "../../ui/Controls";
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
      {/* By how often one comes here: the accounts and what one hears first, how
          the app looks, where posts go; then the rarer; then the extras. */}
      <Group>
        <Row lead={<Lead icon="gamepad" tone="primary" />} title={tr("accounts")} sub={accounts || tr("noPlatforms")} chevron onClick={() => open({ kind: "settings", pane: "accounts" })} />
        <Row lead={<Lead icon="bell" />} title={tr("notifications")} sub={tr("notificationsSub")} chevron onClick={() => open({ kind: "settings", pane: "notifications" })} />
        <Row lead={<Lead icon="palette" />} title={tr("appearance")} sub={tr("appearanceSub")} chevron onClick={() => open({ kind: "settings", pane: "appearance" })} />
        <Row lead={<Lead icon="share" />} title={tr("publishing")} sub={tr("publishingSub")} chevron onClick={() => open({ kind: "settings", pane: "publishing" })} />
      </Group>
      <Group>
        <Row lead={<Lead icon="globe" />} title={tr("general")} sub={tr("generalSub")} chevron onClick={() => open({ kind: "settings", pane: "general" })} />
        <Row lead={<Lead icon="shield" />} title={tr("privacy")} sub={tr("privacySub")} chevron onClick={() => open({ kind: "settings", pane: "privacy" })} />
        <Row lead={<Lead icon="key" />} title={tr("logins")} sub={tr("loginsSub")} chevron onClick={() => open({ kind: "settings", pane: "logins" })} />
      </Group>
      <Group>
        {(me.is_superadmin || me.chat_admin) && (
          <Row lead={<Lead icon="settings" tone="tertiary" />} title={tr("admin")} chevron onClick={() => open({ kind: "admin", screen: null })} />
        )}
        <Row lead={<Lead icon="gift" tone="tertiary" />} title={tr("invites")} sub={tr("invitesSub")} chevron onClick={() => open({ kind: "settings", pane: "invites" })} />
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

function AppearancePane() {
  const { tr, open, data } = useApp();
  const [view, setView] = useState(look);
  // Themes past Violet are the season pass's, claimed on the server.
  const pass = usePass(data);
  const pick = (next: Partial<ReturnType<typeof look>>) => {
    setLook(next);
    setView(look());
  };
  return (
    <>
      <Group>
        <div className="set-pad set-look">
          <div className="swatches" role="radiogroup" aria-label={tr("appearance")}>
            {PALETTES.map((p) => {
              const shut = !paletteOpen(p, pass);
              return (
                <button
                  key={p}
                  type="button"
                  role="radio"
                  aria-checked={view.palette === p}
                  className={`swatch swatch-${p}${view.palette === p ? " swatch-on" : ""}${shut ? " swatch-shut" : ""}`}
                  onClick={() => (shut ? open({ kind: "pass" }) : pick({ palette: p }))}
                >
                  <span className="swatch-dot shape-cookie9">
                    {view.palette === p ? <Icon name="check" size={18} /> : shut ? <Icon name="lock" size={16} /> : null}
                  </span>
                  <span>{tr(PALETTE_NAMES[p])}</span>
                  {shut && (
                    <span className="swatch-level">
                      {tr("passLevel")} {paletteLevel(p, pass)}
                    </span>
                  )}
                </button>
              );
            })}
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
          sub={me.settings.tz_label ?? formatOffset(me.settings.tz_offset_min, locale)}
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
        <TimeZoneSheet
          current={me.settings.tz_name ?? null}
          onPick={(id) => {
            setTz(false);
            void save({ tz_name: id });
          }}
          onClose={() => setTz(false)}
        />
      )}
    </>
  );
}

/** The phone's own time zone, as the browser knows it. */
function deviceZone(): string | null {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || null;
  } catch {
    return null;
  }
}

/** Time zones by place (owner, 2026-10-30): a summer clock change follows by
 * itself. The phone's own first, then a search over the places offered. */
function TimeZoneSheet({ current, onPick, onClose }: { current: string | null; onPick: (id: string) => void; onClose: () => void }) {
  const { data, tr, locale } = useApp();
  const [q, setQ] = useState("");
  const list = useLoad(`time-zones:${locale}`, () => userApi.timeZones(data, locale, deviceZone()));
  const needle = q.trim().toLowerCase();
  const zones = (list.data?.zones ?? []).filter(
    (z) => !needle || z.label.toLowerCase().includes(needle) || z.id.toLowerCase().includes(needle),
  );
  const device = list.data?.device;
  // The cities on the left, the offset on the right.
  const pick = (z: TimeZoneChoice, sub?: string) => (
    <button key={z.id} type="button" className={`set-pick${z.id === current ? " set-pick-on" : ""}`} onClick={() => onPick(z.id)}>
      <span className="set-pick-text">
        {z.name ?? formatOffset(z.offset, locale)}
        {sub && <span className="set-pick-sub">{sub}</span>}
      </span>
      <span className="set-pick-end">
        <span className="set-tz-offset t-num">{formatOffset(z.offset, locale)}</span>
        {z.id === current && <Icon name="check" size={20} />}
      </span>
    </button>
  );
  return (
    <Sheet title={tr("timezone")} onClose={onClose} layer="tz">
      <div className="set-tz-search">
        <Field icon="search" placeholder={tr("timezoneFind")} value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {device && !needle && <div className="set-list set-tz-device">{pick(device, tr("timezoneDevice"))}</div>}
      {list.loading && !list.data ? (
        <div className="set-list">{[0, 1, 2, 3].map((i) => <span key={i} className="set-pick skel" />)}</div>
      ) : (
        <div className="set-list">{zones.map((z) => pick(z))}</div>
      )}
    </Sheet>
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

// The widest first, «Не присылать» always last.
const POST_CHOICES = ["following", "friends", "off"] as const;
const NEWS_CHOICES = ["all", "favorites", "patch", "news", "off"] as const;
const LEVEL_CHOICES = ["all", "prizes", "off"] as const;

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
    // On until switched off (`pass_reward:off`).
    reward: !list.includes("pass_reward:off"),
    seasonStart: !list.includes("season_start:off"),
    // A personal PSN token that stopped working (#233): on until switched off.
    psnToken: !list.includes("psn_token_dead:off"),
    // Every level unless `pass_level:prizes` or `pass_level:off`.
    level: list.includes("pass_level:off") ? "off" : list.includes("pass_level:prizes") ? "prizes" : "all",
  };
}

function writeChannel(c: ReturnType<typeof readChannel>, push: boolean): string[] {
  const out: string[] = [];
  if (c.post !== "off") out.push(`new_post:${c.post}`);
  if (c.news !== "off") out.push(`game_news:${c.news}`);
  if (c.follower) out.push("new_follower");
  if (c.friend) out.push("new_friend");
  if (push && c.xbox) out.push("xbox_login_dead");
  if (!c.reward) out.push("pass_reward:off");
  if (!c.seasonStart) out.push("season_start:off");
  if (!c.psnToken) out.push("psn_token_dead:off");
  if (c.level !== "all") out.push(`pass_level:${c.level}`);
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
  const [picking, setPicking] = useState<"post" | "news" | "level" | null>(null);
  const postLabel: Record<string, TranslationKey> = { off: "notifyOff", friends: "notifyPostsFriends", following: "notifyPostsFollowing" };
  const newsLabel: Record<string, TranslationKey> = {
    off: "notifyOff",
    all: "postsAll",
    patch: "notifyGameNewsPatch",
    news: "notifyGameNewsNews",
    favorites: "notifyGameNewsFavorites",
  };
  const levelLabel: Record<string, TranslationKey> = { all: "notifyPassLevelsAll", prizes: "notifyPassLevelsPrizes", off: "notifyOff" };
  return (
    <div className="set-choices">
      <Group>
        <Row title={tr("notifyPosts")} sub={tr(postLabel[c.post])} chevron onClick={() => setPicking("post")} />
        <Row title={tr("notifyGameNews")} sub={tr(newsLabel[c.news])} chevron onClick={() => setPicking("news")} />
        <Row title={tr("notifyPassLevels")} sub={tr(levelLabel[c.level])} chevron onClick={() => setPicking("level")} />
      </Group>
      <Group>
        <Row title={tr("notifyFollowers")} trail={<Toggle checked={c.follower} label={tr("notifyFollowers")} onChange={(v) => set({ follower: v })} />} />
        <Row title={tr("notifyFriends")} trail={<Toggle checked={c.friend} label={tr("notifyFriends")} onChange={(v) => set({ friend: v })} />} />
        {push && <Row title={tr("notifyAccount")} trail={<Toggle checked={c.xbox} label={tr("notifyAccount")} onChange={(v) => set({ xbox: v })} />} />}
        <Row title={tr("notifyPassRewards")} trail={<Toggle checked={c.reward} label={tr("notifyPassRewards")} onChange={(v) => set({ reward: v })} />} />
        <Row title={tr("notifySeasonStart")} trail={<Toggle checked={c.seasonStart} label={tr("notifySeasonStart")} onChange={(v) => set({ seasonStart: v })} />} />
        <Row title={tr("notifyPsnToken")} trail={<Toggle checked={c.psnToken} label={tr("notifyPsnToken")} onChange={(v) => set({ psnToken: v })} />} />
      </Group>
      {picking === "post" && (
        <ChoiceSheet title={tr("notifyPosts")} layer={`notify-post:${push}`} choices={POST_CHOICES} value={c.post} label={(v) => tr(postLabel[v])} onPick={(v) => set({ post: v })} onClose={() => setPicking(null)} />
      )}
      {picking === "news" && (
        <ChoiceSheet title={tr("notifyGameNews")} layer={`notify-news:${push}`} choices={NEWS_CHOICES} value={c.news} label={(v) => tr(newsLabel[v])} onPick={(v) => set({ news: v })} onClose={() => setPicking(null)} />
      )}
      {picking === "level" && (
        <ChoiceSheet title={tr("notifyPassLevels")} layer={`notify-level:${push}`} choices={LEVEL_CHOICES} value={c.level} label={(v) => tr(levelLabel[v])} onPick={(v) => set({ level: v })} onClose={() => setPicking(null)} />
      )}
    </div>
  );
}

/** One of a few values, picked in a sheet (the design system's choice). */
function ChoiceSheet({ title, layer, choices, value, label, onPick, onClose }: {
  title: string;
  layer: string;
  choices: readonly string[];
  value: string;
  label: (v: string) => string;
  onPick: (v: string) => void;
  onClose: () => void;
}) {
  return (
    <Sheet title={title} onClose={onClose} layer={layer}>
      <div className="set-list">
        {choices.map((v) => (
          <button
            key={v}
            type="button"
            className={`set-pick${v === value ? " set-pick-on" : ""}`}
            onClick={() => {
              onClose();
              onPick(v);
            }}
          >
            {label(v)}
            {v === value && <Icon name="check" size={20} />}
          </button>
        ))}
      </div>
    </Sheet>
  );
}
