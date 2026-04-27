import React from "react";
import ReactDOM from "react-dom/client";
import { PrivyProvider } from "@privy-io/react-auth";
import { toSolanaWalletConnectors } from "@privy-io/react-auth/solana";
import { QueryClientProvider } from "@tanstack/react-query";

import App from "./App";
import { queryClient } from "./lib/queryClient";
import "./styles/tokens.css";
import "./styles.css";

const privyAppId = import.meta.env.VITE_PRIVY_APP_ID;
if (!privyAppId) {
  throw new Error("VITE_PRIVY_APP_ID missing — see frontend/.env.example");
}

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
        },
        solanaClusters: [
          { name: "devnet", rpcUrl: "https://api.devnet.solana.com" },
        ],
      }}
    >
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </PrivyProvider>
  </React.StrictMode>,
);
