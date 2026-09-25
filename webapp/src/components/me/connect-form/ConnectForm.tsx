import { useState } from "react";
import { t, type Locale } from "../../../i18n";
import { BackHead, PlatformLogo } from "../../shared/lib";
import { PLATFORMS } from "../../shared/constants";

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
  const title = platform === PLATFORMS.STEAM ? "Steam" : "PlayStation";

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
      <BackHead
        title={t(locale, "connect")}
        backLabel={t(locale, "back")}
        onBack={onBack}
      />
      <form
        className="glass-card connect-form"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <div className="connect-form-head">
          <PlatformLogo platform={platform} size={40} />
          <span>
            <strong>{title}</strong>
            <p>{label}</p>
          </span>
        </div>
        <input
          className="input wide"
          value={value}
          placeholder={
            platform === PLATFORMS.STEAM
              ? "steamcommunity.com/id/…"
              : "Online ID"
          }
          onChange={(e) => setValue(e.target.value)}
          autoCapitalize="off"
          autoCorrect="off"
          spellCheck={false}
          enterKeyHint="done"
          autoFocus
        />
        {note && <p className="plat-note is-error">{note}</p>}
        <button type="submit" className="btn" disabled={!value.trim() || busy}>
          {t(locale, "submit")}
        </button>
      </form>
    </>
  );
}
