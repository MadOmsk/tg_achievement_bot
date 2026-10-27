import { useEffect, useState } from "react";
import { ApiError, userApi, type LoginsResponse, type MergeChoices, type MergePreview } from "../../api";
import { useApp } from "../../app/context";
import { inTelegram, openExternal } from "../../app/env";
import { useLoad } from "../../app/useLoad";
import { createPasskey, passkeyCancelled, passkeysSupported } from "../../core/passkey";
import { TelegramLogin, type TelegramUser } from "../../core/telegram-login";
import { formatWhen } from "../../i18n";
import { CodeEntry, errorText } from "../../parts/CodeEntry";
import { Button, Field, Group, Row, Segmented } from "../../ui/Controls";
import { Icon } from "../../ui/Icon";
import "../signin/SignIn.css";
import { Confirm, Sheet } from "../../ui/Page";

export function LoginsPane() {
  const { data, tr, locale, toast, reloadMe } = useApp();
  const logins = useLoad<LoginsResponse>("logins", () => userApi.logins(data));
  const config = useLoad("auth-config", () => userApi.authConfig());
  const [editEmail, setEditEmail] = useState(false);
  const [askRemove, setAskRemove] = useState(false);
  const [merge, setMerge] = useState<MergePreview | null>(null);
  const l = logins.data;

  useEffect(() => {
    if (l?.merge_pending) {
      void userApi.pendingMerge(data).then((r) => setMerge(r.merge)).catch(() => undefined);
    }
  }, [l?.merge_pending, data]);

  /** A login that is somebody else's and proved: the answer carries the merge. */
  const takenMerge = (err: unknown): boolean => {
    if (err instanceof ApiError && err.code === "taken" && err.body.merge) {
      setMerge(err.body.merge as MergePreview);
      return true;
    }
    return false;
  };

  const linkTelegram = async (user: TelegramUser) => {
    try {
      logins.set(await userApi.linkTelegram(data, user));
      await reloadMe();
    } catch (err) {
      if (!takenMerge(err)) toast(errorText(err, locale), "error");
    }
  };

  const blockedWhy = l?.telegram.blocked;
  const blockedText =
    blockedWhy === "last_login" ? tr("telegramKeepLast") : blockedWhy === "admin" ? tr("telegramKeepAdmin") : blockedWhy === "in_telegram" ? tr("telegramKeepInside") : null;

  return (
    <>
      <Group title={tr("emailTitle")}>
        {!editEmail ? (
          <Row
            lead={<Icon name="mail" />}
            title={l?.email ?? tr("keyUnset")}
            sub={tr("emailHint")}
            trail={
              l?.email_available ? (
                <button type="button" className="link-btn" onClick={() => setEditEmail(true)}>
                  {l?.email ? tr("emailChangeShort") : tr("connect")}
                </button>
              ) : null
            }
          />
        ) : (
          <div className="row set-col">
            <EmailEditor
              onDone={async (fresh) => {
                logins.set(fresh);
                setEditEmail(false);
                toast(tr("emailSaved"));
                await reloadMe();
              }}
              onMerge={takenMerge}
              onCancel={() => setEditEmail(false)}
            />
          </div>
        )}
      </Group>

      <Group title="Telegram">
        {l?.telegram.linked ? (
          <>
            <Row lead={<Icon name="share" />} title={l.telegram.username ?? tr("telegramLinked")} sub={tr("telegramWhy")} />
            {l.telegram.removable ? (
              <Row lead={<Icon name="trash" />} title={tr("telegramRemove")} danger onClick={() => setAskRemove(true)} />
            ) : blockedText ? (
              <Row lead={<Icon name="lock" />} title={blockedText} />
            ) : null}
          </>
        ) : (
          <div className="row set-col">
            <p className="t-body">{tr("telegramWhy")}</p>
            {!inTelegram() && config.data?.bot_username && <TelegramLogin bot={config.data.bot_username} onAuth={(u) => void linkTelegram(u)} />}
            <Button
              variant="tonal"
              icon="external"
              onClick={async () => {
                try {
                  openExternal((await userApi.telegramLinkUrl(data)).url);
                } catch {
                  toast(tr("somethingWrong"), "error");
                }
              }}
            >
              {tr("telegramViaBot")}
            </Button>
          </div>
        )}
      </Group>

      <Passkeys />

      {askRemove && (
        <Confirm
          text={tr("telegramRemoveConfirm")}
          yes={tr("telegramRemove")}
          no={tr("cancel")}
          danger
          onYes={async () => {
            setAskRemove(false);
            try {
              logins.set(await userApi.removeTelegram(data));
              await reloadMe();
            } catch (err) {
              toast(errorText(err, locale), "error");
            }
          }}
          onNo={() => setAskRemove(false)}
        />
      )}
      {merge && (
        <MergeSheet
          preview={merge}
          onClose={() => setMerge(null)}
          onDone={async (fresh) => {
            setMerge(null);
            logins.set(fresh);
            toast(tr("mergeDone"));
            await reloadMe();
          }}
        />
      )}
    </>
  );
}

