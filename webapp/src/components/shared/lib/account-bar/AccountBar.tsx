import type { MeResponse } from "../../../../api";
import { t, type Locale } from "../../../../i18n";
import { Avatar, accountLabel, telegramPhoto } from "../avatar/Avatar";
import { ScoreCup, meScoreLines } from "../score-cup/ScoreCup";
import "./AccountBar.css";

export function AccountBar({
  me,
  locale,
  onProfile,
  status,
  score = true,
}: {
  me: MeResponse;
  locale: Locale;
  onProfile: () => void;
  /** What the person is doing now, written after the nick. */
  status?: string | null;
  score?: boolean;
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
            <em className="hello">{t(locale, "hello")}</em>
            <strong>{name}</strong>
            {status && <small className="account-status">{status}</small>}
          </span>
        </button>
        {score && <ScoreCup locale={locale} lines={meScoreLines(me, locale)} />}
      </div>
    </header>
  );
}
