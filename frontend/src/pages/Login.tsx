import { usePrivy } from "@privy-io/react-auth";

import Icon from "../components/ui/Icon";
import X402Mark from "../components/ui/X402Mark";

export default function Login() {
  const { login } = usePrivy();

  return (
    <main
      className="x-app"
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
        position: "relative",
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "var(--tint-grad)",
          pointerEvents: "none",
        }}
      />
      <div
        className="x-card"
        style={{
          position: "relative",
          width: "100%",
          maxWidth: 420,
          padding: 28,
          boxShadow: "var(--shadow-card)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            marginBottom: 18,
          }}
        >
          <X402Mark size={28} />
          <div>
            <div className="x-display" style={{ fontSize: 18 }}>
              x402 Advertiser Dashboard
            </div>
            <div
              style={{
                fontSize: 11,
                color: "var(--tx-2)",
                marginTop: 2,
                fontFamily: "var(--font-mono)",
                letterSpacing: "0.06em",
                textTransform: "uppercase",
              }}
            >
              Solana · devnet
            </div>
          </div>
        </div>

        <div
          style={{
            fontSize: 13,
            color: "var(--tx-1)",
            lineHeight: 1.55,
          }}
        >
          Run on-chain DOOH ad campaigns. Upload a creative, pick markets,
          fund in USDC. Publishers settle every play on Solana.
        </div>

        <button
          onClick={login}
          className="x-btn x-btn-primary x-btn-lg"
          style={{ width: "100%", marginTop: 22 }}
        >
          <Icon name="arrowRight" size={13} stroke={2} /> Sign in with email
        </button>

        <div
          style={{
            marginTop: 14,
            fontSize: 11,
            color: "var(--tx-2)",
            fontFamily: "var(--font-mono)",
            textAlign: "center",
          }}
        >
          demo · third-party advertiser view on x402 ad server
        </div>
      </div>
    </main>
  );
}
