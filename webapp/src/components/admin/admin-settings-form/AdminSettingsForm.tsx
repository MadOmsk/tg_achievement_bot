import type { AdminSetting, AdminSettingsGroup } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { Group, NumberRow, SelectRow, ToggleRow } from "../../shared/lib";

type Value = AdminSetting["value"];

const ZERO = {
  unlimited: "limitZeroUnlimited",
  off: "limitZeroOff",
  no_delay: "limitZeroNoDelay",
} as const;

/** The server's settings registry drawn as rows (#176): a number with its
 * bounds, a switch, or a pick from a list — whatever the server lists, so a
 * new admin setting needs no change here. */
export function AdminSettingsForm({
  groups,
  locale,
  onChange,
}: {
  groups: AdminSettingsGroup[];
  locale: Locale;
  onChange: (key: string, value: Value) => void;
}) {
  const row = (item: AdminSetting) => {
    if (item.kind === "bool") {
      return (
        <ToggleRow
          key={item.key}
          label={item.label}
          sub={item.hint ?? undefined}
          on={Boolean(item.value)}
          onChange={(on) => onChange(item.key, on)}
        />
      );
    }
    if (item.options.length > 0) {
      return (
        <SelectRow
          key={item.key}
          label={item.label}
          sub={item.hint ?? undefined}
          value={item.value as string | number}
          options={item.options.map((o) => ({ value: o.value as string | number, label: o.label }))}
          onChange={(v) => onChange(item.key, v)}
        />
      );
    }
    return (
      <NumberRow
        key={item.key}
        label={item.label}
        sub={item.hint ?? (item.zero_means ? t(locale, ZERO[item.zero_means]) : undefined)}
        value={Number(item.value)}
        min={item.min ?? undefined}
        max={item.max ?? undefined}
        decimal={item.kind === "float"}
        onChange={(v) => onChange(item.key, v)}
      />
    );
  };

  return (
    <>
      {groups.map((g) => (
        <Group key={g.id} title={g.title}>
          {g.items.map(row)}
        </Group>
      ))}
    </>
  );
}
