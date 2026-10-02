import { useEffect, useState } from "react";
import { peopleApi, type ActivityVisible, type PersonRow } from "../../../api/people/peopleApi";
import { t, type Locale } from "../../../i18n";
import { BackHead, Group, InfoRow, SelectRow, SettingsSkel } from "../../shared/lib";

/** Privacy (#157): who sees my activity in the app, then the people blocked. More
 * privacy settings, when there are any, join this screen. */
export function PrivacyPane({
  locale,
  data,
  initial,
  onBack,
  onFlash,
}: {
  locale: Locale;
  data: string;
  initial: ActivityVisible;
  onBack: () => void;
  onFlash: (message: string) => void;
}) {
  const [value, setValue] = useState<ActivityVisible>(initial);
  const [blocked, setBlocked] = useState<PersonRow[] | null>(null);
  const fail = (err: unknown) => onFlash(`${t(locale, "error")}: ${String(err)}`);

  useEffect(() => {
    peopleApi
      .blocked(data)
      .then((res) => setBlocked(res.people))
      .catch((err: unknown) => onFlash(`${t(locale, "error")}: ${String(err)}`));
  }, [data, locale, onFlash]);

  const choose = (next: ActivityVisible) => {
    const previous = value;
    setValue(next);
    peopleApi.setPrivacy(data, next).catch((err: unknown) => {
      setValue(previous);
      fail(err);
    });
  };

  return (
    <>
      <BackHead title={t(locale, "privacy")} backLabel={t(locale, "back")} onBack={onBack} />
      <Group>
        <SelectRow
          label={t(locale, "privacyWho")}
          sub={t(locale, "privacyHint")}
          value={value}
          options={[
            { value: "all" as ActivityVisible, label: t(locale, "privacyAll") },
            { value: "friends" as ActivityVisible, label: t(locale, "privacyFriends") },
            { value: "nobody" as ActivityVisible, label: t(locale, "privacyNobody") },
          ]}
          onChange={choose}
        />
      </Group>

      {blocked === null ? (
        <SettingsSkel groups={[1]} />
      ) : (
        blocked.length > 0 && (
          <Group title={t(locale, "blockedTitle")}>
            {blocked.map((row) => (
              <InfoRow key={row.id} label={row.handle}>
                <button
                  type="button"
                  className="btn sm is-quiet"
                  onClick={() =>
                    void peopleApi
                      .unblock(data, row.id)
                      .then(() => setBlocked((rows) => (rows ?? []).filter((item) => item.id !== row.id)))
                      .catch(fail)
                  }
                >
                  {t(locale, "unblock")}
                </button>
              </InfoRow>
            ))}
          </Group>
        )
      )}
    </>
  );
}
