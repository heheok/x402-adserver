import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useApi } from "../lib/api";
import { solscanAccountUrl, solscanTxUrl, truncateAddress } from "../lib/format";
import { useWalletTrack } from "../lib/walletTrack";

export type CampaignSummary = {
  id: string;
  name: string;
  status: string;
  budget: number;
  spent: number;
  remaining: number;
  wallet_address: string;
};

type SettlementSummary = {
  id: string;
  nonce: string;
  publisher_wallet: string;
  amount_usdc: number;
  tx_hash: string | null;
  solscan_url: string | null;
  status: string;
  created_at: string;
};

type CampaignStats = {
  campaign_id: string;
  status: string;
  budget: number;
  spent: number;
  remaining_budget: number;
  total_plays: number;
  total_confirmed_usdc: number;
  cpm_price: number;
  recent_settlements: SettlementSummary[];
};

type SimulatePlayResponse = {
  amount_usdc: number;
  tx_hash: string;
  solscan_url: string;
  publisher_wallet: string;
};

type RefundResponse = {
  refund_amount: number;
  tx_hash: string | null;
  solscan_url: string | null;
};

const STATUS_LABELS: Record<string, string> = {
  draft: "draft",
  active: "active",
  paused: "paused",
  completed: "completed",
  refunded: "refunded",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`badge badge-${status}`}>
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

