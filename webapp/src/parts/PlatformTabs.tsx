import { tick } from "../core/haptic";
import { PlatformMark } from "./AccountCard";

const NAME: Record<string, string> = {
  xbox: "Xbox",
  xbox_modern: "Xbox",
  xbox_360: "Xbox 360",
  psn: "PlayStation",
  steam: "Steam",
};

/** One game's lists on several platforms, one shown at a time: a pill each,
 * its platform's mark, name and what was earned there. */
export function PlatformTabs({
  lists,
  value,
  onChange,
  className = "",
}: {
  lists: { platform: string; title_id: string; count?: number }[];
  value: string;
  onChange: (key: string) => void;
  className?: string;
}) {
  return (
    <div className={`plat-tabs ${className}`} role="radiogroup">
      {lists.map((l) => {
        const key = `${l.platform}:${l.title_id}`;
        const on = key === value;
        return (
          <button
            key={key}
            type="button"
            role="radio"
            aria-checked={on}
            className={`plat-tab${on ? " plat-tab-on" : ""}`}
            onClick={() => {
              if (on) return;
              tick();
              onChange(key);
            }}
          >
            <PlatformMark platform={l.platform} size={24} />
            <span>{NAME[l.platform] ?? l.platform}</span>
            {l.count != null && <b className="t-num">{l.count}</b>}
          </button>
        );
      })}
    </div>
  );
}
