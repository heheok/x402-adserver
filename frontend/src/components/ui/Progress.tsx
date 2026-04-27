type Props = {
  value: number; // 0..1
  color?: string;
  height?: number;
};

export default function Progress({
  value,
  color = "var(--tint-grad-strong)",
  height = 4,
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
