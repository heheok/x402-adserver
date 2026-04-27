import type { JSX } from "react";

export type IconName =
  | "chevron"
  | "chevronUp"
  | "chevronLeft"
  | "copy"
  | "external"
  | "plus"
  | "check"
  | "close"
  | "pause"
  | "play"
  | "upload"
  | "calendar"
  | "map"
  | "wallet"
  | "activity"
  | "refund"
  | "sparkle"
  | "info"
  | "arrowRight"
  | "drag"
  | "file"
  | "image";

const PATHS: Record<IconName, JSX.Element> = {
  chevron: <path d="M3 6l5 5 5-5" />,
  chevronUp: <path d="M3 10l5-5 5 5" />,
  chevronLeft: <path d="M10 3l-5 5 5 5" />,
  copy: (
    <>
      <rect x="5" y="5" width="9" height="9" rx="1.5" />
      <path d="M3 11V3.5A1.5 1.5 0 0 1 4.5 2H10" />
    </>
  ),
  external: (
    <>
      <path d="M9 3h4v4" />
      <path d="M13 3l-7 7" />
      <path d="M11 8.5V13H3V5h4.5" />
    </>
  ),
  plus: (
    <>
      <path d="M8 3v10" />
      <path d="M3 8h10" />
    </>
  ),
  check: <path d="M3 8.5L6.5 12 13 4.5" />,
  close: (
    <>
      <path d="M4 4l8 8" />
      <path d="M12 4l-8 8" />
    </>
  ),
  pause: (
    <>
      <rect x="5" y="3" width="2.2" height="10" rx="0.6" />
      <rect x="9" y="3" width="2.2" height="10" rx="0.6" />
    </>
  ),
  play: <path d="M5 3.5v9l8-4.5z" />,
  upload: (
    <>
      <path d="M8 12V3.5" />
      <path d="M4 7l4-4 4 4" />
      <path d="M2.5 13h11" />
    </>
  ),
  calendar: (
    <>
      <rect x="2.5" y="3.5" width="11" height="10" rx="1.5" />
      <path d="M5 2v3M11 2v3M2.5 7h11" />
    </>
  ),
  map: (
    <>
      <path d="M2 4l4-1.5L10 4l4-1.5V12l-4 1.5L6 12 2 13.5z" />
      <path d="M6 2.5V12M10 4v9.5" />
    </>
  ),
  wallet: (
    <>
      <rect x="2" y="4" width="12" height="9" rx="1.5" />
      <path d="M11 8.5h2" />
      <path d="M2 6.5h10" />
    </>
  ),
  activity: <path d="M1.5 8h3l2-5 3 10 2-5h3" />,
  refund: (
    <>
      <path d="M3 8a5 5 0 1 0 1.5-3.5" />
      <path d="M3 3v3.5h3.5" />
    </>
  ),
  sparkle: <path d="M8 2v4M8 10v4M2 8h4M10 8h4" />,
  info: (
    <>
      <circle cx="8" cy="8" r="6" />
      <path d="M8 11V7M8 5v.01" />
    </>
  ),
  arrowRight: <path d="M3 8h10M9 4l4 4-4 4" />,
  drag: (
    <>
      <circle cx="6" cy="4" r="0.9" />
      <circle cx="10" cy="4" r="0.9" />
      <circle cx="6" cy="8" r="0.9" />
      <circle cx="10" cy="8" r="0.9" />
      <circle cx="6" cy="12" r="0.9" />
      <circle cx="10" cy="12" r="0.9" />
    </>
  ),
  file: (
    <>
      <path d="M4 2h5l3 3v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z" />
      <path d="M9 2v3h3" />
    </>
  ),
  image: (
    <>
      <rect x="2" y="3" width="12" height="10" rx="1.5" />
      <circle cx="6" cy="7" r="1.2" />
      <path d="M3 11l3-3 3 3 2-2 3 3" />
    </>
  ),
};

type Props = {
  name: IconName;
  size?: number;
  stroke?: number;
};

export default function Icon({ name, size = 16, stroke = 1.6 }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={stroke}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {PATHS[name]}
    </svg>
  );
}
