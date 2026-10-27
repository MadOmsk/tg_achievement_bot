import type { ReactNode } from "react";

const WAVES = 16;
const STEPS = 360;

/** The wave's circular form: a waved arc up to the mark over a flat track,
 * with whatever sits inside it (a cover, a number) in the middle. */
export function WaveRing({
  value,
  total,
  size = 168,
  waves = WAVES,
  amp = 2.5,
  children,
}: {
  value: number;
  total: number | null | undefined;
  size?: number;
  /** A small ring takes fewer, lower waves, or it reads as a flower. */
  waves?: number;
  amp?: number;
  children?: ReactNode;
}) {
  const share = total ? Math.max(0, Math.min(1, value / total)) : 0;
  const c = size / 2;
  const r = c - 8;
  const points: string[] = [];
  const steps = Math.max(2, Math.round(STEPS * share));
  for (let i = 0; i <= steps; i++) {
    const t = (i / STEPS) * Math.PI * 2;
    const rr = r + amp * Math.sin(t * waves);
    const x = c + rr * Math.sin(t);
    const y = c - rr * Math.cos(t);
    points.push(`${i ? "L" : "M"}${x.toFixed(2)} ${y.toFixed(2)}`);
  }
  return (
    <span
      className={`ring${share >= 1 ? " ring-full" : ""}`}
      style={{ width: size, height: size }}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={total ?? undefined}
      aria-valuenow={value}
    >
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} aria-hidden="true">
        {share < 1 && <circle className="ring-off" cx={c} cy={c} r={r} />}
        {share > 0 && <path className="ring-on" d={points.join(" ")} />}
      </svg>
      <span className="ring-in">{children}</span>
    </span>
  );
}
