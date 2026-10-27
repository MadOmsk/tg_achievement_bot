/** The name as one word: the icon's U (an open shackle), then "nlocked" in
 * the wordmark's font. */
export function Wordmark({ className = "" }: { className?: string }) {
  return (
    <span className={`wordmark ${className}`} role="img" aria-label="Unlocked">
      <svg viewBox="140 112 232 280" className="wordmark-u" aria-hidden="true">
        <path
          d="M180 150 V282 a76 76 0 0 0 152 0 V206"
          stroke="currentColor"
          strokeWidth="58"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
      </svg>
      <span className="wordmark-rest" aria-hidden="true">
        nlocked
      </span>
    </span>
  );
}
