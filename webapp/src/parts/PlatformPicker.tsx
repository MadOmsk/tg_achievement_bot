import { useState } from "react";
import { useApp } from "../app/context";
import { tick } from "../core/haptic";
import { Row } from "../ui/Controls";
import { Icon } from "../ui/Icon";
import { Sheet } from "../ui/Page";
import { PlatformMark } from "./AccountCard";

const NAME: Record<string, string> = {
  xbox: "Xbox",
  xbox_modern: "Xbox",
  xbox_360: "Xbox 360",
  psn: "PlayStation",
  steam: "Steam",
};

type PickerList = { platform: string; title_id: string; count?: number; total?: number | null };

/** One game's lists on several platforms, one shown at a time — chosen as
 * the month is: one chip, and a sheet of them with what was earned on each. */
export function PlatformPicker({
  lists,
  value,
  onChange,
  className = "",
}: {
  lists: PickerList[];
  value: string;
  onChange: (key: string) => void;
  className?: string;
}) {
  const { tr } = useApp();
  const [open, setOpen] = useState(false);
  const shown = lists.find((l) => `${l.platform}:${l.title_id}` === value) ?? lists[0];
  const score = (l: PickerList) => (l.count == null ? null : l.total ? `${l.count} / ${l.total}` : String(l.count));
  return (
    <>
      <button
        type="button"
        className={`plat-pick ${className}`}
        onClick={() => {
          tick();
          setOpen(true);
        }}
      >
        <PlatformMark platform={shown.platform} size={24} />
        <span>{NAME[shown.platform] ?? shown.platform}</span>
        <Icon name="down" size={18} />
      </button>
      {open && (
        <Sheet title={tr("pickPlatform")} onClose={() => setOpen(false)} layer="platforms">
          <div className="group">
            <div className="group-items">
              {lists.map((l) => {
                const key = `${l.platform}:${l.title_id}`;
                const on = key === value;
                return (
                  <Row
                    key={key}
                    className={on ? "plat-pick-on" : ""}
                    lead={<PlatformMark platform={l.platform} size={40} />}
                    title={NAME[l.platform] ?? l.platform}
                    sub={score(l) ?? undefined}
                    trail={on ? <Icon name="check" size={20} /> : undefined}
                    onClick={() => {
                      tick();
                      setOpen(false);
                      if (!on) onChange(key);
                    }}
                  />
                );
              })}
            </div>
          </div>
        </Sheet>
      )}
    </>
  );
}
