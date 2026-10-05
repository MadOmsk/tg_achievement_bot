import { useState } from "react";
import { userApi, type MergeChoices, type MergePreview, type MergeSide } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { CheckRow, Group, PlatformLogo, Sheet } from "../../shared/lib";
import { PLATFORMS } from "../../shared/constants";
import "./Logins.css";

type Side = "keep" | "absorb";

const PLATFORM_NAMES: Record<string, string> = { xbox: "Xbox", psn: "PlayStation", steam: "Steam" };
const PLATFORM_MARKS: Record<string, string> = {
  xbox: PLATFORMS.XBOX,
  psn: PLATFORMS.PSN,
  steam: PLATFORMS.STEAM,
};

/** What one side brings, in a line or two. */
function SideCard({ side, title, locale }: { side: MergeSide; title: string; locale: Locale }) {
  const accounts = Object.entries(side.accounts).flatMap(([platform, items]) =>
    items.map((item) => ({ platform, name: item.name || item.id })),
  );
  return (
    <div className="merge-side glass">
      <small>{title}</small>
      <strong>{side.handle}</strong>
      <span className="merge-facts">
        {side.email && <span>{side.email}</span>}
        {side.has_telegram && <span>Telegram{side.telegram ? ` · ${side.telegram}` : ""}</span>}
        {accounts.map((item) => (
          <span key={`${item.platform}:${item.name}`} className="merge-account">
            <PlatformLogo platform={PLATFORM_MARKS[item.platform] ?? item.platform} size={14} />
            {item.name}
          </span>
        ))}
        {side.follows + side.chats > 0 && (
          <span>
            {t(locale, "mergeFollows")} {side.follows} · {t(locale, "mergeChats")} {side.chats}
          </span>
        )}
      </span>
    </div>
  );
}

/** The merge of two accounts that turned out to be one person (#162): what each
 * brings, a choice wherever both have something, and the person's word. The
 * account signed in now stays, with its nickname. */
export function MergeSheet({
  preview,
  data,
  locale,
  onDone,
  onClose,
}: {
  preview: MergePreview;
  data: string;
  locale: Locale;
  onDone: () => void;
  onClose: () => void;
}) {
  const conflicts = preview.conflicts;
  const [choices, setChoices] = useState<MergeChoices>(() => {
    const start: MergeChoices = {};
    for (const name of ["xbox", "steam", "email"] as const) if (conflicts[name]) start[name] = "keep";
    // An admin's Telegram is never let go: it is the one picked from the start.
    if (conflicts.telegram) start.telegram = conflicts.telegram.absorb.admin ? "absorb" : "keep";
    if (conflicts.psn) start.psn = conflicts.psn.accounts.slice(0, conflicts.psn.max).map((a) => a.id);
    return start;
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pick = (name: "xbox" | "steam" | "email" | "telegram", side: Side) =>
    setChoices((current) => ({ ...current, [name]: side }));

  const pairRows = (
    name: "xbox" | "steam" | "email" | "telegram",
    label: (side: Side) => string,
    locked?: (side: Side) => boolean,
  ) =>
    (["keep", "absorb"] as const).map((side) => (
      <CheckRow
        key={side}
        label={label(side)}
        sub={t(locale, side === "keep" ? "mergeThisSide" : "mergeOtherSide")}
        checked={choices[name] === side}
        onClick={() => {
          if (locked?.(side === "keep" ? "absorb" : "keep")) return;
          pick(name, side);
        }}
      />
    ));

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await userApi.merge(data, choices);
      onDone();
    } catch (err) {
      setError(String(err).includes("admin") ? t(locale, "mergeAdmin") : `${t(locale, "error")}: ${String(err)}`);
    } finally {
      setBusy(false);
    }
  };

  const psnPicked = new Set(choices.psn ?? []);
  const psnOk = !conflicts.psn || (psnPicked.size > 0 && psnPicked.size <= conflicts.psn.max);

  return (
    <Sheet tall onClose={onClose}>
      <div className="sheet-content merge-sheet">
        <h2>{t(locale, "mergeTitle")}</h2>
        <p className="merge-text">{t(locale, "mergeText")}</p>
        <div className="merge-sides">
          <SideCard side={preview.keep} title={t(locale, "mergeThis")} locale={locale} />
          <SideCard side={preview.absorb} title={t(locale, "mergeOther")} locale={locale} />
        </div>

        {(["xbox", "steam"] as const).map((platform) => {
          const conflict = conflicts[platform];
          if (!conflict) return null;
          return (
            <Group key={platform} title={PLATFORM_NAMES[platform]} hint={t(locale, "mergeAccountHint")}>
              {pairRows(platform, (side) => conflict[side].name || conflict[side].id)}
            </Group>
          );
        })}
        {conflicts.psn && (
          <Group title="PlayStation" hint={`${t(locale, "mergePsnHint")} ${conflicts.psn.max}`}>
            {conflicts.psn.accounts.map((account) => (
              <CheckRow
                key={account.id}
                label={account.name || account.id}
                checked={psnPicked.has(account.id)}
                onClick={() => {
                  const next = new Set(psnPicked);
                  if (next.has(account.id)) next.delete(account.id);
                  else next.add(account.id);
                  setChoices((current) => ({ ...current, psn: [...next] }));
                }}
              />
            ))}
          </Group>
        )}
        {conflicts.telegram && (
          <Group title="Telegram" hint={t(locale, "mergeTelegramHint")}>
            {pairRows(
              "telegram",
              (side) => conflicts.telegram?.[side].name || "Telegram",
              (side) => Boolean(conflicts.telegram?.[side].admin),
            )}
          </Group>
        )}
        {conflicts.email && (
          <Group title={t(locale, "emailTitle")}>
            {pairRows("email", (side) => conflicts.email?.[side] ?? "")}
          </Group>
        )}

        {error && <p className="email-note is-error">{error}</p>}
        <div className="merge-actions">
          <button type="button" className="btn" disabled={busy || !psnOk} onClick={() => void submit()}>
            {t(locale, "mergeDo")}
          </button>
          <button
            type="button"
            className="see-all"
            disabled={busy}
            onClick={() => {
              void userApi.cancelMerge(data).catch(() => undefined);
              onClose();
            }}
          >
            {t(locale, "mergeNotNow")}
          </button>
        </div>
      </div>
    </Sheet>
  );
}
