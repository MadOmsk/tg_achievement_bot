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
    | "off";
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
        <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
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
            <circle cx="11" cy="11" r="7" />
            <path d="m16.2 16.2 5 5" stroke="currentColor" strokeWidth="2.2" fill="none" />
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
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 32 32"
        fill="currentColor"
        aria-hidden
      >
        <path d="M31.734,2.429c-1.438-1.196-3.664-1.953-6.543,0.354c-0.006-0.35-0.01-0.695-0.022-1.059c-1.79,0-16.547,0-18.337,0 C6.818,2.088,6.814,2.434,6.81,2.782C3.93,0.477,1.705,1.231,0.268,2.43L0,2.653l0.017,0.346c0.015,0.333,0.432,8.199,4.749,11.769 c1.508,1.247,3.305,1.824,5.343,1.701c-0.139,0.438-0.414,1.042-0.731,1.574l1.197,0.718c0.227-0.379,0.602-1.066,0.828-1.769 c1.59,1.29,2.982,1.677,2.982,2.631c0,2.148-5.313,3.546-5.504,4.891H8.143v0.567H7.355v5.632h17.116v-5.632h-0.691v-0.567H23.12 c-0.188-1.345-5.505-2.741-5.505-4.891c0-0.955,1.393-1.342,2.984-2.631c0.227,0.701,0.601,1.389,0.825,1.768l1.199-0.719 c-0.317-0.53-0.595-1.135-0.731-1.572c2.039,0.122,3.834-0.454,5.342-1.701c4.317-3.57,4.733-11.437,4.75-11.77L32,2.65 L31.734,2.429z M5.659,13.694C2.301,10.919,1.57,4.828,1.438,3.291c1.586-1.121,3.353-0.673,5.378,1.364 C6.824,4.919,6.84,5.169,6.854,5.422c-0.49,0.47-1.151,1.085-1.756,1.633l0.938,1.036c0.36-0.326,0.676-0.613,0.952-0.868 c0.409,3.825,1.438,6.242,2.604,7.855C8.095,15.075,6.773,14.615,5.659,13.694z M21.936,29.541H10.219v-2.863h11.716V29.541z M26.342,13.694c-1.113,0.921-2.436,1.38-3.932,1.384c1.165-1.614,2.195-4.03,2.604-7.854c0.277,0.254,0.592,0.541,0.953,0.867 l0.938-1.035c-0.605-0.548-1.268-1.162-1.756-1.635c0.014-0.252,0.027-0.501,0.035-0.766c2.025-2.037,3.793-2.485,5.379-1.365 C30.43,4.827,29.701,10.918,26.342,13.694z" />
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
