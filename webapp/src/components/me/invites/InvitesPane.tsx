import { useEffect, useState } from "react";
import { userApi, type InviteItem } from "../../../api";
import { formatWhen, t, type Locale } from "../../../i18n";
import { Avatar, BackHead, Group, Icon, InfoRow, SettingsSkel, showToast } from "../../shared/lib";
import "./Invites.css";

/** Settings → «Пригласить друга» (owner, 2026-10-05): somebody new signs up in a
 * browser only with a code a member made. One code lets one person in; it does
 * not expire, and a member may make as many as they like. */
export function InvitesPane({
  locale,
  data,
  onBack,
  onOpenPerson,
}: {
  locale: Locale;
  data: string;
  onBack: () => void;
  onOpenPerson?: (personId: number) => void;
}) {
  const [items, setItems] = useState<InviteItem[] | null>(null);
  const [linkBase, setLinkBase] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const fail = (err: unknown) => showToast(`${t(locale, "error")}: ${String(err)}`, "error");

  useEffect(() => {
    void userApi
      .invites(data)
      .then((res) => {
        setItems(res.items);
        setLinkBase(res.link_base);
      })
      .catch((err: unknown) => showToast(`${t(locale, "error")}: ${String(err)}`, "error"));
  }, [data, locale]);

  // A shared link opens the sign-in with the code already in it.
  const linkOf = (code: string) => {
    const base = linkBase || `${window.location.origin}${import.meta.env.BASE_URL}`;
    return `${base}${base.includes("?") ? "&" : "?"}invite=${code}`;
  };

  // The code with its link: pasted anywhere, it reads and it opens.
  const copy = async (code: string) => {
    try {
      await navigator.clipboard.writeText(`${t(locale, "inviteShareText")} ${code}\n${linkOf(code)}`);
      showToast(t(locale, "inviteCopied"));
    } catch {
      showToast(code);
    }
  };

  const remove = async (code: string) => {
    try {
      await userApi.deleteInvite(data, code);
      setItems((list) => list?.filter((item) => item.code !== code) ?? list);
      showToast(t(locale, "inviteDeleted"));
    } catch (err) {
      fail(err);
    }
  };

  const create = async () => {
    setBusy(true);
    try {
      const { code } = await userApi.createInvite(data);
      setItems((list) => [
        { code, created_at: new Date().toISOString(), used_at: null, used_by: null },
        ...(list ?? []),
      ]);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };

  const open = (items ?? []).filter((item) => !item.used_by);
  const used = (items ?? []).filter((item) => item.used_by);

  return (
    <>
      <BackHead title={t(locale, "invites")} backLabel={t(locale, "back")} onBack={onBack} />
      <div className="form-stack invites-make">
        <p className="field-note">{t(locale, "invitesHint")}</p>
        <button type="button" className="btn is-wide" disabled={busy} onClick={() => void create()}>
          {t(locale, "inviteCreate")}
        </button>
      </div>

      {items === null ? (
        <SettingsSkel groups={[2]} />
      ) : (
        <>
          {open.length > 0 && (
            <Group title={t(locale, "invitesOpen")}>
              {open.map((item) => (
                <InfoRow
                  key={item.code}
                  label={<span className="invite-code">{item.code}</span>}
                  sub={`${t(locale, "inviteMade")} ${formatWhen(item.created_at, locale)}`}
                >
                  <span className="fr-icons" role="group">
                    <button
                      type="button"
                      onClick={() => void copy(item.code)}
                      aria-label={t(locale, "inviteCopy")}
                      title={t(locale, "inviteCopy")}
                    >
                      <Icon name="copy" size={16} />
                    </button>
                    <button
                      type="button"
                      className="is-danger"
                      onClick={() => void remove(item.code)}
                      aria-label={t(locale, "inviteDelete")}
                      title={t(locale, "inviteDelete")}
                    >
                      <Icon name="trash" size={16} />
                    </button>
                  </span>
                </InfoRow>
              ))}
            </Group>
          )}
          {used.length > 0 && (
            <Group title={t(locale, "invitesUsed")}>
              {used.map((item) => {
                const who = item.used_by as { person_id: number; name: string | null };
                return (
                  <InfoRow
                    key={item.code}
                    lead={<Avatar name={who.name ?? "?"} personId={who.person_id} size={36} />}
                    label={
                      onOpenPerson ? (
                        <button type="button" className="invite-who" onClick={() => onOpenPerson(who.person_id)}>
                          {who.name ?? "—"}
                        </button>
                      ) : (
                        (who.name ?? "—")
                      )
                    }
                    sub={`${t(locale, "inviteJoined")} ${formatWhen(item.used_at, locale)}`}
                  />
                );
              })}
            </Group>
          )}
        </>
      )}
    </>
  );
}
