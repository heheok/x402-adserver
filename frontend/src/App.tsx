import { useState } from "react";
import { usePrivy } from "@privy-io/react-auth";

import AppHeader from "./components/AppHeader";
import CampaignWizard from "./components/CampaignWizard";
import TabRow, { type TabId } from "./components/TabRow";
import Login from "./pages/Login";
import Overview from "./pages/Overview";
import Campaigns from "./pages/Campaigns";

export default function App() {
  const { ready, authenticated } = usePrivy();
  const [tab, setTab] = useState<TabId>("overview");
  const [wizardOpen, setWizardOpen] = useState(false);
  // After "Done" on the wizard's success state, we ping the Campaigns tab
  // with the new campaign's ID so it auto-expands the matching card.
  const [highlightId, setHighlightId] = useState<string | null>(null);

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
        onNewCampaign={() => setWizardOpen(true)}
      />
      <main>
        {tab === "overview" ? (
          <Overview
            onNewCampaign={() => setWizardOpen(true)}
            onJumpToCampaigns={() => setTab("campaigns")}
          />
        ) : (
          <Campaigns
            onNewCampaign={() => setWizardOpen(true)}
            highlightId={highlightId}
          />
        )}
      </main>
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