export default function CampaignCard({
  campaign,
}: {
  campaign: CampaignSummary;
}) {
  const api = useApi();
  const qc = useQueryClient();
  const startPolling = useWalletTrack((s) => s.startPolling);
  const [expanded, setExpanded] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [lastSimTx, setLastSimTx] = useState<string | null>(null);
  const [lastRefundTx, setLastRefundTx] = useState<string | null>(null);

  const stats = useQuery<CampaignStats>({
    queryKey: ["campaign-stats", campaign.id],
    queryFn: async () => {
      const r = await api.get<CampaignStats>(
        `/api/campaigns/${campaign.id}/stats`,
      );
      return r.data;
    },
    enabled: expanded,
  });

  function invalidateCampaign() {
    qc.invalidateQueries({ queryKey: ["campaigns"] });
    qc.invalidateQueries({ queryKey: ["campaign-stats", campaign.id] });
  }

  const simulate = useMutation({
    mutationFn: async () => {
      const r = await api.post<SimulatePlayResponse>(
        `/api/campaigns/${campaign.id}/simulate-play`,
      );
      return r.data;
    },
    onMutate: () => setActionError(null),
    onSuccess: (data) => {
      setLastSimTx(data.tx_hash);
      invalidateCampaign();
    },
    onError: (err: Error) => setActionError(err.message),
  });

  const pause = useMutation({
    mutationFn: async () => {
      await api.post(`/api/campaigns/${campaign.id}/pause`);
    },
    onMutate: () => setActionError(null),
    onSuccess: invalidateCampaign,
    onError: (err: Error) => setActionError(err.message),
  });

  const resume = useMutation({
    mutationFn: async () => {
      await api.post(`/api/campaigns/${campaign.id}/resume`);
    },
    onMutate: () => setActionError(null),
    onSuccess: invalidateCampaign,
    onError: (err: Error) => setActionError(err.message),
  });

  const refund = useMutation({
    mutationFn: async () => {
      const r = await api.post<RefundResponse>(
        `/api/campaigns/${campaign.id}/refund`,
      );
      return r.data;
    },
    onMutate: () => setActionError(null),
    onSuccess: (data) => {
      if (data.tx_hash) setLastRefundTx(data.tx_hash);
      invalidateCampaign();
      qc.invalidateQueries({ queryKey: ["wallet"] });
      // Refund credits the advertiser wallet — poll until the devnet RPC
      // catches up with the transfer.
      startPolling(20_000);
    },
    onError: (err: Error) => setActionError(err.message),
  });

  const pct =
    campaign.budget > 0
      ? Math.min(100, (campaign.spent / campaign.budget) * 100)
      : 0;
  const busy =
    simulate.isPending || pause.isPending || resume.isPending || refund.isPending;
  const canRefund =
    campaign.status === "paused" || campaign.status === "completed";

  return (
    <div className="campaign-card">
      <div
        className="campaign-summary"
        onClick={() => setExpanded((v) => !v)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setExpanded((v) => !v);
          }
        }}
      >
        <div className="campaign-title">
          <strong>{campaign.name}</strong>
          <StatusBadge status={campaign.status} />
        </div>
        <div className="campaign-progress">
          <div className="bar">
            <div className="fill" style={{ width: `${pct}%` }} />
          </div>
          <span className="muted footnote">
            {campaign.spent.toFixed(4)} / {campaign.budget.toFixed(4)} USDC
          </span>
        </div>
        <span className="muted">{expanded ? "▾" : "▸"}</span>
      </div>

      {expanded && (
        <div className="campaign-detail">
          <div className="kv">
            <div>
              <span className="muted">Campaign wallet</span>
              <a
                href={solscanAccountUrl(campaign.wallet_address)}
                target="_blank"
                rel="noreferrer"
              >
                <code>{truncateAddress(campaign.wallet_address, 6)}</code>
              </a>
            </div>
            {stats.data && (
              <>
                <div>
                  <span className="muted">Plays</span>
                  <span>{stats.data.total_plays}</span>
                </div>
                <div>
                  <span className="muted">CPM</span>
                  <span>{stats.data.cpm_price.toFixed(4)} USDC</span>
                </div>
                <div>
                  <span className="muted">Remaining</span>
                  <span>
                    {stats.data.remaining_budget.toFixed(4)} USDC
                  </span>
                </div>
              </>
            )}
          </div>

          <div className="actions">
            {campaign.status === "active" && (
              <>
                <button
                  onClick={() => simulate.mutate()}
                  disabled={busy}
                >
                  {simulate.isPending ? "Playing…" : "Simulate play"}
                </button>
                <button
                  onClick={() => pause.mutate()}
                  disabled={busy}
                  className="secondary"
                >
                  {pause.isPending ? "Pausing…" : "Pause"}
                </button>
              </>
            )}
            {campaign.status === "paused" && (
              <>
                <button
                  onClick={() => resume.mutate()}
                  disabled={busy}
                >
                  {resume.isPending ? "Resuming…" : "Resume"}
                </button>
                <button
                  onClick={() => refund.mutate()}
                  disabled={busy}
                  className="secondary"
                >
                  {refund.isPending ? "Refunding…" : "Refund remaining"}
                </button>
              </>
            )}
            {campaign.status === "completed" && (
              <button
                onClick={() => refund.mutate()}
                disabled={busy || !canRefund}
                className="secondary"
              >
                {refund.isPending ? "Refunding…" : "Refund"}
              </button>
            )}
            {campaign.status === "refunded" && (
              <span className="muted footnote">Campaign refunded — no further actions.</span>
            )}
          </div>

          {actionError && <p className="error">{actionError}</p>}
          {lastSimTx && (
            <p className="footnote muted">
              Last play:{" "}
              <a
                href={solscanTxUrl(lastSimTx)}
                target="_blank"
                rel="noreferrer"
              >
                {truncateAddress(lastSimTx, 6)}
              </a>
            </p>
          )}
          {lastRefundTx && (
            <p className="footnote muted">
              Refund tx:{" "}
              <a
                href={solscanTxUrl(lastRefundTx)}
                target="_blank"
                rel="noreferrer"
              >
                {truncateAddress(lastRefundTx, 6)}
              </a>
            </p>
          )}

          {stats.isLoading && <p className="muted footnote">Loading stats…</p>}
          {stats.data && stats.data.recent_settlements.length > 0 && (
            <div className="settlements">
              <h4>Recent plays</h4>
              <ul>
                {stats.data.recent_settlements.map((s) => (
                  <li key={s.id}>
                    <span>{s.amount_usdc.toFixed(6)} USDC → </span>
                    <a
                      href={solscanAccountUrl(s.publisher_wallet)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <code>{truncateAddress(s.publisher_wallet, 4)}</code>
                    </a>
                    {s.tx_hash && s.solscan_url && (
                      <>
                        {" · "}
                        <a href={s.solscan_url} target="_blank" rel="noreferrer">
                          tx {truncateAddress(s.tx_hash, 4)}
                        </a>
                      </>
                    )}
                    {s.status === "failed" && (
                      <span className="error"> (failed)</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
