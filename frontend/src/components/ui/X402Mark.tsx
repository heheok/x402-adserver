type Props = { size?: number };

export default function X402Mark({ size = 22 }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <defs>
        <linearGradient
          id="x402-grad"
          x1="0"
          y1="0"
          x2="24"
          y2="24"
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0%" stopColor="#9945FF" />
          <stop offset="100%" stopColor="#14F195" />
        </linearGradient>
      </defs>
      <rect
        x="1.5"
        y="1.5"
        width="21"
        height="21"
        rx="6.5"
        stroke="url(#x402-grad)"
        strokeWidth="1.5"
      />
      <path
        d="M7.5 7.5 L16.5 16.5 M16.5 7.5 L7.5 16.5"
        stroke="url(#x402-grad)"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      <circle cx="12" cy="12" r="2" fill="url(#x402-grad)" />
    </svg>
  );
}
