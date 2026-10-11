import { useCallback, useEffect, useState } from "react";
import { fetchAdminActions, postAdminAction, type AdminAction, type AdminActionDone } from "../../../api";
import { Group, NavRow } from "../../shared/lib";

/** A card's super-admin actions, as the server's registry lists them (#176;
 * the bot's card draws the same ones). A tap is taken a step at a time: the
 * server answers each confirmation to ask — the same words and steps as the
 * bot's — or what the action did. A new action needs no change here. */
export function AdminActions({
  data,
  scope,
  target,
  reloadKey,
  onFlash,
  onFail,
  onDone,
}: {
  data: string;
  scope: "user" | "chat" | "global";
  target: string;
  /** Changes when the card reloads, so the list follows (a restored person
   * reads "Исключить" again). */
  reloadKey?: unknown;
  onFlash: (message: string) => void;
  onFail: (err: unknown) => void;
  onDone: (done: AdminActionDone) => void;
}) {
  const [actions, setActions] = useState<AdminAction[] | null>(null);

  const load = useCallback(() => {
    void fetchAdminActions(data, scope, target)
      .then((r) => setActions(r.actions))
      .catch(onFail);
  }, [data, onFail, scope, target]);

  useEffect(load, [load, reloadKey]);

  const run = async (action: AdminAction) => {
    let step = 0;
    for (;;) {
      const res = await postAdminAction(data, {
        scope: action.scope,
        target: action.target,
        action: action.id,
        step,
      });
      if (res.confirm) {
        if (!window.confirm(res.confirm.text)) return;
        step = res.confirm.step;
        continue;
      }
      if (res.done) {
        if (res.done.text) onFlash(res.done.text);
        onDone(res.done);
        if (!res.done.gone) load();
      }
      return;
    }
  };

  if (actions == null || actions.length === 0) return null;

  // One group per section, in the order the server lists them.
  const sections: Array<{ title: string | null; items: AdminAction[] }> = [];
  for (const action of actions) {
    const last = sections[sections.length - 1];
    if (last && last.title === action.section_title) last.items.push(action);
    else sections.push({ title: action.section_title, items: [action] });
  }

  return (
    <>
      {sections.map((section, i) => (
        <Group key={`${section.title ?? ""}-${i}`} title={section.title ?? undefined}>
          {section.items.map((action) => (
            <NavRow
              key={`${action.target}:${action.id}`}
              danger={action.danger}
              label={action.label}
              onClick={() => void run(action).catch(onFail)}
            />
          ))}
        </Group>
      ))}
    </>
  );
}
