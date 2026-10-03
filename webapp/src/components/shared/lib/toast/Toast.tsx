import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import "./Toast.css";

export type ToastKind = "info" | "success" | "error";

type Toast = { text: string; kind: ToastKind; seq: number };

const SHOW_MS = 3200;
const LEAVE_MS = 220;
const listeners = new Set<(text: string, kind: ToastKind) => void>();

/** Show a short notice over the top of the screen, from anywhere in the app. It
 * floats above the content, never moves it, and goes away by itself or on a tap. */
export function showToast(text: string, kind: ToastKind = "info"): void {
  listeners.forEach((listen) => listen(text, kind));
}

/** Mounted once, in the app shell. One notice at a time: a new one takes the
 * place of the one showing — its text changes, the timer starts over — rather
 * than stacking or sliding in again. */
export function Toaster() {
  const [toast, setToast] = useState<Toast | null>(null);
  const [leaving, setLeaving] = useState(false);
  const hide = useRef<number | undefined>(undefined);
  const drop = useRef<number | undefined>(undefined);

  useEffect(() => {
    const show = (text: string, kind: ToastKind) => {
      window.clearTimeout(hide.current);
      window.clearTimeout(drop.current);
      setLeaving(false);
      setToast((current) => ({ text, kind, seq: (current?.seq ?? 0) + 1 }));
      hide.current = window.setTimeout(() => {
        setLeaving(true);
        drop.current = window.setTimeout(() => setToast(null), LEAVE_MS);
      }, SHOW_MS);
    };
    listeners.add(show);
    return () => {
      listeners.delete(show);
      window.clearTimeout(hide.current);
      window.clearTimeout(drop.current);
    };
  }, []);

  const dismiss = () => {
    window.clearTimeout(hide.current);
    setLeaving(true);
    drop.current = window.setTimeout(() => setToast(null), LEAVE_MS);
  };

  return createPortal(
    <div className="toasts" aria-live="polite">
      {toast && (
        <button
          type="button"
          className={`toast is-${toast.kind}${leaving ? " is-leaving" : ""}`}
          onClick={dismiss}
        >
          {/* Keyed by the notice, so only the text fades when it is replaced. */}
          <span key={toast.seq} className="toast-text">
            {toast.text}
          </span>
        </button>
      )}
    </div>,
    document.body,
  );
}
