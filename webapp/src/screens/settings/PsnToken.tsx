import { useState } from "react";
import { ApiError, userApi } from "../../api";
import { useApp } from "../../app/context";
import { dayLabel, timeAgo, type TranslationKey } from "../../i18n";
import { errorText } from "../../parts/CodeEntry";
import { Button, Field, Group, Row } from "../../ui/Controls";
import { Icon } from "../../ui/Icon";
import { Confirm, Page } from "../../ui/Page";

const SSO_URL = "https://ca.account.sony.com/api/v1/ssocookie";

const ERRORS: Record<string, TranslationKey> = {
  format: "psnTokenErrFormat",
  refused: "psnTokenErrRefused",
  mismatch: "psnTokenErrMismatch",
  unavailable: "psnTokenErrUnavailable",
  not_linked: "psnTokenErrNotLinked",
  too_soon: "psnTokenErrTooSoon",
  not_configured: "connectNotConfigured",
  limit: "connectLimit",
  cooldown: "connectCooldown",
};

/** A PSN account's own token (#233; agreed on the bot's mockup): what it
 * gives, how to get one, paste it; its state, replace, remove. `accountId`
 * null links a new PSN account by its token. The token is never shown back. */
export function PsnTokenPage({ accountId, onClose, layer }: { accountId: string | null; onClose: () => void; layer: string }) {
  const { me, data, tr, locale, toast, reloadMe } = useApp();
  const account = accountId && me.psn.linked ? me.psn.accounts?.find((a) => a.account_id === accountId) : undefined;
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [asking, setAsking] = useState(false);
  const state = account?.token ?? null;
  const showForm = !accountId || !state || editing || state === "dead";

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      if (accountId) {
        await userApi.setPsnToken(data, accountId, value);
        toast(tr("psnTokenSaved"));
      } else {
        await userApi.connectPsnByToken(data, value);
        toast(tr("psnTokenLinked"));
      }
      setValue("");
      setEditing(false);
      await reloadMe();
      if (!accountId) onClose();
    } catch (err) {
      const code = err instanceof ApiError ? err.code : "";
      const key = ERRORS[code];
      const other = err instanceof ApiError ? String(err.body.other ?? "") : "";
      setError(key ? tr(key).replace("{other}", other) : errorText(err, locale));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!accountId) return;
    try {
      await userApi.removePsnToken(data, accountId);
      toast(tr("psnTokenRemoved"));
      await reloadMe();
    } catch {
      toast(tr("somethingWrong"), "error");
    }
  };

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(SSO_URL);
      toast(tr("psnTokenLinkCopied"));
    } catch {
      toast(SSO_URL);
    }
  };

  return (
    <Page title={accountId ? tr("psnToken") : tr("psnTokenLink")} onBack={onClose} layer={layer}>
      {account && (
        <Group>
          <Row lead={<span className="acc-mark acc-psn shape-cookie9">PS</span>} title={account.name} sub={state === "active" ? tr("psnTokenOwn") : state === "dead" ? tr("psnTokenDeadShort") : tr("psnTokenShared")} />
          {state === "active" && (
            <>
              <Row lead={<Icon name="check" />} title={tr("psnTokenAlive")} sub={`${tr("psnTokenChecked")}: ${timeAgo(account.token_checked_at ?? null, locale)}`} />
              <Row lead={<Icon name="calendar" />} title={tr("psnTokenSince")} trail={<span className="t-meta">{dayLabel(account.token_since ?? null, locale)}</span>} />
            </>
          )}
          {state === "dead" && (
            <Row lead={<Icon name="lock" />} title={`${tr("psnTokenDeadSince")} ${dayLabel(account.token_dead_at ?? null, locale)}`} sub={tr("psnTokenDeadWhy")} />
          )}
          {state && (
            <>
              {state === "active" && !editing && <Row lead={<Icon name="refresh" />} title={tr("psnTokenReplace")} onClick={() => setEditing(true)} />}
              <Row lead={<Icon name="trash" />} title={tr("psnTokenRemove")} danger onClick={() => setAsking(true)} />
            </>
          )}
        </Group>
      )}

      {showForm && (
        <>
          {(!state || !accountId) && (
            <>
              <Group title={tr("psnTokenGives")}>
                <Row lead={<Icon name="trophy" />} title={tr("psnTokenGive1")} />
                <Row lead={<Icon name="gamepad" />} title={tr("psnTokenGive2")} />
                <Row lead={<Icon name="clock" />} title={tr("psnTokenGive3")} />
                <Row lead={<Icon name="sparkle" />} title={tr("psnTokenGive4")} />
              </Group>
              <Group title={tr("psnTokenSafetyTitle")}>
                <Row lead={<Icon name="shield" />} title={tr("psnTokenSafetyLead")} sub={tr("psnTokenSafety")} />
              </Group>
            </>
          )}
          <Group title={tr("psnTokenSteps")}>
            <Row lead={<span className="t-num">1</span>} title={tr("psnTokenStep1")} />
            <Row lead={<span className="t-num">2</span>} title={tr("psnTokenStep2")} sub={SSO_URL} trail={<Icon name="copy" />} onClick={() => void copyLink()} />
            <Row lead={<span className="t-num">3</span>} title={tr("psnTokenStep3")} />
            <Row lead={<span className="t-num">4</span>} title={tr("psnTokenStep4")} />
          </Group>
          <form
            className="set-pad set-form"
            onSubmit={(e) => {
              e.preventDefault();
              if (value.trim()) void submit();
            }}
          >
            <Field
              label={tr("psnTokenField")}
              type="password"
              value={value}
              autoComplete="off"
              autoCapitalize="off"
              autoCorrect="off"
              spellCheck={false}
              onChange={(e) => setValue(e.target.value)}
              error={error}
            />
            <Button wide type="submit" busy={busy} disabled={!value.trim()}>
              {state === "dead" ? tr("psnTokenRenew") : accountId ? tr("psnTokenSave") : tr("psnTokenLink")}
            </Button>
          </form>
        </>
      )}

      {asking && (
        <Confirm
          text={tr("psnTokenRemoveAsk")}
          yes={tr("psnTokenRemove")}
          no={tr("cancel")}
          danger
          onYes={() => {
            setAsking(false);
            void remove();
          }}
          onNo={() => setAsking(false)}
        />
      )}
    </Page>
  );
}
