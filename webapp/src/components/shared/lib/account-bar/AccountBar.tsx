import type { ReactNode } from "react";
import type { MeResponse } from "../../../../api";
import { t, type Locale } from "../../../../i18n";
import { Avatar, accountLabel, telegramPhoto } from "../avatar/Avatar";
import "./AccountBar.css";
import { HandleName } from "../handle-name/HandleName";

export function AccountBar({
  me,
  locale,
  onProfile,
  status,
  plats,
}: {
  me: MeResponse;
  locale: Locale;
  onProfile: () => void;
  /** What the person is doing now, written after the nick. */
  status?: string | null;
  /** Small, subtle platform marks after the nick. */
  plats?: ReactNode;
}) {
  const name = accountLabel(me);
  return (
    <header className="account-bar">
      <div className="account-top">
        <button type="button" className="account-who" onClick={onProfile}>
          <Avatar
            name={name}
            photo={telegramPhoto()}
            tgId={me.tg_id}
            size={48}
            zoomLabel={t(locale, "close")}
          />
          <span>
            <span className="account-name-row">
              <strong>
                <HandleName text={name} />
              </strong>
              {plats}
            </span>
            {status && <small className="account-status">{status}</small>}
          </span>
        </button>
      </div>
    </header>
  );
}
