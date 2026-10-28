import { useApp } from "../../app/context";
import { passProgress, usePass } from "../../core/season-pass";
import { Icon } from "../../ui/Icon";
import "./SeasonPass.css";

/** The door to the season pass in Home's month card; a count of the rewards
 * waiting to be claimed rides on it. */
export function PassStrip() {
  const { data, tr, open } = useApp();
  const waiting = passProgress(usePass(data)).due;
  return (
    <button type="button" className="hero-pass" onClick={() => open({ kind: "pass" })}>
      <Icon name="crown" size={18} />
      {tr("passOpen")}
      {waiting > 0 && <b className="hero-pass-count t-num">{waiting}</b>}
    </button>
  );
}
