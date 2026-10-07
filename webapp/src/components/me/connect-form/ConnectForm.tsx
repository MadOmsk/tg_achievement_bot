import { useState } from "react";
import { t, type Locale } from "../../../i18n";
import { BackHead, PlatformLogo } from "../../shared/lib";
import { PLATFORMS } from "../../shared/constants";
import "./ConnectForm.css";

/** Linking a Steam or PlayStation account: one field for who you are there, and
 * what the bot needs from that account's privacy to see anything. */
export function ConnectForm({
  locale,
  platform,
  label,
  onBack,
  onSubmit,
}: {
  locale: Locale;
  platform: "steam" | "psn";
  label: string;
  onBack: () => void;
  onSubmit: (identity: string) => Promise<void>;
}) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const steam = platform === PLATFORMS.STEAM;
  const title = steam ? "Steam" : "PlayStation";

  const send = () => {
    if (!value.trim() || busy) return;
    setBusy(true);
    setNote(null);
    void onSubmit(value.trim())
      .catch((err: unknown) => setNote(String(err)))
      .finally(() => setBusy(false));
  };

  return (
    <>
      <BackHead title={t(locale, "connect")} backLabel={t(locale, "back")} onBack={onBack} />
      <form
        className={`connect-stage is-${platform}`}
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <div className="connect-hero">
          <span className="connect-mark">
            <PlatformLogo platform={platform} size={56} />
          </span>
          <h1>{title}</h1>
          <p>{label}</p>
        </div>

        <label className={note ? "field is-error" : "field"}>
          <input
            value={value}
            placeholder={steam ? "steamcommunity.com/id/…" : "Online ID"}
            onChange={(e) => setValue(e.target.value)}
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
            enterKeyHint="done"
            autoFocus
            aria-label={label}
          />
        </label>
        {note && <p className="field-note is-error">{note}</p>}

        <ul className="connect-tips">
          <li>{t(locale, steam ? "connectSteamTip" : "connectPsnTip")}</li>
          <li>{t(locale, "connectHistoryTip")}</li>
        </ul>

        <button type="submit" className="btn is-wide" disabled={!value.trim() || busy}>
          {busy ? <span className="connect-spin" aria-hidden /> : t(locale, "submit")}
        </button>
      </form>
    </>
  );
}
