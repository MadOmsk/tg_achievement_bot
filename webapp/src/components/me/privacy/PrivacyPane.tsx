import { useEffect, useState } from "react";
import { peopleApi, type ActivityVisible, type PersonRow } from "../../../api/people/peopleApi";
import { t, type Locale } from "../../../i18n";
import { BackHead, CheckRow, Group, InfoRow, RowLink, SettingsSkel } from "../../shared/lib";

const CHOICES: Array<{ value: ActivityVisible; key: "privacyAll" | "privacyFriends" | "privacyNobody" }> = [
  { value: "all", key: "privacyAll" },
  { value: "friends", key: "privacyFriends" },
  { value: "nobody", key: "privacyNobody" },
];

/** The one privacy setting (#157): who sees my activity in the app. Below it, the
 * people you blocked, each with a way to undo it. */
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
      {value === null ? (
        <SettingsSkel groups={[3]} />
      ) : (
        <Group title={t(locale, "privacyWho")} hint={t(locale, "privacyHint")}>
          {CHOICES.map((choice) => (
            <CheckRow
              key={choice.value}
              label={t(locale, choice.key)}
              checked={value === choice.value}
              onClick={() => choose(choice.value)}
            />
          ))}
        </Group>
      )}

      {blocked.length > 0 && (
        <Group title={t(locale, "blockedTitle")}>
          {blocked.map((row) => (
            <InfoRow key={row.id} label={row.handle}>
              <RowLink
                onClick={() =>
                  void peopleApi
                    .unblock(data, row.id)
                    .then(() => setBlocked((rows) => rows.filter((item) => item.id !== row.id)))
                    .catch((err: unknown) => onFlash(`${t(locale, "error")}: ${String(err)}`))
                }
              >
                {t(locale, "unblock")}
              </RowLink>
            </InfoRow>
          ))}
        </Group>
      )}
    </>
  );
}
