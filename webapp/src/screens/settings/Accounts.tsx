import { useState } from "react";
import { ApiError, userApi } from "../../api";
import { useApp } from "../../app/context";
import { openExternal } from "../../app/env";
import { num, plural, type TranslationKey } from "../../i18n";
import { errorText } from "../../parts/CodeEntry";
import { Button, Field, Group, Row, Toggle } from "../../ui/Controls";
import { Icon } from "../../ui/Icon";
import { Confirm, Page } from "../../ui/Page";

type Unlink = { platform: "xbox" | "steam" | "psn"; accountId?: string; label: string } | null;

export function AccountsPane() {
  const { me, data, tr, locale, setMe, toast, open, reloadMe } = useApp();
  const [unlink, setUnlink] = useState<Unlink>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const connectXbox = async () => {
    setBusy("xbox");
    try {
      const res = await userApi.connectXbox(data);
      toast(tr("openMicrosoft"));
      openExternal(res.authorize_url);
    } catch (err) {
      toast(errorText(err, locale), "error");
    } finally {
      setBusy(null);
    }
  };

  const publishes = async (platform: "xbox" | "steam" | "psn", on: boolean, accountId?: string) => {
    try {
      setMe(await userApi.setAccountPublishes(data, platform, on, accountId));
    } catch {
      toast(tr("somethingWrong"), "error");
    }
  };

  const doUnlink = async (u: NonNullable<Unlink>) => {
    try {
      if (u.platform === "xbox") await userApi.disconnectXbox(data);
      else if (u.platform === "steam") await userApi.disconnectSteam(data);
      else await userApi.disconnectPsn(data, u.accountId);
      await reloadMe();
    } catch {
      toast(tr("somethingWrong"), "error");
    }
  };

  const x = me.xbox;
  const psn = me.psn.linked ? me.psn : null;
  const steam = me.steam.linked ? me.steam : null;
  const psnAccounts = psn?.accounts ?? [];
  const maxPsn = psn?.max_accounts ?? 3;

  return (
    <>
      <p className="set-intro">{tr("connectHistoryTip")}</p>
      <Group title="Xbox">
        {x.linked ? (
          <>
            <Row
              lead={<span className="acc-mark acc-xbox shape-cookie9">X</span>}
              title={x.gamertag_modern ?? x.gamertag ?? ""}
              sub={[
                x.gamerscore != null ? `${num(x.gamerscore, locale)} G` : null,
                `${num(x.achievement_count, locale)} ${plural(locale, x.achievement_count, ["achOne", "achFew", "achMany"])}`,
                x.completed_games ? `${tr("factCompleted")}: ${x.completed_games}` : null,
              ]
                .filter(Boolean)
                .join(" · ")}
            />
            {x.needs_reconnect && (
              <Row lead={<Icon name="key" />} title={tr("reconnectHint")} trail={<Button variant="filled" busy={busy === "xbox"} onClick={() => void connectXbox()}>{tr("connect")}</Button>} />
            )}
            <Row title={tr("publishing")} trail={<Toggle checked={x.publishes !== false} label={tr("publishing")} onChange={(on) => void publishes("xbox", on)} />} />
            <Row
              lead={<Icon name="refresh" />}
              title={tr("sync")}
              onClick={async () => {
                try {
                  await userApi.syncXbox(data);
                  toast(tr("syncQueued"));
                } catch {
                  toast(tr("somethingWrong"), "error");
                }
              }}
            />
            <Row lead={<Icon name="trash" />} title={tr("disconnect")} danger onClick={() => setUnlink({ platform: "xbox", label: "Xbox" })} />
          </>
        ) : (
          <Row
            lead={<span className="acc-mark acc-xbox shape-cookie9">X</span>}
            title={tr("connectXbox")}
            sub={tr("connectXboxHint")}
            trail={<Button busy={busy === "xbox"} onClick={() => void connectXbox()}>{tr("connect")}</Button>}
          />
        )}
      </Group>

      <Group title="PlayStation">
        {psnAccounts.map((a) => (
          <div key={a.account_id} className="acc-block">
            <Row
              lead={<span className="acc-mark acc-psn shape-cookie9">PS</span>}
              title={a.name}
              sub={[
                a.trophy_level ? `${tr("level")} ${a.trophy_level}` : null,
                `${num(a.trophy_count, locale)} ${tr("trophies")}`,
                a.platinum_count ? `${tr("tierPlatinum")}: ${a.platinum_count}` : null,
              ]
                .filter(Boolean)
                .join(" · ")}
            />
            {a.achievements_visible === false && <Row lead={<Icon name="lock" />} title={tr("hiddenPsn")} sub={tr("connectPsnTip")} />}
            <Row title={tr("publishing")} trail={<Toggle checked={a.publishes} label={tr("publishing")} onChange={(on) => void publishes("psn", on, a.account_id)} />} />
            <Row
              lead={<Icon name="key" />}
              title={tr("psnTokenRow")}
              sub={a.token === "active" ? tr("psnTokenOwn") : a.token === "dead" ? tr("psnTokenDeadShort") : tr("psnTokenShared")}
              danger={a.token === "dead"}
              chevron
              onClick={() => open({ kind: "psn-token", accountId: a.account_id })}
            />
            <Row lead={<Icon name="trash" />} title={tr("disconnect")} danger onClick={() => setUnlink({ platform: "psn", accountId: a.account_id, label: a.name })} />
          </div>
        ))}
        {psnAccounts.length < maxPsn && (
          <Row
            lead={<span className="acc-mark acc-psn shape-cookie9">PS</span>}
            title={psnAccounts.length ? tr("addAccount") : tr("connectPsn")}
            sub={tr("connectPsnTip")}
            chevron
            onClick={() => open({ kind: "connect", platform: "psn" })}
          />
        )}
      </Group>

      <Group title="Steam">
        {steam ? (
          <>
            <Row
              lead={<span className="acc-mark acc-steam shape-cookie9">S</span>}
              title={steam.display_name ?? steam.steam_id}
              sub={[
                `${num(steam.achievement_count, locale)} ${plural(locale, steam.achievement_count, ["achOne", "achFew", "achMany"])}`,
                steam.completed_games ? `${tr("factCompleted")}: ${steam.completed_games}` : null,
              ]
                .filter(Boolean)
                .join(" · ")}
            />
            {steam.achievements_visible === false && <Row lead={<Icon name="lock" />} title={tr("hiddenSteam")} sub={tr("connectSteamTip")} />}
            <Row title={tr("publishing")} trail={<Toggle checked={steam.publishes !== false} label={tr("publishing")} onChange={(on) => void publishes("steam", on)} />} />
            <Row lead={<Icon name="trash" />} title={tr("disconnect")} danger onClick={() => setUnlink({ platform: "steam", label: "Steam" })} />
          </>
        ) : (
          <Row
            lead={<span className="acc-mark acc-steam shape-cookie9">S</span>}
            title={tr("connectSteam")}
            sub={tr("connectSteamTip")}
            chevron
            onClick={() => open({ kind: "connect", platform: "steam" })}
          />
        )}
      </Group>

      {unlink && (
        <Confirm
          text={`${tr("confirmDisconnect")}\n${unlink.label}`}
          yes={tr("disconnect")}
          no={tr("cancel")}
          danger
          onYes={() => {
            const u = unlink;
            setUnlink(null);
            void doUnlink(u);
          }}
          onNo={() => setUnlink(null)}
        />
      )}
    </>
  );
}

