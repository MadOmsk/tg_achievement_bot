import "./Wordmark.css";

/** The app's name as one word (owner, 2026-10-08): the icon's platinum "U" — an
 * open shackle, its tip glowing — and "nlocked" after it in the heading's own
 * type, in place of a logo above a title. The U is drawn the height of the
 * letters and sits on their baseline. */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={className ? `wordmark ${className}` : "wordmark"} role="img" aria-label="Unlocked">
      <UMark className="wordmark-u" />
      <span className="wordmark-rest" aria-hidden>
        nlocked
      </span>
    </span>
  );
}

/** The icon's U alone, drawn in the app (no tile): the first letter of the
 * wordmark, and the app's mark where a small one is wanted (the install
 * banner). Every copy defines the same gradients under the same ids, so
 * several on one page draw alike. */
export function UMark({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="118 62 340 340" aria-hidden>
      <defs>
        <linearGradient id="wm-platinum" x1="140" y1="90" x2="380" y2="420" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset=".35" stopColor="#cfeaff" />
          <stop offset=".65" stopColor="#d9c9ff" />
          <stop offset="1" stopColor="#ffd9ec" />
        </linearGradient>
        <radialGradient
          id="wm-tip"
          cx="0"
          cy="0"
          r="1"
          gradientUnits="userSpaceOnUse"
          gradientTransform="translate(356 150) scale(70)"
        >
          <stop offset="0" stopColor="#ffffff" stopOpacity=".9" />
          <stop offset=".35" stopColor="#bfe6ff" stopOpacity=".45" />
          <stop offset="1" stopColor="#bfe6ff" stopOpacity="0" />
        </radialGradient>
      </defs>
      <path
        d="M156 112 V268 a100 100 0 0 0 200 0 V150"
        stroke="url(#wm-platinum)"
        strokeWidth="64"
        strokeLinecap="round"
        fill="none"
      />
      <circle cx="356" cy="150" r="70" fill="url(#wm-tip)" />
      <circle cx="356" cy="150" r="14" fill="#ffffff" />
      <path
        d="M410 66 C415.2 86.8 415.2 86.8 436 92 C415.2 97.2 415.2 97.2 410 118 C404.8 97.2 404.8 97.2 384 92 C404.8 86.8 404.8 86.8 410 66Z"
        fill="#ffffff"
      />
      <path
        d="M442 129 C444.2 137.8 444.2 137.8 453 140 C444.2 142.2 444.2 142.2 442 151 C439.8 142.2 439.8 142.2 431 140 C439.8 137.8 439.8 137.8 442 129Z"
        fill="#d9c9ff"
        opacity=".9"
      />
    </svg>
  );
}
