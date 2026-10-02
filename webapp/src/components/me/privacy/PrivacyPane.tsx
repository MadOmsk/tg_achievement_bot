import { useEffect, useState } from "react";
import { peopleApi, type ActivityVisible, type PersonRow } from "../../../api/people/peopleApi";
import { t, type Locale } from "../../../i18n";
import { BackHead } from "../../shared/lib";

const CHOICES: Array<{ value: ActivityVisible; key: "privacyAll" | "privacyFriends" | "privacyNobody" }> = [
  { value: "all", key: "privacyAll" },
  { value: "friends", key: "privacyFriends" },
  { value: "nobody", key: "privacyNobody" },
];

/** The one privacy setting (#157): who sees my activity in the app. The nickname
 * and avatar stay visible; publishing to chats is a separate screen. Below it,
 * the people you blocked, each with a way to undo it. */
export function PrivacyPane({
  locale,
  data,
  onBack,
  onFlash,
}: {
  locale: Locale;
  data: string;
  onBack: () => void;
  onFlash: (message: string) => void;
}) {
  const [value, setValue] = useState<ActivityVisible | null>(null);
  const [blocked, setBlocked] = useState<PersonRow[]>([]);

  useEffect(() => {
    const fail = (err: unknown) => onFlash(`${t(locale, "error")}: ${String(err)}`);
    peopleApi.privacy(data).then((res) => setValue(res.activity_visible)).catch(fail);
    peopleApi.blocked(data).then((res) => setBlocked(res.people)).catch(fail);
  }, [data, locale, onFlash]);

  const choose = (next: ActivityVisible) => {
    const previous = value;
    setValue(next);
    peopleApi.setPrivacy(data, next).catch((err: unknown) => {
      setValue(previous);
      onFlash(`${t(locale, "error")}: ${String(err)}`);
    });
  };

  return (
    <>
      <BackHead title={t(locale, "privacy")} backLabel={t(locale, "back")} onBack={onBack} />
      <p className="kicker">{t(locale, "privacyWho")}</p>
      <div className="glass-card">
        {CHOICES.map((choice) => (
          <button
            key={choice.value}
            type="button"
            className="ios-row"
            onClick={() => choose(choice.value)}
          >
            <span>{t(locale, choice.key)}</span>
            {value === choice.value && <span className="ios-value">✓</span>}
          </button>
        ))}
      </div>
      <p className="settings-hint">{t(locale, "privacyHint")}</p>

      {blocked.length > 0 && (
        <>
          <p className="kicker">{t(locale, "blockedTitle")}</p>
          <div className="glass-card">
            {blocked.map((row) => (
              <div key={row.id} className="ios-row">
                <span>{row.handle}</span>
                <button
                  type="button"
                  className="btn sm"
                  onClick={() =>
                    void peopleApi
                      .unblock(data, row.id)
                      .then(() => setBlocked((rows) => rows.filter((item) => item.id !== row.id)))
                      .catch((err: unknown) => onFlash(`${t(locale, "error")}: ${String(err)}`))
                  }
                >
                  {t(locale, "unblock")}
                </button>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}
