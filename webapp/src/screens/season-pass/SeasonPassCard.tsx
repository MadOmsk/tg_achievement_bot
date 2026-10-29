import { useApp } from "../../app/context";
import { passProgress, usePass } from "../../core/season-pass";
import "./SeasonPass.css";

/** The door to the season pass in Home's month card. It shows how far the
 * month's points stand: the way to the next level fills it; a count of the
 * rewards waiting to be claimed rides on it. */
export function PassStrip() {
  const { data, tr, open } = useApp();
  const progress = passProgress(usePass(data));
  const { next, points, from, due } = progress;
  const share = next ? Math.max(0, Math.min(1, (points - from) / Math.max(1, next.points - from))) : 1;
  return (
    <button type="button" className="hero-pass" onClick={() => open({ kind: "pass" })}>
      <span className="hero-pass-fill" style={{ width: `${share * 100}%` }} aria-hidden="true" />
      {tr("passOpen")}
      {due > 0 && <b className="hero-pass-count t-num">{due}</b>}
    </button>
  );
}
