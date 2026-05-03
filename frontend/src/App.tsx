import { useEffect, useState } from "react";
import { usePrivy } from "@privy-io/react-auth";
import { useQueryClient } from "@tanstack/react-query";

import AppHeader from "./components/AppHeader";
import CampaignWizard from "./components/CampaignWizard";
import TabRow, { type TabId } from "./components/TabRow";
import Login from "./pages/Login";
import Overview from "./pages/Overview";
import Campaigns from "./pages/Campaigns";
import { cmpMicro } from "./lib/money";

type WalletCacheShape = { usdc_balance: string };

export default function App() {
  const { ready, authenticated } = usePrivy();
  const qc = useQueryClient();
  const [tab, setTab] = useState<TabId>("overview");
  const [wizardOpen, setWizardOpen] = useState(false);
  // After "Done" on the wizard's success state, we ping the Campaigns tab
  // with the new campaign's ID so it auto-expands the matching card.
  const [highlightId, setHighlightId] = useState<string | null>(null);
  // Toast for the "fund first" guard below. State-driven so it picks up the
  // app's color scheme instead of the OS-native alert(). Auto-dismisses
  // after 4s; clicking the toast also clears it.
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), 4000);
    return () => window.clearTimeout(t);
  }, [toast]);

  function handleNewCampaign() {
    // Fail-open if the wallet query hasn't loaded yet — StepCalculator's
    // own insufficient-funds guard will catch any edge case downstream.
    const data = qc.getQueryData<WalletCacheShape>(["wallet"]);
    if (data && cmpMicro(data.usdc_balance, "0") <= 0) {
      setToast("Get test USDC from your wallet first to fund a campaign.");
      return;
    }
    setWizardOpen(true);
  }

  if (!ready) {
    return (
      <main
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--tx-2)",
          fontFamily: "var(--font-mono)",
          fontSize: 12,
          background: "var(--bg-0)",
        }}
      >
        loading…
      </main>
    );
  }

  if (!authenticated) return <Login />;

  return (
    <div className="x-app" style={{ minHeight: "100vh" }}>
      <AppHeader />
      <TabRow
        tab={tab}
        onTabChange={setTab}
        onNewCampaign={handleNewCampaign}
      />
      <main>
        {tab === "overview" ? (
          <Overview
            onNewCampaign={handleNewCampaign}
            onJumpToCampaigns={() => setTab("campaigns")}
          />
        ) : (
          <Campaigns
            onNewCampaign={handleNewCampaign}
            highlightId={highlightId}
          />
        )}
      </main>
      {toast && (
        <div
          onClick={() => setToast(null)}
          style={{
            position: "fixed",
            top: 16,
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 1000,
            padding: "10px 16px",
            borderRadius: 10,
            border: "1px solid var(--line-2)",
            background: "var(--bg-2)",
            color: "var(--tx-0)",
            fontSize: 13,
            fontWeight: 500,
            boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
            cursor: "pointer",
            maxWidth: "90vw",
          }}
        >
          {toast}
        </div>
      )}
      {wizardOpen && (
        <CampaignWizard
          onClose={() => setWizardOpen(false)}
          onDone={(campaign) => {
            setHighlightId(campaign.id);
            setTab("campaigns");
            setWizardOpen(false);
          }}
        />
      )}
    </div>
  );
}
