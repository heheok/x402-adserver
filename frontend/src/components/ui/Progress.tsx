type Props = {
  value: number; // 0..1
  color?: string;
  height?: number;
  /** When true, paints a slow, subtle highlight sweep across the filled
   *  portion — used to signal a live/active campaign. */
  shine?: boolean;
};

export default function Progress({
  value,
  color = "var(--tint-grad-strong)",
  height = 4,
  shine = false,
}: Props) {
  return (
    <div
      style={{
        width: "100%",
        height,
        background: "var(--bg-3)",
        borderRadius: 999,
        overflow: "hidden",
      }}
    >
      <div
        className={shine ? "x-progress-shine" : undefined}
        style={{
          width: `${Math.min(100, Math.max(0, value * 100))}%`,
          height: "100%",
          background: color,
          borderRadius: 999,
          transition: "width 0.3s ease",
        }}
      />
    </div>
  );
}
