import { useEffect, useState } from "react";
import { t, type Locale } from "../../../../i18n";
import { UMark } from "../wordmark/Wordmark";
import { installWay, onInstallChange, promptInstall, type InstallWay } from "./install";
import "./InstallPrompt.css";

const DISMISSED_KEY = "install-dismissed-at";
// Closed once, the banner rests this long before it offers again.
const REST_MS = 14 * 24 * 60 * 60 * 1000;

function restingNow(): boolean {
  try {
    const at = Number(localStorage.getItem(DISMISSED_KEY));
    return Boolean(at) && Date.now() - at < REST_MS;
  } catch {
    return false;
  }
}

/** «Поставь приложение на экран»: offered in a plain browser that can install
 * the app, above the dock, until it is installed or closed. */
export function InstallPrompt({ locale }: { locale: Locale }) {
  const [way, setWay] = useState<InstallWay>(() => installWay());
  const [resting, setResting] = useState(restingNow);

  useEffect(() => onInstallChange(() => setWay(installWay())), []);

  if (!way || resting) return null;

  const close = () => {
    try {
      localStorage.setItem(DISMISSED_KEY, String(Date.now()));
    } catch {
      // Private mode: it just comes back next time.
    }
    setResting(true);
  };

  return (
    <div className="install-prompt" role="dialog" aria-label={t(locale, "installTitle")}>
      <UMark className="install-logo" />
      <div className="install-text">
        <b>{t(locale, "installTitle")}</b>
        <span>{t(locale, way === "ios" ? "installIos" : "installText")}</span>
      </div>
      {way === "prompt" && (
        <button type="button" className="btn sm" onClick={() => void promptInstall()}>
          {t(locale, "installButton")}
        </button>
      )}
      <button type="button" className="install-close" onClick={close} aria-label={t(locale, "close")}>
        ×
      </button>
    </div>
  );
}
