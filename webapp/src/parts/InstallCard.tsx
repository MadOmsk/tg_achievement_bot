import { useEffect, useState } from "react";
import { useApp } from "../app/context";
import { installWay, onInstallChange, promptInstall, type InstallWay } from "../core/install";
import { Button, IconButton } from "../ui/Controls";

const REST_KEY = "install-dismissed-at";
const REST_MS = 14 * 24 * 3600 * 1000;

function resting(): boolean {
  try {
    const at = Number(localStorage.getItem(REST_KEY) ?? 0);
    return Date.now() - at < REST_MS;
  } catch {
    return false;
  }
}

/** Installing the app, offered in a browser that can: never inside Telegram
 * or once installed; dismissed, it rests two weeks. */
export function InstallCard() {
  const { tr } = useApp();
  const [way, setWay] = useState<InstallWay>(() => (resting() ? null : installWay()));
  useEffect(() => onInstallChange(() => setWay(resting() ? null : installWay())), []);
  if (!way) return null;
  const dismiss = () => {
    try {
      localStorage.setItem(REST_KEY, String(Date.now()));
    } catch {
      // No storage: it comes back next time.
    }
    setWay(null);
  };
  return (
    <section className="install">
      <img src={`${import.meta.env.BASE_URL}logo-192.png`} alt="" className="install-logo" />
      <div className="install-text">
        <p className="t-label">{tr("installTitle")}</p>
        <p className="t-meta">{way === "ios" ? tr("installIos") : tr("installText")}</p>
      </div>
      {way === "prompt" && (
        <Button variant="filled" className="btn-small" onClick={() => void promptInstall().then((ok) => ok && setWay(null))}>
          {tr("installButton")}
        </Button>
      )}
      <IconButton icon="close" label={tr("close")} variant="plain" onClick={dismiss} />
    </section>
  );
}
