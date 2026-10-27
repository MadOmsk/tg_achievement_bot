import { useState } from "react";
import { userApi, type InviteItem } from "../../api";
import { useApp } from "../../app/context";
import { useLoad } from "../../app/useLoad";
import { formatWhen } from "../../i18n";
import { Button, Group, Row } from "../../ui/Controls";
import { Face } from "../../ui/Face";
import { Icon } from "../../ui/Icon";
import { Confirm } from "../../ui/Page";

function linkOf(base: string | null, code: string): string {
  const root = base ?? `${window.location.origin}${import.meta.env.BASE_URL}`;
  return `${root}${root.includes("?") ? "&" : "?"}invite=${encodeURIComponent(code)}`;
}

export function InvitesPane() {
  const { data, tr, locale, toast, open } = useApp();
  const invites = useLoad("invites", () => userApi.invites(data));
  const [busy, setBusy] = useState(false);
  const [drop, setDrop] = useState<string | null>(null);
  const items = invites.data?.items ?? [];
  const unused = items.filter((i) => !i.used_at);
  const used = items.filter((i) => i.used_at);

  const copy = async (item: InviteItem) => {
    const text = `${tr("inviteShareText")} ${item.code}\n${linkOf(invites.data?.link_base ?? null, item.code)}`;
    try {
      await navigator.clipboard.writeText(text);
      toast(tr("inviteCopied"));
    } catch {
      toast(item.code);
    }
  };

  return (
    <>
      <p className="set-intro">{tr("invitesHint")}</p>
      <div className="set-pad">
        <Button
          wide
          icon="plus"
          busy={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await userApi.createInvite(data);
              invites.reload();
            } catch {
              toast(tr("somethingWrong"), "error");
            } finally {
              setBusy(false);
            }
          }}
        >
          {tr("inviteCreate")}
        </Button>
      </div>
      {unused.length > 0 && (
        <Group title={tr("invitesOpen")}>
          {unused.map((i) => (
            <Row
              key={i.code}
              lead={<Icon name="gift" />}
              title={<span className="invite-code">{i.code}</span>}
              sub={`${tr("inviteMade")} ${formatWhen(i.created_at, locale)}`}
              trail={
                <>
                  <button type="button" className="link-btn" aria-label={tr("inviteCopy")} onClick={() => void copy(i)}>
                    <Icon name="copy" size={18} />
                  </button>
                  <button type="button" className="link-btn" aria-label={tr("inviteDelete")} onClick={() => setDrop(i.code)}>
                    <Icon name="trash" size={18} />
                  </button>
                </>
              }
            />
          ))}
        </Group>
      )}
      {used.length > 0 && (
        <Group title={tr("invitesUsed")}>
          {used.map((i) =>
            i.used_by ? (
              <Row
                key={i.code}
                lead={<Face personId={i.used_by.person_id} name={i.used_by.name ?? "?"} size={40} />}
                title={i.used_by.name ?? i.code}
                sub={`${tr("inviteJoined")} ${formatWhen(i.used_at, locale)}`}
                chevron
                onClick={() => open({ kind: "person", personId: i.used_by!.person_id })}
              />
            ) : (
              <Row key={i.code} title={i.code} sub={formatWhen(i.used_at, locale)} />
            ),
          )}
        </Group>
      )}
      {drop && (
        <Confirm
          text={`${tr("inviteDelete")}?\n${drop}`}
          yes={tr("inviteDelete")}
          no={tr("cancel")}
          danger
          onYes={async () => {
            const code = drop;
            setDrop(null);
            try {
              await userApi.deleteInvite(data, code);
              invites.reload();
              toast(tr("inviteDeleted"));
            } catch {
              toast(tr("somethingWrong"), "error");
            }
          }}
          onNo={() => setDrop(null)}
        />
      )}
    </>
  );
}
