import { useEffect, useState } from "react";
import { fetchAdminLimits, patchAdminLimit, type AdminLimit } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { BackHead, Group, NumberRow, SettingsSkel } from "../../shared/lib";

// Which group each limit belongs to; anything new and unlisted lands in "Other",
// so a setting added on the server shows up here with no change.
const GROUPS: Array<{ title: "limitsLists" | "limitsHltb" | "limitsTimers" | "limitsOther"; keys: string[] }> = [
  { title: "limitsLists", keys: ["summary_top_limit", "stats_games_limit", "recent_limit"] },
  { title: "limitsHltb", keys: ["hltb_results_limit", "hltb_page_size"] },
  {
    title: "limitsTimers",
    keys: [
      "system_message_ttl_min",
      "online_refresh_interval_min",
      "online_refresh_ttl_hours",
      "service_health_interval_min",
      "monthly_summary_delay_minutes",
      "patch_refresh_hours",
    ],
  },
];

export function AdminLimits({
  data,
  locale,
  onBack,
  onFail,
}: {
  data: string;
  locale: Locale;
  onBack: () => void;
  onFail: (err: unknown) => void;
}) {
  const [limits, setLimits] = useState<AdminLimit[] | null>(null);

  useEffect(() => {
    void fetchAdminLimits(data)
      .then((r) => setLimits(r.items))
      .catch(onFail);
  }, [data, onFail]);

  const row = (item: AdminLimit) => (
    <NumberRow
      key={item.key}
      label={item.label}
      sub={
        item.zero_means === "unlimited"
          ? t(locale, "limitZeroUnlimited")
          : item.zero_means === "off"
            ? t(locale, "limitZeroOff")
            : item.zero_means === "no_delay"
              ? t(locale, "limitZeroNoDelay")
              : undefined
      }
      value={item.value}
      min={item.min}
      max={item.max}
      onChange={(v) =>
        void patchAdminLimit(data, item.key, v)
          .then((r) => setLimits(r.items))
          .catch(onFail)
      }
    />
  );

  const listed = new Set(GROUPS.flatMap((g) => g.keys));
  const groups = limits
    ? [
        ...GROUPS.map((g) => ({
          title: g.title,
          items: g.keys
            .map((k) => limits.find((item) => item.key === k))
            .filter((item): item is AdminLimit => Boolean(item)),
        })),
        { title: "limitsOther" as const, items: limits.filter((item) => !listed.has(item.key)) },
      ].filter((g) => g.items.length > 0)
    : [];

  return (
    <>
      <BackHead title={t(locale, "adminLimits")} backLabel={t(locale, "back")} onBack={onBack} />
      {limits == null ? (
        <SettingsSkel groups={[3, 2, 6]} />
      ) : (
        groups.map((g) => (
          <Group key={g.title} title={t(locale, g.title)}>
            {g.items.map(row)}
          </Group>
        ))
      )}
    </>
  );
}
