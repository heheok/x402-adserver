type Props = {
  value: number; // 0..1
  color?: string;
  height?: number;
  /** When true, paints a slow, subtle highlight sweep across the filled
   *  portion — used to signal a live/active campaign. */
  shine?: boolean;
  /** When true, ignores `value` and renders a slim segment sliding back and
   *  forth across the full track — for "we're working on something whose
   *  duration we don't know" states (server-side validation, etc.). */
  indeterminate?: boolean;
};

export default function Progress({
  value,
  color = "var(--tint-grad-strong)",
  height = 4,
  shine = false,
  indeterminate = false,
}: Props) {
  return (
    <div
      style={{
        width: "100%",
        height,
        background: "var(--bg-3)",
        borderRadius: 999,
        overflow: "hidden",
        position: "relative",
      }}
    >
      {indeterminate ? (
        <div
          className="x-progress-indeterminate"
          style={{
            position: "absolute",
            top: 0,
            height: "100%",
            background: color,
            borderRadius: 999,
          }}
        />
      ) : (
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
      )}
    </div>
  );
}
