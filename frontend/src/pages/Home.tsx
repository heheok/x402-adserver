import { usePrivy } from "@privy-io/react-auth";

import CampaignsPanel from "../components/CampaignsPanel";
import WalletPanel from "../components/WalletPanel";

export default function Home() {
  const { user, logout } = usePrivy();

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Advertiser Dashboard</h1>
          <p className="muted footnote">
            Demo — third-party advertiser view on x402 Ad Server
          </p>
        </div>
        <div className="user">
          <span className="muted">{user?.email?.address ?? user?.id}</span>
          <button onClick={logout}>Sign out</button>
        </div>
      </header>

      <main className="content">
        <WalletPanel />
        <CampaignsPanel />
      </main>
    </div>
  );
}
