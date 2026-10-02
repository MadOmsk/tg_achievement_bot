import { t, type Locale } from "../../../i18n";
import { Avatar, BackHead, EmptyState } from "../../shared/lib";

/** What a profile shows when its owner keeps their activity private (#157): the
 * nickname and avatar, nothing they did. */
export function HiddenProfile({
  tgId,
  name,
  locale,
  onBack,
}: {
  tgId: number;
  name: string;
  locale: Locale;
  onBack: () => void;
}) {
  return (
    <>
      <BackHead title={name} backLabel={t(locale, "back")} onBack={onBack} />
      <div className="hidden-profile">
        <Avatar name={name} tgId={tgId} size={88} />
      </div>
      <EmptyState title={t(locale, "activityHidden")} />
    </>
  );
}