function EmailEditor({
  onDone,
  onMerge,
  onCancel,
}: {
  onDone: (fresh: LoginsResponse) => void;
  onMerge: (err: unknown) => boolean;
  onCancel: () => void;
}) {
  const { data, tr, locale } = useApp();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const verify = async (code: string) => {
    try {
      onDone(await userApi.emailLinkVerify(data, email.trim(), code));
    } catch (err) {
      if (onMerge(err)) return;
      throw err;
    }
  };
  if (sent !== null) {
    return (
      <CodeEntry
        locale={locale}
        email={email.trim()}
        resendAfter={sent}
        onVerify={verify}
        onResend={async () => (await userApi.emailLinkStart(data, email.trim())).resend_after}
        onChangeAddress={() => setSent(null)}
      />
    );
  }
  return (
    <form
      className="set-form"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        try {
          const res = await userApi.emailLinkStart(data, email.trim());
          if (res.skip_code) await verify("000000");
          else setSent(res.resend_after);
        } catch (err) {
          if (!onMerge(err)) setError(errorText(err, locale));
        } finally {
          setBusy(false);
        }
      }}
    >
      <Field type="email" inputMode="email" autoComplete="email" icon="mail" placeholder={tr("emailPlaceholder")} value={email} error={error} onChange={(e) => setEmail(e.target.value)} />
      <div className="set-buttons">
        <Button variant="text" onClick={onCancel}>
          {tr("cancel")}
        </Button>
        <Button type="submit" busy={busy} disabled={!email.includes("@")}>
          {tr("emailGetCode")}
        </Button>
      </div>
    </form>
  );
}

