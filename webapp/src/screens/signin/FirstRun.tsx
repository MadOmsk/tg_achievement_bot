import { useState } from "react";
import { ApiError, userApi } from "../../api";
import { useApp } from "../../app/context";
import { CodeEntry, errorText } from "../../parts/CodeEntry";
import { Button, Field } from "../../ui/Controls";
import { Face } from "../../ui/Face";
import "./SignIn.css";

/** What a person meets once, in order: their nickname, then one ask for an
 * email (a way in that works without Telegram). */
export function FirstRun({ onDone }: { onDone: () => void }) {
  const { me } = useApp();
  const [step, setStep] = useState<"nick" | "email">(me.handle?.confirmed === false ? "nick" : "email");
  if (step === "nick") {
    return <Nickname onNext={() => (me.email_prompt ? setStep("email") : onDone())} />;
  }
  return <AddEmail onDone={onDone} />;
}

function Nickname({ onNext }: { onNext: () => void }) {
  const { me, data, tr, setMe, locale } = useApp();
  const [name, setName] = useState(me.handle?.name ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const valid = /^[A-Za-z0-9]{3,20}$/.test(name);
  const changed = name !== (me.handle?.name ?? "");

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      let next = me;
      if (changed) next = await userApi.putHandle(data, name);
      next = await userApi.confirmHandle(data);
      setMe(next);
      onNext();
    } catch (err) {
      setError(
        err instanceof ApiError && err.code === "too_soon"
          ? tr("nicknameTooSoon")
          : err instanceof ApiError && err.code === "invalid"
            ? tr("nicknameInvalid")
            : errorText(err, locale),
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      className="firstrun"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) void save();
      }}
    >
      <span className="firstrun-face">
        <Face personId={me.person_id} name={name || "?"} size={96} />
      </span>
      <h1 className="t-headline">{tr("nicknameTitle")}</h1>
      <p className="t-body">{tr("nicknameIntro")}</p>
      <Field
        value={name}
        autoCapitalize="off"
        autoCorrect="off"
        spellCheck={false}
        maxLength={20}
        icon="user"
        onChange={(e) => setName(e.target.value.replace(/[^A-Za-z0-9]/g, ""))}
        hint={error ? null : tr("nicknameHint")}
        error={error}
      />
      <div className="firstrun-actions">
        <Button wide type="submit" busy={busy} disabled={!valid}>
          {changed ? tr("nicknameSave") : tr("nicknameKeep")}
        </Button>
      </div>
    </form>
  );
}

function AddEmail({ onDone }: { onDone: () => void }) {
  const { data, tr, locale, reloadMe } = useApp();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const later = async () => {
    await userApi.emailLater(data).catch(() => undefined);
    onDone();
  };

  const finish = async () => {
    await reloadMe();
    onDone();
  };

  const send = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await userApi.emailLinkStart(data, email.trim());
      if (res.skip_code) {
        await userApi.emailLinkVerify(data, email.trim(), "000000");
        await finish();
        return;
      }
      setSent(res.resend_after);
    } catch (err) {
      setError(errorText(err, locale));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="firstrun">
      <h1 className="t-headline">{tr("addEmailTitle")}</h1>
      <p className="t-body">{tr("addEmailText")}</p>
      {sent === null ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
          className="signin-form"
        >
          <Field
            type="email"
            inputMode="email"
            autoComplete="email"
            icon="mail"
            placeholder={tr("emailPlaceholder")}
            value={email}
            error={error}
            onChange={(e) => setEmail(e.target.value)}
          />
          <Button wide type="submit" busy={busy} disabled={!email.includes("@")}>
            {tr("emailGetCode")}
          </Button>
        </form>
      ) : (
        <CodeEntry
          locale={locale}
          email={email.trim()}
          resendAfter={sent}
          onVerify={async (code) => {
            await userApi.emailLinkVerify(data, email.trim(), code);
            await finish();
          }}
          onResend={async () => (await userApi.emailLinkStart(data, email.trim())).resend_after}
          onChangeAddress={() => setSent(null)}
        />
      )}
      <Button variant="text" onClick={() => void later()}>
        {tr("addEmailLater")}
      </Button>
    </div>
  );
}
