/** The name as one word: the logo's U (an open shackle) with its sparkle,
 * then "nlocked" in the wordmark's font. */
export function Wordmark({ className = "" }: { className?: string }) {
  return (
    <span className={`wordmark ${className}`} role="img" aria-label="Unlocked">
      <svg viewBox="140 88 296 304" className="wordmark-u" aria-hidden="true">
        <defs>
          <filter id="wordmark-shine" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="9" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <path
          d="M180 150 V282 a76 76 0 0 0 152 0 V206"
          stroke="currentColor"
          strokeWidth="58"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
        <path
          d="M384 92 C395 127 395 127 430 138 C395 149 395 149 384 184 C373 149 373 149 338 138 C373 127 373 127 384 92Z"
          className="wordmark-spark"
          filter="url(#wordmark-shine)"
        />
      </svg>
      <span className="wordmark-rest" aria-hidden="true">
        nlocked
      </span>
    </span>
  );
}