function Passkeys() {
  const { data, tr, locale, toast } = useApp();
  const keys = useLoad(inTelegram() ? null : "passkeys", () => userApi.passkeys(data));
  const [ask, setAsk] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (inTelegram()) {
    return (
      <Group title={tr("passkeysTitle")}>
        <Row lead={<Icon name="key" />} title={tr("passkeysHint")} sub={tr("passkeyInTelegram")} />
      </Group>
    );
  }
  if (!keys.data?.available) return null;
  const supported = passkeysSupported();
  const add = async () => {
    setBusy(true);
    try {
      const { token, options } = await userApi.passkeyOptions(data);
      const credential = await createPasskey(options);
      keys.set(await userApi.addPasskey(data, token, credential));
      toast(tr("passkeyAdded"));
    } catch (err) {
      if (!passkeyCancelled(err)) toast(err instanceof ApiError && err.code === "taken" ? tr("passkeyTaken") : tr("passkeyFailed"), "error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Group title={tr("passkeysTitle")}>
      {keys.data.keys.map((k) => (
        <Row
          key={k.id}
          lead={<Icon name="key" />}
          title={k.name ?? tr("passkeyUnnamed")}
          sub={`${tr("passkeyCreated")} ${formatWhen(k.created_at, locale)}${k.last_used_at ? ` · ${tr("passkeyUsed")} ${formatWhen(k.last_used_at, locale)}` : ""}`}
          trail={
            <button type="button" className="link-btn" aria-label={tr("passkeyRemove")} onClick={() => setAsk(k.id)}>
              <Icon name="trash" size={18} />
            </button>
          }
        />
      ))}
      <Row
        lead={<Icon name="plus" />}
        title={tr("passkeyAdd")}
        sub={supported ? tr("passkeysHint") : tr("passkeyNoSupport")}
        onClick={supported && !busy ? () => void add() : undefined}
      />
      {ask && (
        <Confirm
          text={tr("passkeyRemoveConfirm")}
          yes={tr("passkeyRemove")}
          no={tr("cancel")}
          danger
          onYes={async () => {
            const id = ask;
            setAsk(null);
            try {
              keys.set(await userApi.removePasskey(data, id));
            } catch {
              toast(tr("somethingWrong"), "error");
            }
          }}
          onNo={() => setAsk(null)}
        />
      )}
    </Group>
  );
}

type Side = "keep" | "absorb";

function MergeSheet({ preview, onClose, onDone }: { preview: MergePreview; onClose: () => void; onDone: (fresh: LoginsResponse) => void }) {
  const { data, tr, toast, locale } = useApp();
  const [choices, setChoices] = useState<MergeChoices>({});
  const [psn, setPsn] = useState<string[]>(preview.conflicts.psn?.accounts.slice(0, preview.conflicts.psn.max).map((a) => a.id) ?? []);
  const [busy, setBusy] = useState(false);
  const c = preview.conflicts;
  const pick = (key: "xbox" | "steam" | "telegram" | "email", label: string, keep: string, absorb: string) => (
    <div className="merge-pick" key={key}>
      <p className="set-label">{label}</p>
      <Segmented
        options={[
          { value: "keep", label: keep },
          { value: "absorb", label: absorb },
        ]}
        value={(choices[key] as Side) ?? "keep"}
        onChange={(v) => setChoices((s) => ({ ...s, [key]: v }))}
      />
    </div>
  );
  const side = (s: typeof preview.keep, title: string) => (
    <div className="merge-side">
      <p className="set-label">{title}</p>
      <p className="row-title">{s.handle ?? s.email ?? s.telegram}</p>
      <p className="row-sub">
        {[s.email, s.telegram, ...Object.entries(s.accounts).flatMap(([p, list]) => list.map((a) => `${p}: ${a.name ?? a.id}`))].filter(Boolean).join(" · ")}
      </p>
      <p className="row-sub">
        {tr("mergeFollows")} {s.follows} · {tr("mergeChats")} {s.chats}
      </p>
    </div>
  );
  return (
    <Sheet title={tr("mergeTitle")} onClose={onClose} layer="merge">
      <div className="set-pad merge">
        <p className="t-body">{tr("mergeText")}</p>
        {side(preview.keep, tr("mergeThis"))}
        {side(preview.absorb, tr("mergeOther"))}
        {(c.xbox || c.steam || c.telegram || c.email) && <p className="set-hint">{tr("mergeAccountHint")}</p>}
        {c.xbox && pick("xbox", "Xbox", c.xbox.keep.name ?? c.xbox.keep.id, c.xbox.absorb.name ?? c.xbox.absorb.id)}
        {c.steam && pick("steam", "Steam", c.steam.keep.name ?? c.steam.keep.id, c.steam.absorb.name ?? c.steam.absorb.id)}
        {c.telegram && pick("telegram", "Telegram", c.telegram.keep.name ?? tr("mergeThisSide"), c.telegram.absorb.name ?? tr("mergeOtherSide"))}
        {c.email && pick("email", tr("emailTitle"), c.email.keep, c.email.absorb)}
        {c.psn && (
          <div className="merge-pick">
            <p className="set-label">
              PlayStation · {tr("mergePsnHint")} {c.psn.max}
            </p>
            <div className="set-chips">
              {c.psn.accounts.map((a) => {
                const on = psn.includes(a.id);
                return (
                  <button
                    key={a.id}
                    type="button"
                    className={`set-chip${on ? " on" : ""}`}
                    onClick={() => setPsn((s) => (on ? s.filter((x) => x !== a.id) : s.length < c.psn!.max ? [...s, a.id] : s))}
                  >
                    {a.name ?? a.id}
                  </button>
                );
              })}
            </div>
          </div>
        )}
        <div className="set-buttons">
          <Button
            variant="text"
            onClick={async () => {
              await userApi.cancelMerge(data).catch(() => undefined);
              onClose();
            }}
          >
            {tr("mergeNotNow")}
          </Button>
          <Button
            busy={busy}
            onClick={async () => {
              setBusy(true);
              try {
                onDone(await userApi.merge(data, { ...choices, ...(c.psn ? { psn } : {}) }));
              } catch (err) {
                toast(err instanceof ApiError && err.code === "admin" ? tr("mergeAdmin") : errorText(err, locale), "error");
              } finally {
                setBusy(false);
              }
            }}
          >
            {tr("mergeDo")}
          </Button>
        </div>
      </div>
    </Sheet>
  );
}
