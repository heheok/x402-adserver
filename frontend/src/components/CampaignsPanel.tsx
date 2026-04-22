import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api, useApi } from "../lib/api";
import { humanizeError } from "../lib/errors";
import CampaignCard, { type CampaignSummary } from "./CampaignCard";
import CreateCampaignForm from "./CreateCampaignForm";

type AutoPlayStatus = { enabled: boolean; interval_seconds: number };

export default function CampaignsPanel() {
  const authedApi = useApi();
  const [showForm, setShowForm] = useState(false);

  const autoPlay = useQuery<AutoPlayStatus>({
    queryKey: ["auto-play-status"],
    queryFn: async () => {
      const r = await api.get<AutoPlayStatus>("/api/auto-play-status");
      return r.data;
    },
    staleTime: 60_000,
  });

  const campaigns = useQuery<CampaignSummary[]>({
    queryKey: ["campaigns"],
    queryFn: async () => {
      const r = await authedApi.get<CampaignSummary[]>("/api/campaigns");
      return r.data;
    },
    // When auto-play is on, refetch once per tick so the dashboard reflects
    // server-side settlements without a manual refresh.
    refetchInterval: autoPlay.data?.enabled
      ? autoPlay.data.interval_seconds * 1000
      : false,
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

      {autoPlay.data?.enabled && (
        <p className="auto-play-badge">
          <span className="pulse" aria-hidden>
            ●
          </span>{" "}
          Auto-simulating plays every {autoPlay.data.interval_seconds}s on
          active, funded campaigns (demo mode — in production real publishers
          drive plays).
        </p>
      )}

      {showForm && (
        <div className="inline-form">
          <CreateCampaignForm onCreated={() => setShowForm(false)} />
        </div>
      )}

      {campaigns.isLoading && <p className="muted">Loading…</p>}
      {campaigns.isError && (
        <p className="error">
          Failed to load campaigns: {humanizeError(campaigns.error)}
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
