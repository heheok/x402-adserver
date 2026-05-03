import React from "react";
import ReactDOM from "react-dom/client";
import { PrivyProvider } from "@privy-io/react-auth";
import { toSolanaWalletConnectors } from "@privy-io/react-auth/solana";
import { QueryClientProvider } from "@tanstack/react-query";

import App from "./App";
import { queryClient } from "./lib/queryClient";
import { solanaRpcUrl } from "./lib/rpc";
import "./styles/tokens.css";
import "./styles.css";

const privyAppId = import.meta.env.VITE_PRIVY_APP_ID;
if (!privyAppId) {
  throw new Error("VITE_PRIVY_APP_ID missing — see frontend/.env.example");
}

// BrandMark as a data-URI so Privy's modal header shows our logo without
// needing a hosted asset. Inline gradient stops match --sol-purple/--sol-teal.
const BRAND_LOGO_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none"><defs><linearGradient id="g" x1="0" y1="0" x2="24" y2="24" gradientUnits="userSpaceOnUse"><stop offset="0%" stop-color="#9945FF"/><stop offset="100%" stop-color="#14F195"/></linearGradient></defs><rect x="1.5" y="1.5" width="21" height="21" rx="6.5" stroke="url(#g)" stroke-width="1.5"/><path d="M7.5 7.5 L16.5 16.5 M16.5 7.5 L7.5 16.5" stroke="url(#g)" stroke-width="1.6" stroke-linecap="round"/><circle cx="12" cy="12" r="2" fill="url(#g)"/></svg>`;
const BRAND_LOGO_URI = `data:image/svg+xml;utf8,${encodeURIComponent(BRAND_LOGO_SVG)}`;

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <PrivyProvider
      appId={privyAppId}
      config={{
        loginMethods: ["email"],
        // Nested under `solana` — the top-level `createOnLogin` only creates
        // EVM wallets. We're Solana-only, so we skip the ethereum branch.
        embeddedWallets: {
          solana: {
            createOnLogin: "users-without-wallets",
          },
        },
        externalWallets: {
          solana: { connectors: toSolanaWalletConnectors() },
        },
        appearance: {
          walletChainType: "solana-only",
          theme: "#0E1118",           // --bg-1, matches our dark surface
          accentColor: "#3D5AFE",     // --x402-blue, primary CTA
          logo: BRAND_LOGO_URI,
          landingHeader: "Sign in to Solboards",
          loginMessage: "On-chain DOOH ad campaigns on Solana",
        },
        solanaClusters: [
          { name: "devnet", rpcUrl: solanaRpcUrl() },
        ],
      }}
    >
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </PrivyProvider>
  </React.StrictMode>,
);
