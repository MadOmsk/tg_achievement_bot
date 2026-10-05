import "./Icon.css";

export function Icon({
  name,
  size = 24,
  filled = false,
}: {
  name:
    | "home"
    | "people"
    | "search"
    | "gear"
    | "g"
    | "feed"
    | "lock"
    | "unlock"
    | "compare"
    | "trash"
    | "stats"
    | "cup"
    | "back"
    | "forward"
    | "link"
    | "sync"
    | "off"
    | "sort"
    | "guide";
  size?: number;
  filled?: boolean;
}) {
  const props = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: filled ? "currentColor" : "none",
    stroke: filled ? "none" : "currentColor",
    strokeWidth: filled ? 0 : 1.75,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  if (name === "home") {
    return (
      <svg {...props}>
        <path d="M4 10.5 12 4l8 6.5V20a1.2 1.2 0 0 1-1.2 1.2h-4.6v-6.2H9.8v6.2H5.2A1.2 1.2 0 0 1 4 20z" />
      </svg>
    );
  }
  if (name === "people") {
    if (filled) {
      return (
        <svg
          width={size}
          height={size}
          viewBox="0 0 24 24"
          fill="currentColor"
          aria-hidden
        >
          <circle cx="9" cy="8" r="3.15" />
          <path d="M3.1 20.2c0-3.4 2.6-5.8 5.9-5.8s5.9 2.4 5.9 5.8V21H3.1z" />
          <circle cx="16.7" cy="9.1" r="2.45" />
          <path d="M13.2 20.2c.5-1.7 1.6-3.1 3.4-3.8 1.8.7 3 2.1 3.5 3.8V21h-6.9z" />
        </svg>
      );
    }
    return (
      <svg {...props}>
        <circle cx="9" cy="8" r="3" />
        <path d="M3.5 19a5.5 5.5 0 0 1 11 0" />
        <circle cx="17" cy="9" r="2.4" />
        <path d="M16 19a4.5 4.5 0 0 1 5-4.4" />
      </svg>
    );
  }
  if (name === "stats") {
    return (
      <svg {...props}>
        <rect x="4" y="11" width="3.2" height="8" rx="1" />
        <rect x="10.4" y="5" width="3.2" height="14" rx="1" />
        <rect x="16.8" y="9" width="3.2" height="10" rx="1" />
      </svg>
    );
  }
  if (name === "search") {
    return (
      <svg {...props}>
        {filled ? (
          <>
            <circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" strokeWidth="2.2" />
            <path
              d="m16.2 16.2 5 5"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              fill="none"
            />
          </>
        ) : (
          <>
            <circle cx="11" cy="11" r="6.5" />
            <path d="m16 16 4 4" />
          </>
        )}
      </svg>
    );
  }
  if (name === "feed") {
    return (
      <svg {...props}>
        <rect x="3.5" y="4.5" width="17" height="5" rx="1.6" />
        <rect x="3.5" y="11.5" width="17" height="5" rx="1.6" />
        <rect x="3.5" y="18.5" width="11" height="2.2" rx="1" />
      </svg>
    );
  }
  if (name === "lock") {
    return (
      <svg {...props}>
        <rect x="5" y="11" width="14" height="10" rx="2" />
        <path d="M8 11V8a4 4 0 0 1 8 0v3" />
      </svg>
    );
  }
  if (name === "unlock") {
    return (
      <svg {...props}>
        <rect x="5" y="11" width="14" height="10" rx="2" />
        <path d="M8 11V8a4 4 0 0 1 7.6-1.7" />
      </svg>
    );
  }
  if (name === "trash") {
    return (
      <svg {...props}>
        <path d="M4.5 7h15" />
        <path d="M9.5 7V4.8h5V7" />
        <path d="M6.6 7l.9 12.2h9l.9-12.2" />
        <path d="M10.2 10.6v5.6M13.8 10.6v5.6" />
      </svg>
    );
  }
  if (name === "compare") {
    return (
      <svg {...props}>
        <circle cx="9" cy="12" r="5.6" />
        <circle cx="15" cy="12" r="5.6" />
      </svg>
    );
  }
  if (name === "gear") {
    if (filled) {
      // One shape with the middle cut out: two filled paths would cover the hole.
      return (
        <svg {...props} fillRule="evenodd">
          <path d="M12 8.4a3.6 3.6 0 1 0 0 7.2 3.6 3.6 0 0 0 0-7.2zM19.2 13.1c.05-.36.08-.73.08-1.1s-.03-.74-.08-1.1l2.05-1.6-1.95-3.38-2.42.78a7.7 7.7 0 0 0-1.9-1.1L14.6 3.5h-5.2l-.38 2.1a7.7 7.7 0 0 0-1.9 1.1l-2.42-.78-1.95 3.38 2.05 1.6a7.4 7.4 0 0 0 0 2.2l-2.05 1.6 1.95 3.38 2.42-.78c.57.45 1.2.82 1.9 1.1l.38 2.1h5.2l.38-2.1c.7-.28 1.33-.65 1.9-1.1l2.42.78 1.95-3.38z" />
        </svg>
      );
    }
    return (
      <svg {...props}>
        <path d="M12 8.4a3.6 3.6 0 1 0 0 7.2 3.6 3.6 0 0 0 0-7.2z" />
        <path d="M19.2 13.1c.05-.36.08-.73.08-1.1s-.03-.74-.08-1.1l2.05-1.6-1.95-3.38-2.42.78a7.7 7.7 0 0 0-1.9-1.1L14.6 3.5h-5.2l-.38 2.1a7.7 7.7 0 0 0-1.9 1.1l-2.42-.78-1.95 3.38 2.05 1.6a7.4 7.4 0 0 0 0 2.2l-2.05 1.6 1.95 3.38 2.42-.78c.57.45 1.2.82 1.9 1.1l.38 2.1h5.2l.38-2.1c.7-.28 1.33-.65 1.9-1.1l2.42.78 1.95-3.38z" />
      </svg>
    );
  }
  if (name === "back") {
    return (
      <svg {...props} strokeWidth={filled ? 0 : 2.35}>
        <path d="M14.2 5.2 7.2 12l7 6.8" />
        <path d="M8.1 12h9.7" />
      </svg>
    );
  }
  if (name === "forward") {
    return (
      <svg {...props} strokeWidth={filled ? 0 : 2.35}>
        <path d="M9.8 5.2 16.8 12l-7 6.8" />
        <path d="M6.2 12h9.7" />
      </svg>
    );
  }
  if (name === "cup") {
    // A plain cup: bowl, two handles, stem and foot. Drawn on the logo's grid and
    // cropped to the cup, in the current colour.
    return (
      <svg
        width={size}
        height={size}
        viewBox="112 112 288 288"
        fill="currentColor"
        stroke="currentColor"
        aria-hidden
      >
        <path d="M168 142h176v66a88 88 0 0 1-176 0z" stroke="none" />
        <path
          d="M168 176h-22c-30 0-30 62 0 62h26M344 176h22c30 0 30 62 0 62h-26"
          fill="none"
          strokeWidth="20"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <rect x="243" y="292" width="26" height="46" stroke="none" />
        <rect x="196" y="334" width="120" height="26" rx="13" stroke="none" />
      </svg>
    );
  }
  if (name === "link") {
    return (
      <svg {...props}>
        <path d="M10 14a4.5 4.5 0 0 0 6.36.2l2.2-2.2a4.5 4.5 0 0 0-6.36-6.36l-1.1 1.1" />
        <path d="M14 10a4.5 4.5 0 0 0-6.36-.2l-2.2 2.2a4.5 4.5 0 0 0 6.36 6.36l1.1-1.1" />
      </svg>
    );
  }
  if (name === "sync") {
    return (
      <svg {...props}>
        <path d="M20 12a8 8 0 0 1-13.5 5.8" />
        <path d="M4 12a8 8 0 0 1 13.5-5.8" />
        <path d="M16.5 3.5V6.8H20" />
        <path d="M7.5 20.5V17.2H4" />
      </svg>
    );
  }
  if (name === "sort") {
    return (
      <svg {...props}>
        <path d="M7 5v13.5M7 18.5 3.8 15.3M7 18.5l3.2-3.2" />
        <path d="M17 19V5.5M17 5.5l3.2 3.2M17 5.5l-3.2 3.2" />
      </svg>
    );
  }
  if (name === "guide") {
    return (
      <svg {...props}>
        <path d="M12 6.6C10.3 5.3 8 4.8 4.5 4.9v12.5c3.5-.1 5.8.4 7.5 1.7" />
        <path d="M12 6.6c1.7-1.3 4-1.8 7.5-1.7v12.5c-3.5-.1-5.8.4-7.5 1.7" />
        <path d="M12 6.6v12.5" />
      </svg>
    );
  }
  if (name === "off") {
    return (
      <svg {...props}>
        <path d="M12 3.5v8" />
        <path d="M7.2 6.4a7 7 0 1 0 9.6 0" />
      </svg>
    );
  }
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden>
      <circle cx="12" cy="12" r="10" fill="#3ee0a0" />
      <text
        x="12"
        y="16.2"
        textAnchor="middle"
        fontSize="13"
        fontWeight="700"
        fill="#0a0c12"
        fontFamily="inherit"
      >
        G
      </text>
    </svg>
  );
}
