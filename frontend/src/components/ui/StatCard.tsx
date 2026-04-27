import type { ReactNode } from "react";

import Sparkline from "./Sparkline";

type Props = {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  sparkData?: number[];
  sparkColor?: string;
  accent?: string;
};

export default function StatCard({
  label,
  value,
  sub,
  sparkData,
  sparkColor,
  accent,
}: Props) {
  return (
    <div
      className="x-card"
      style={{ padding: 16, position: "relative", overflow: "hidden" }}
    >
      {accent && (
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: 1,
            background: accent,
          }}
        />
      )}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
        }}
      >
        <div
          style={{
            fontSize: 11,
            color: "var(--tx-2)",
            letterSpacing: "0.06em",
            textTransform: "uppercase",
            fontFamily: "var(--font-mono)",
          }}
        >
          {label}
        </div>
        {sparkData && (
          <Sparkline data={sparkData} color={sparkColor || "var(--sol-teal)"} />
        )}
      </div>
      <div
        className="x-display x-tnum"
        style={{ fontSize: 30, marginTop: 10, lineHeight: 1.05 }}
      >
        {value}
      </div>
      {sub && (
        <div
          style={{
            fontSize: 11,
            color: "var(--tx-2)",
            marginTop: 6,
            fontFamily: "var(--font-mono)",
          }}
        >
          {sub}
        </div>
      )}
    </div>
  );
}
