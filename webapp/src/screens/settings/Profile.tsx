import { useRef, useState } from "react";
import { ApiError, userApi } from "../../api";
import { useApp } from "../../app/context";
import { formatWhen } from "../../i18n";
import { Button, Field, Group, Row } from "../../ui/Controls";
import { Face } from "../../ui/Face";
import { Icon } from "../../ui/Icon";
import { Cropper } from "../../ui/Cropper";
import { Confirm } from "../../ui/Page";


export function ProfilePane() {
  const { me, data, tr, setMe, toast, locale, open } = useApp();
  const [name, setName] = useState(me.handle?.name ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(0);
  const [picked, setPicked] = useState<string | null>(null);
  const [askReset, setAskReset] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  const valid = /^[A-Za-z0-9]{3,20}$/.test(name);
  const changed = name !== (me.handle?.name ?? "");
  const next = me.handle?.next_change_at;
  const onlyCase = changed && name.toLowerCase() === (me.handle?.name ?? "").toLowerCase();

  const saveName = async () => {
    setBusy(true);
    setError(null);
    try {
      setMe(await userApi.putHandle(data, name));
      toast(tr("nicknameSaved"));
    } catch (err) {
      setError(err instanceof ApiError && err.code === "too_soon" ? tr("nicknameTooSoon") : tr("nicknameInvalid"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="pf-face">
        <Face personId={me.person_id} name={me.handle?.display ?? ""} size={128} version={version} />
        <div className="pf-face-actions">
          <Button variant="tonal" icon="image" onClick={() => file.current?.click()}>
            {tr("avatarChange")}
          </Button>
          {me.avatar_custom && me.tg_id != null && (
            <Button variant="text" onClick={() => setAskReset(true)}>
              {tr("avatarReset")}
            </Button>
          )}
        </div>
        <input
          ref={file}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (f) setPicked(URL.createObjectURL(f));
          }}
        />
      </div>

      <Group title={tr("nickname")}>
        <form
          className="set-pad set-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (valid && changed) void saveName();
          }}
        >
          <Field
            value={name}
            icon="user"
            maxLength={20}
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
            onChange={(e) => setName(e.target.value.replace(/[^A-Za-z0-9]/g, ""))}
            error={error}
            hint={
              error
                ? null
                : next && !onlyCase
                  ? `${tr("nicknameNext")} ${formatWhen(next, locale)}`
                  : me.handle?.number
                    ? `${tr("nicknameHint")} ${tr("nicknameDigits")} ${me.handle.display}`
                    : tr("nicknameHint")
            }
          />
          {changed && (
            <Button type="submit" busy={busy} disabled={!valid}>
              {tr("nicknameSave")}
            </Button>
          )}
        </form>
      </Group>
      <Group>
        <Row lead={<Icon name="user" />} title={tr("profileOpenCard")} chevron onClick={() => open({ kind: "person", personId: me.person_id })} />
      </Group>

      {picked && (
        <Cropper
          src={picked}
          title={tr("avatarPlace")}
          round
          size={512}
          onCancel={() => {
            URL.revokeObjectURL(picked);
            setPicked(null);
          }}
          onDone={async (blob) => {
            URL.revokeObjectURL(picked);
            setPicked(null);
            try {
              setMe(await userApi.putAvatar(data, blob));
              setVersion(Date.now());
              toast(tr("avatarDone"));
            } catch {
              toast(tr("avatarFailed"), "error");
            }
          }}
        />
      )}
      {askReset && (
        <Confirm
          text={tr("avatarResetConfirm")}
          yes={tr("avatarReset")}
          no={tr("cancel")}
          onYes={async () => {
            setAskReset(false);
            try {
              setMe(await userApi.deleteAvatar(data));
              setVersion(Date.now());
            } catch {
              toast(tr("somethingWrong"), "error");
            }
          }}
          onNo={() => setAskReset(false)}
        />
      )}
    </>
  );
}
