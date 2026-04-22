import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useApi } from "../lib/api";
import CampaignCard, { type CampaignSummary } from "./CampaignCard";
import CreateCampaignForm from "./CreateCampaignForm";

export default function CampaignsPanel() {
  const api = useApi();
  const [showForm, setShowForm] = useState(false);

  const campaigns = useQuery<CampaignSummary[]>({
    queryKey: ["campaigns"],
    queryFn: async () => {
      const r = await api.get<CampaignSummary[]>("/api/campaigns");
      return r.data;
    },
  });

  return (
    <section className="card card-wide">
      <div className="panel-header">
        <h2>Campaigns</h2>
        <button
          onClick={() => setShowForm((v) => !v)}
          className={showForm ? "secondary" : undefined}
        >
          {showForm ? "Close form" : "New campaign"}
        </button>
      </div>

      {showForm && (
        <div className="inline-form">
          <CreateCampaignForm onCreated={() => setShowForm(false)} />
        </div>
      )}

      {campaigns.isLoading && <p className="muted">Loading…</p>}
      {campaigns.isError && (
        <p className="error">
          Failed to load campaigns: {(campaigns.error as Error).message}
        </p>
      )}
      {campaigns.data && campaigns.data.length === 0 && !showForm && (
        <p className="muted">
          No campaigns yet — click "New campaign" to create your first one.
        </p>
      )}
      {campaigns.data?.map((c) => (
        <CampaignCard key={c.id} campaign={c} />
      ))}
    </section>
  );
}
