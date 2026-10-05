import { t, type Locale } from "../../../i18n";
import { Avatar, EmptyState, Icon } from "../../shared/lib";
import { HandleName } from "../../shared/lib/handle-name/HandleName";

/** A profile whose owner keeps their activity from this viewer (#157): the same
 * bar as any profile — back, avatar, nickname — and, below it, only the card that
 * says so. Reached like any profile: the friends strip, a feed author, a link. */
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
      <header className="account-bar person-bar">
        <div className="account-top">
          <button
            type="button"
            className="person-back"
            onClick={onBack}
            aria-label={t(locale, "back")}
          >
            <Icon name="back" size={26} />
          </button>
          <div className="account-who">
            <Avatar name={name} tgId={tgId} size={48} />
            <span className="person-bar-title">
              <span className="account-name-row">
                <strong>
                  <HandleName text={name} />
                </strong>
              </span>
            </span>
          </div>
        </div>
      </header>
      <EmptyState
        title={t(locale, "activityHidden")}
        hint={t(locale, "activityHiddenHint")}
        icon="lock"
        slide
      />
    </>
  );
}
