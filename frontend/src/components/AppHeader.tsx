import WalletChip from "./WalletChip";
import BrandMark from "./ui/BrandMark";

export default function AppHeader() {
  return (
    <header
      className="x-bar-pad"
      style={{
        height: 64,
        padding: "0 28px",
        display: "flex",
        alignItems: "center",
        borderBottom: "1px solid var(--line-1)",
        background: "var(--bg-0)",
        position: "relative",
        zIndex: 5,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
        <BrandMark size={22} />
        <div
          style={{ display: "flex", flexDirection: "column", lineHeight: 1 }}
        >
          <span
            className="x-display"
            style={{ fontSize: 18, letterSpacing: "-0.02em" }}
          >
            solboards
          </span>
          <span
            className="x-hide-sm"
            style={{
              fontSize: 10,
              color: "var(--tx-2)",
              marginTop: 2,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              fontFamily: "var(--font-mono)",
            }}
          >
            DOOH ad network
          </span>
        </div>
        <span
          className="x-hide-sm"
          style={{
            marginLeft: 14,
            padding: "3px 7px",
            borderRadius: 6,
            fontSize: 10,
            fontFamily: "var(--font-mono)",
            color: "var(--sol-teal)",
            background: "rgba(20,241,149,0.08)",
            border: "1px solid rgba(20,241,149,0.20)",
            textTransform: "uppercase",
            letterSpacing: "0.08em",
          }}
        >
          Solana · devnet
        </span>
      </div>

      <div style={{ flex: 1 }} />

      <WalletChip />
    </header>
  );
}
