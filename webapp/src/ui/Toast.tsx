import { useEffect, useState } from "react";

type Item = { id: number; text: string; kind: "info" | "error" };

let push: ((text: string, kind: "info" | "error") => void) | null = null;

export function showToast(text: string, kind: "info" | "error" = "info"): void {
  push?.(text, kind);
}

/** One message at a time, above the toolbar, gone after a few seconds. */
export function Toaster() {
  const [item, setItem] = useState<Item | null>(null);
  useEffect(() => {
    push = (text, kind) => setItem({ id: Date.now(), text, kind });
    return () => {
      push = null;
    };
  }, []);
  useEffect(() => {
    if (!item) return;
    const id = window.setTimeout(() => setItem(null), item.kind === "error" ? 5000 : 2800);
    return () => window.clearTimeout(id);
  }, [item]);
  if (!item) return null;
  return (
    <div key={item.id} className={`toast toast-${item.kind}`} role="status" onClick={() => setItem(null)}>
      {item.text}
    </div>
  );
}
