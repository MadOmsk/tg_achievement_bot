import { useEffect, useRef, useState } from "react";
import type { Handle } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { Avatar, BackHead, showToast, telegramPhoto } from "../../shared/lib";
import { AvatarCropper } from "./AvatarCropper";

const VALID = /^[A-Za-z0-9]{3,20}$/;

/** Choose or change the nickname (#157). `first` is the screen a person sees
 * once, on their first visit: it asks them to keep the nickname they were given
 * or to pick another, and has no way back. Otherwise it is a Settings pane. */
export function NicknameForm({
  locale,
  handle,
  first,
  onBack,
  onSubmit,
  onKeep,
  tgId,
  avatarCustom,
  onAvatar,
  onAvatarReset,
}: {
  locale: Locale;
  handle: Handle;
  first?: boolean;
  onBack?: () => void;
  onSubmit: (value: string) => Promise<void>;
  onKeep?: () => Promise<void>;
  /** Whose face it is, and whether it is one chosen in the app. */
  tgId: number;
  avatarCustom?: boolean;
  onAvatar: (image: Blob) => Promise<void>;
  onAvatarReset: () => Promise<void>;
}) {
  const [value, setValue] = useState(handle.name);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  // A change is locked for a day after the last real one; the first choice
  // is free (the server decides, this only explains it).
  const waitUntil = !first && handle.next_change_at ? new Date(handle.next_change_at) : null;
  const locked = waitUntil !== null && waitUntil.getTime() > Date.now();
  const unchanged = value === handle.name;
  const valid = VALID.test(value);

  const send = () => {
    if (busy || locked || !valid) return;
    setBusy(true);
    setNote(null);
    const action = unchanged && onKeep ? onKeep() : onSubmit(value);
    void action
      .catch((err: unknown) => {
        const text = String(err);
        setNote(
          text.includes("too_soon")
            ? t(locale, "nicknameTooSoon")
            : text.includes("invalid")
              ? t(locale, "nicknameInvalid")
              : text,
        );
      })
      .finally(() => setBusy(false));
  };

  const shown = value || handle.name;
  // The digits stay while only the letters' case changes; any other name is
  // checked anew, and gets digits of its own only if it is taken.
  const tag =
    handle.number && value.toLowerCase() === handle.name.toLowerCase()
      ? `#${String(handle.number).padStart(4, "0")}`
      : null;
  const file = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  // A picked picture is placed in the circle first (AvatarCropper), which hands
  // back a 512 px square: small, and already the shape every avatar shows.
  const [picked, setPicked] = useState<File | null>(null);
  // While it uploads, the new face is already in the circle, under a turning ring.
  const [preview, setPreview] = useState<string | null>(null);
  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);
  const upload = (image: Blob) => {
    setPicked(null);
    setUploading(true);
    setNote(null);
    setPreview(URL.createObjectURL(image));
    void onAvatar(image)
      .then(() => showToast(t(locale, "avatarDone"), "success"))
      .catch(() => {
        setNote(t(locale, "avatarFailed"));
        setPreview(null);
      })
      .finally(() => setUploading(false));
  };

  return (
    <>
      {first ? null : (
        <BackHead
          title={t(locale, "profileLook")}
          backLabel={t(locale, "back")}
          onBack={onBack ?? (() => undefined)}
        />
      )}
      <form
        className={first ? "nick-stage is-first" : "nick-stage"}
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <div className="nick-hero">
          <span className="nick-avatar-wrap">
          <button
            type="button"
            className={uploading ? "nick-avatar is-busy" : "nick-avatar"}
            onClick={() => file.current?.click()}
            aria-label={t(locale, "avatarChange")}
          >
            <Avatar name={shown} photo={telegramPhoto()} tgId={tgId} size={168} />
            {preview && (
              <img className="nick-avatar-preview" src={preview} alt="" />
            )}
            {uploading && <span className="nick-avatar-spin" aria-hidden />}
          </button>
          {avatarCustom && (
            // Back to the Telegram photo: the badge at the lower right, after a question.
            <button
              type="button"
              className="nick-avatar-badge is-reset"
              aria-label={t(locale, "avatarReset")}
              title={t(locale, "avatarReset")}
              onClick={() => {
                if (!window.confirm(t(locale, "avatarResetConfirm"))) return;
                setPreview(null);
                setUploading(true);
                void onAvatarReset().finally(() => setUploading(false));
              }}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden>
                <path
                  d="M4 12a8 8 0 1 0 2.4-5.7M4 4v4h4"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          )}
          </span>
          <input
            ref={file}
            type="file"
            accept="image/*"
            hidden
            onChange={(e) => {
              const chosen = e.target.files?.[0];
              if (chosen) setPicked(chosen);
              e.target.value = "";
            }}
          />
          {first && <h1>{t(locale, "nicknameTitle")}</h1>}
          {first && <p className="nick-intro">{t(locale, "nicknameIntro")}</p>}
        </div>

        <label className={locked ? "nick-field is-locked" : "nick-field"}>
          <input
            value={value}
            onChange={(e) => setValue(e.target.value.replace(/[^A-Za-z0-9]/g, "").slice(0, 20))}
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
            enterKeyHint="done"
            maxLength={20}
            disabled={locked}
            aria-label={t(locale, "nickname")}
          />
          {/* The digits a taken name carries, on the right; while typing a new
              name, how long it is instead. */}
          {tag ? (
            <span className="nick-tag">{tag}</span>
          ) : (
            <span className="nick-count">{value.length}/20</span>
          )}
        </label>
        {(note || (locked && waitUntil)) && (
          <p className={note ? "nick-hint is-error" : "nick-hint"}>
            {note ?? `${t(locale, "nicknameNext")} ${waitUntil?.toLocaleDateString(locale)}`}
          </p>
        )}

        <button type="submit" className="btn nick-save" disabled={!valid || busy || locked || (unchanged && !first)}>
          {unchanged && first ? t(locale, "nicknameKeep") : t(locale, "nicknameSave")}
        </button>
      </form>
      {picked && (
        <AvatarCropper
          file={picked}
          locale={locale}
          onCancel={() => setPicked(null)}
          onDone={upload}
        />
      )}
    </>
  );
}
