import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api, useApi } from "../lib/api";
import type { CampaignRow } from "../lib/aggregations";
import { humanizeError } from "../lib/errors";
import { formatUsdc, sumMicro } from "../lib/money";
import CampaignCard from "../components/CampaignCard";
import Icon from "../components/ui/Icon";

type AutoPlayStatus = { enabled: boolean; interval_seconds: number };

type Props = {
  onNewCampaign: () => void;
  /** When set, auto-expands the matching campaign card on next render. Used
   *  by the wizard's "Done" → Campaigns navigation flow. */
  highlightId?: string | null;
};

export default function Campaigns({ onNewCampaign, highlightId }: Props) {
  const authedApi = useApi();
  const [expanded, setExpanded] = useState<string | null>(highlightId ?? null);

  // When a new highlightId arrives (e.g. user just funded another campaign),
  // expand it. We only react to changes — the local toggle still wins for
  // subsequent collapses.
  useEffect(() => {
    if (highlightId) setExpanded(highlightId);
  }, [highlightId]);

  const autoPlay = useQuery<AutoPlayStatus>({
    queryKey: ["auto-play-status"],
    queryFn: async () => {
      const r = await api.get<AutoPlayStatus>("/api/auto-play-status");
      return r.data;
    },
    staleTime: 60_000,
  });

  const pollMs = autoPlay.data?.enabled
    ? Math.min(5000, autoPlay.data.interval_seconds * 1000)
    : 5000;

  const campaigns = useQuery<CampaignRow[]>({
    queryKey: ["campaigns"],
    queryFn: async () => {
      const r = await authedApi.get<CampaignRow[]>("/api/campaigns");
      return r.data;
    },
    refetchInterval: pollMs,
  });

  if (campaigns.isLoading) {
    return (
      <div
        className="x-page"
        style={{
          color: "var(--tx-2)",
          fontFamily: "var(--font-mono)",
          fontSize: 12,
        }}
      >
        loading…
      </div>
    );
  }

  if (campaigns.isError) {
    return (
      <div className="x-page">
        <p
          style={{
            color: "var(--st-expired)",
            fontFamily: "var(--font-mono)",
            fontSize: 12,
          }}
        >
          Failed to load campaigns: {humanizeError(campaigns.error)}
        </p>
      </div>
    );
  }

  const rows = campaigns.data ?? [];

  if (rows.length === 0) {
    return <Empty onNewCampaign={onNewCampaign} />;
  }

  const activeCount = rows.filter((c) => c.status === "active").length;
  const totalSpentMicro = sumMicro(rows.map((c) => c.spent));
  const totalBudgetMicro = sumMicro(rows.map((c) => c.budget));

  return (
    <div className="x-page">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-end",
          marginBottom: 24,
        }}
      >
        <div>
          <div
            className="x-display"
            style={{ fontSize: 28, letterSpacing: "-0.025em" }}
          >
            Campaigns
          </div>
          <div style={{ fontSize: 13, color: "var(--tx-2)", marginTop: 4 }}>
            {rows.length} campaign{rows.length === 1 ? "" : "s"} · {activeCount}{" "}
            active · {formatUsdc(totalSpentMicro, 2)} USDC spent of{" "}
            {formatUsdc(totalBudgetMicro, 2)} funded
          </div>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {rows.map((c) => (
          <CampaignCard
            key={c.id}
            campaign={c}
            expanded={expanded === c.id}
            onToggle={() => setExpanded((cur) => (cur === c.id ? null : c.id))}
          />
        ))}
      </div>
    </div>
  );
}

function Empty({ onNewCampaign }: { onNewCampaign: () => void }) {
  return (
    <div className="x-page">
      <div
        className="x-display"
        style={{ fontSize: 28, letterSpacing: "-0.025em" }}
      >
        Campaigns
      </div>
      <div style={{ fontSize: 13, color: "var(--tx-2)", marginTop: 4 }}>
        You haven't shipped a campaign yet.
      </div>

      <div
        className="x-card"
        style={{
          marginTop: 24,
          padding: "56px 32px",
          textAlign: "center",
          position: "relative",
          overflow: "hidden",
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
        <div style={{ position: "relative" }}>
          <div
            className="x-display"
            style={{
              fontSize: 20,
              marginTop: 22,
              letterSpacing: "-0.02em",
            }}
          >
            No campaigns yet
          </div>
          <div style={{ fontSize: 13, color: "var(--tx-1)", marginTop: 6 }}>
            Click{" "}
            <span style={{ color: "var(--tx-0)", fontWeight: 600 }}>
              + New campaign
            </span>{" "}
            to get started.
          </div>
          <button
            className="x-btn x-btn-grad x-btn-lg"
            style={{ marginTop: 18 }}
            onClick={onNewCampaign}
          >
            <Icon name="plus" size={13} stroke={2} /> New campaign
          </button>
        </div>
      </div>
    </div>
  );
}