/** Steam by its profile link, vanity name or SteamID64; PSN by online id. */
export function ConnectPage({ platform, onClose, layer }: { platform: "steam" | "psn"; onClose: () => void; layer: string }) {
  const { data, tr, locale, reloadMe, toast, open } = useApp();
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const steam = platform === "steam";

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      if (steam) await userApi.connectSteam(data, value.trim());
      else await userApi.connectPsn(data, value.trim());
      await reloadMe();
      toast(tr("backfillStarted"));
      onClose();
    } catch (err) {
      const key = err instanceof ApiError ? CONNECT_ERRORS[err.code] : undefined;
      setError(key ? tr(key) : errorText(err, locale));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Page title={steam ? tr("connectSteam") : tr("connectPsn")} onBack={onClose} layer={layer}>
      <form
        className="set-pad set-form connect"
        onSubmit={(e) => {
          e.preventDefault();
          if (value.trim()) void submit();
        }}
      >
        <span className={`acc-mark acc-big ${steam ? "acc-steam" : "acc-psn"} shape-cookie12`}>{steam ? "S" : "PS"}</span>
        <p className="t-body">{steam ? tr("connectSteamTip") : tr("connectPsnTip")}</p>
        <Field
          label={steam ? tr("steamPrompt") : tr("psnPrompt")}
          value={value}
          autoCapitalize="off"
          autoCorrect="off"
          spellCheck={false}
          onChange={(e) => setValue(e.target.value)}
          error={error}
          hint={tr("connectHistoryTip")}
        />
        <Button wide type="submit" busy={busy} disabled={!value.trim()}>
          {tr("submit")}
        </Button>
      </form>
      {!steam && (
        <Group>
          <Row
            lead={<Icon name="key" />}
            title={tr("psnTokenByToken")}
            sub={tr("psnTokenByTokenSub")}
            chevron
            onClick={() => open({ kind: "psn-token", accountId: null })}
          />
        </Group>
      )}
    </Page>
  );
}

const CONNECT_ERRORS: Record<string, TranslationKey> = {
  not_configured: "connectNotConfigured",
  missing_identity: "connectNotFound",
  not_found: "connectNotFound",
  private: "connectPrivate",
  already_linked: "connectTaken",
  cooldown: "connectCooldown",
  service_dead: "connectServiceDead",
  limit: "connectLimit",
  // A token pasted into the nickname field is linked as a token (#233).
  format: "psnTokenErrFormat",
  refused: "psnTokenErrRefused",
  unavailable: "psnTokenErrUnavailable",
  too_soon: "psnTokenErrTooSoon",
};
