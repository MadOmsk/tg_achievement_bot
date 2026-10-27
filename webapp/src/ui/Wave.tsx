/** Progress as a running wave up to the mark, a flat track after it, and a
 * dot at its end. A full list is all wave. `loading` keeps the wave moving. */
export function Wave({
  value,
  total,
  className = "",
  loading = false,
}: {
  value: number;
  total: number | null | undefined;
  className?: string;
  loading?: boolean;
}) {
  const share = total ? Math.max(0, Math.min(1, value / total)) : 0;
  const full = share >= 1;
  return (
    <span
      className={`wave${loading ? " wave-loading" : ""}${full ? " wave-full" : ""} ${className}`}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={total ?? undefined}
      aria-valuenow={value}
    >
      <span className="wave-on" style={{ width: `${(full ? 1 : share) * 100}%` }} />
      {!full && <span className="wave-off" />}
      {!full && <span className="wave-end" />}
    </span>
  );
}
