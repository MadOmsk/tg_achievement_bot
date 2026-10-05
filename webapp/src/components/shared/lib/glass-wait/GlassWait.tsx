import "./GlassWait.css";

export function GlassWait({ tall = false }: { tall?: boolean }) {
  return (
    <div className={tall ? "glass-wait is-tall" : "glass-wait"} aria-hidden>
      <span className="glass-orb" />
      <span className="glass-orb" />
      <span className="glass-orb" />
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="spinner-wrap" role="status" aria-live="polite">
      <span className="spinner" />
      {label && <p className="muted">{label}</p>}
    </div>
  );
}
