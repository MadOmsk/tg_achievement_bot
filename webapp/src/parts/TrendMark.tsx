import { useApp } from "../app/context";
import { num } from "../i18n";

/** How many achievements people here got in a trending game, on its cover's
 * corner as an achievement wears its rarity: a flower with the number. */
export function TrendMark({ count }: { count: number }) {
  const { tr, locale } = useApp();
  return (
    <span className="trend-mark shape-flower6">
      <b className="t-num">{num(count, locale)}</b>
      <small>{tr("achShort")}</small>
    </span>
  );
}
