import { useState } from "react";
import type { ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, useApi } from "../lib/api";
import {
  type CampaignRow,
  type SettlementRow,
  type StatsRow,
  formatDmas,
  timeAgo,
} from "../lib/aggregations";
import { humanizeError } from "../lib/errors";
import { solscanAccountUrl, truncateAddress } from "../lib/format";
import { formatUsdc, parseUsdc, subMicro } from "../lib/money";
import { useWalletTrack } from "../lib/walletTrack";
import CreativeThumb from "./ui/CreativeThumb";
import Icon from "./ui/Icon";
import { LiveActivityMap } from "./LiveActivityMap";
import Progress from "./ui/Progress";
import Solscan from "./ui/Solscan";
import StatusBadge from "./ui/StatusBadge";

type RefundResponse = {
  refund_amount: string; // microUSDC string
  tx_hash: string | null;
  solscan_url: string | null;
};

type AutoPlayStatus = { enabled: boolean; interval_seconds: number };

type Props = {
  campaign: CampaignRow;
  expanded: boolean;
  onToggle: () => void;
};

export default function CampaignCard({
  campaign,
  expanded,
  onToggle,
}: Props) {
  const authedApi = useApi();
  const qc = useQueryClient();
  const startPolling = useWalletTrack((s) => s.startPolling);

  const autoPlay = useQuery<AutoPlayStatus>({
    queryKey: ["auto-play-status"],
    queryFn: async () => {
      const r = await api.get<AutoPlayStatus>("/api/auto-play-status");
      return r.data;
    },
    staleTime: 60_000,
  });

  const [actionError, setActionError] = useState<string | null>(null);

  const stats = useQuery<StatsRow & { cpm_price: string; remaining_budget: string }>({
    queryKey: ["campaign-stats", campaign.id],
    queryFn: async () => {
      const r = await authedApi.get(`/api/campaigns/${campaign.id}/stats`);
      return r.data;
    },
    enabled: expanded,
    // Always poll while the card is expanded so the user sees plays settle
    // live regardless of auto-play state. Tighten to the auto-play tick when
    // it's running so the rhythm matches.
    refetchInterval: expanded
      ? autoPlay.data?.enabled
        ? Math.min(5000, autoPlay.data.interval_seconds * 1000)
        : 5000
      : false,
  });

  function invalidateCampaign() {
    qc.invalidateQueries({ queryKey: ["campaigns"] });
    qc.invalidateQueries({ queryKey: ["campaign-stats", campaign.id] });
  }

  const pause = useMutation({
    mutationFn: async () => {
      await authedApi.post(`/api/campaigns/${campaign.id}/pause`);
    },
    onMutate: () => setActionError(null),
    onSuccess: invalidateCampaign,
    onError: (err: Error) => setActionError(humanizeError(err)),
  });

  const resume = useMutation({
    mutationFn: async () => {
      await authedApi.post(`/api/campaigns/${campaign.id}/resume`);
    },
    onMutate: () => setActionError(null),
    onSuccess: invalidateCampaign,
    onError: (err: Error) => setActionError(humanizeError(err)),
  });

  const refund = useMutation({
    mutationFn: async () => {
      const r = await authedApi.post<RefundResponse>(
        `/api/campaigns/${campaign.id}/refund`,
      );
      return r.data;
    },
    onMutate: () => setActionError(null),
    onSuccess: () => {
      invalidateCampaign();
      qc.invalidateQueries({ queryKey: ["wallet"] });
      startPolling(20_000);
    },
    onError: (err: Error) => setActionError(humanizeError(err)),
  });

  // Percentage is float — fine because it's a ratio, never compared to budget.
  const budgetUsdc = parseUsdc(campaign.budget);
  const spentUsdc = parseUsdc(campaign.spent);
  const pct = budgetUsdc > 0 ? spentUsdc / budgetUsdc : 0;
  const busy = pause.isPending || resume.isPending || refund.isPending;

  const dmaSummary =
    campaign.target_dmas && campaign.target_dmas.length > 0
      ? campaign.target_dmas.join(" · ")
      : "—";
  const days =
    campaign.start_date && campaign.end_date
      ? Math.max(
          1,
          Math.ceil(
            (new Date(`${campaign.end_date}T00:00:00`).getTime() -
              new Date(`${campaign.start_date}T00:00:00`).getTime()) /
              86400000,
          ) + 1,
        )
      : null;

  // Collapsed view ---------------------------------------------------------
  if (!expanded) {
    return (
      <div
        className="x-card x-camp-collapsed"
        onClick={onToggle}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onToggle();
          }
        }}
        style={{
          padding: 18,
          display: "grid",
          gridTemplateColumns: "40px 1fr 220px 24px",
          alignItems: "center",
          gap: 16,
          cursor: "pointer",
        }}
      >
        <CreativeThumb seed={campaign.id} size={40} label={campaign.name} />
        <div style={{ minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span
              style={{
                fontSize: 14,
                fontWeight: 600,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {campaign.name}
            </span>
            <StatusBadge status={campaign.status} />
          </div>
          <div
            style={{
              fontSize: 11,
              color: "var(--tx-2)",
              marginTop: 4,
              fontFamily: "var(--font-mono)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {dmaSummary}
            {days ? ` · ${days} day${days === 1 ? "" : "s"}` : ""}
          </div>
        </div>
        <div>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              fontSize: 11,
              marginBottom: 6,
            }}
          >
            <span
              style={{
                color: "var(--tx-2)",
                fontFamily: "var(--font-mono)",
              }}
            >
              SPENT
            </span>
            <span className="x-mono x-tnum" style={{ color: "var(--tx-1)" }}>
              {formatUsdc(campaign.spent)}{" "}
              <span style={{ color: "var(--tx-3)" }}>
                / {formatUsdc(campaign.budget)}
              </span>
            </span>
          </div>
          <Progress
            value={pct}
            color={
              campaign.status === "active"
                ? "var(--tint-grad-strong)"
                : "var(--tx-3)"
            }
            shine={campaign.status === "active" && pct > 0}
          />
        </div>
        <Icon name="chevron" size={14} />
      </div>
    );
  }

  // Expanded view ----------------------------------------------------------
  const lastPlay: SettlementRow | undefined = stats.data?.recent_settlements[0];

  return (
    <div
      className="x-card x-ring-grad"
      style={{ padding: 20, position: "relative", overflow: "hidden" }}
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
          className="x-camp-expanded-head"
          style={{
            display: "grid",
            gridTemplateColumns: "64px 1fr auto",
            alignItems: "center",
            gap: 16,
          }}
        >
          <CreativeThumb seed={campaign.id} size={64} label={campaign.name} />
          <div style={{ minWidth: 0 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                flexWrap: "wrap",
              }}
            >
              <span className="x-display" style={{ fontSize: 18 }}>
                {campaign.name}
              </span>
              <StatusBadge status={campaign.status} />
              {days && (
                <span
                  style={{
                    fontSize: 11,
                    color: "var(--tx-2)",
                    fontFamily: "var(--font-mono)",
                    whiteSpace: "nowrap",
                  }}
                >
                  · {days} day{days === 1 ? "" : "s"}
                </span>
              )}
            </div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                flexWrap: "wrap",
                fontSize: 11,
                color: "var(--tx-2)",
                marginTop: 6,
                fontFamily: "var(--font-mono)",
              }}
            >
              <span style={{ whiteSpace: "nowrap" }}>
                Wallet {truncateAddress(campaign.wallet_address, 4)}
              </span>
              <Solscan href={solscanAccountUrl(campaign.wallet_address)}>
                View on Solscan
              </Solscan>
            </div>
          </div>
          <div
            style={{
              display: "flex",
              gap: 8,
              flexWrap: "wrap",
              justifyContent: "flex-end",
            }}
          >
            {campaign.status === "active" && (
              <button
                className="x-btn x-btn-sm"
                onClick={() => pause.mutate()}
                disabled={busy}
              >
                <Icon name="pause" size={11} />{" "}
                {pause.isPending ? "Pausing…" : "Pause"}
              </button>
            )}
            {campaign.status === "paused" && (
              <>
                <button
                  className="x-btn x-btn-sm"
                  onClick={() => resume.mutate()}
                  disabled={busy}
                >
                  <Icon name="play" size={11} />{" "}
                  {resume.isPending ? "Resuming…" : "Resume"}
                </button>
                <button
                  className="x-btn x-btn-sm"
                  onClick={() => refund.mutate()}
                  disabled={busy}
                >
                  <Icon name="refund" size={11} />{" "}
                  {refund.isPending ? "Refunding…" : "Refund"}
                </button>
              </>
            )}
            {(campaign.status === "completed" ||
              campaign.status === "expired") && (
              <button
                className="x-btn x-btn-sm"
                onClick={() => refund.mutate()}
                disabled={busy}
              >
                <Icon name="refund" size={11} />{" "}
                {refund.isPending ? "Refunding…" : "Refund"}
              </button>
            )}
            <button
              className="x-btn x-btn-sm"
              onClick={onToggle}
              aria-label="Collapse"
            >
              <Icon name="chevronUp" size={11} />
            </button>
          </div>
        </div>

        <hr className="x-hr" style={{ margin: "18px 0" }} />

        {/* Stats grid */}
        <div
          className="x-grid-md-3 x-grid-sm-2"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(6, 1fr)",
            gap: 16,
          }}
        >
          <Stat
            label="Plays"
            value={stats.data?.total_plays?.toLocaleString() ?? "—"}
            sub={
              stats.data && (stats.data.pending_plays ?? 0) > 0 ? (
                <span
                  style={{
                    color: "var(--tx-2)",
                    fontFamily: "var(--font-mono)",
                  }}
                >
                  {stats.data.pending_plays} queued
                </span>
              ) : undefined
            }
          />
          <Stat
            label="CPM"
            value={
              stats.data ? (
                <>
                  {formatUsdc(stats.data.cpm_price, 2)}{" "}
                  <span style={{ fontSize: 10, color: "var(--tx-2)" }}>
                    USDC
                  </span>
                </>
              ) : (
                "—"
              )
            }
          />
          <Stat label="Spent" value={formatUsdc(campaign.spent)} />
          <Stat
            label={campaign.status === "refunded" ? "Refunded" : "Remaining"}
            value={
              <span
                style={{
                  color:
                    campaign.status === "refunded"
                      ? "var(--st-refunded)"
                      : "var(--sol-teal)",
                }}
              >
                {formatUsdc(subMicro(campaign.budget, campaign.spent))}
              </span>
            }
            sub={
              campaign.wallet_address ? (
                <Solscan href={solscanAccountUrl(campaign.wallet_address)}>
                  wallet {truncateAddress(campaign.wallet_address, 4)}
                </Solscan>
              ) : null
            }
          />
          <Stat
            label="Protocol fee"
            value={
              campaign.protocol_fee_amount != null
                ? formatUsdc(campaign.protocol_fee_amount)
                : "—"
            }
            sub={
              campaign.protocol_fee_tx_hash &&
              campaign.protocol_fee_solscan_url ? (
                <Solscan href={campaign.protocol_fee_solscan_url}>
                  tx {truncateAddress(campaign.protocol_fee_tx_hash, 4)}
                </Solscan>
              ) : null
            }
          />
          <Stat
            small
            label="Schedule"
            value={
              campaign.start_date && campaign.end_date
                ? `${campaign.start_date.slice(5)} → ${campaign.end_date.slice(5)}`
                : "—"
            }
          />
        </div>

        {/* Budget bar */}
        <div style={{ marginTop: 14 }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              fontSize: 11,
              marginBottom: 6,
            }}
          >
            <span
              style={{
                color: "var(--tx-2)",
                fontFamily: "var(--font-mono)",
              }}
            >
              BUDGET ·{" "}
              {budgetUsdc > 0
                ? (pct * 100).toFixed(1)
                : "0.0"}
              % spent
            </span>
            <span className="x-mono x-tnum" style={{ color: "var(--tx-1)" }}>
              {formatUsdc(campaign.spent)} / {formatUsdc(campaign.budget)} USDC
            </span>
          </div>
          <Progress
            value={pct}
            shine={campaign.status === "active" && pct > 0}
          />
        </div>

        <hr className="x-hr" style={{ margin: "18px 0" }} />

        {/* Targeting + last play */}
        <div
          className="x-grid-sm-1"
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 24,
          }}
        >
          <div>
            <div
              style={{
                fontSize: 10,
                color: "var(--tx-2)",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                fontFamily: "var(--font-mono)",
              }}
            >
              Target DMAs
            </div>
            <div
              style={{
                display: "flex",
                gap: 8,
                marginTop: 8,
                flexWrap: "wrap",
              }}
            >
              {(campaign.target_dmas ?? []).map((dma) => (
                <div
                  key={dma}
                  style={{
                    padding: "6px 10px",
                    borderRadius: 8,
                    border: "1px solid var(--line-1)",
                    background: "var(--bg-2)",
                    fontSize: 12,
                    fontWeight: 500,
                  }}
                >
                  {dma}
                </div>
              ))}
              {(!campaign.target_dmas || campaign.target_dmas.length === 0) && (
                <span
                  style={{
                    fontSize: 12,
                    color: "var(--tx-2)",
                    fontFamily: "var(--font-mono)",
                  }}
                >
                  no targeting
                </span>
              )}
            </div>
          </div>
          <div>
            <div
              style={{
                fontSize: 10,
                color: "var(--tx-2)",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                fontFamily: "var(--font-mono)",
              }}
            >
              Last play
            </div>
            {lastPlay ? (
              <div
                style={{
                  marginTop: 8,
                  padding: "10px 12px",
                  borderRadius: 10,
                  background: "var(--bg-2)",
                  border: "1px solid var(--line-1)",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <div
                  style={{ display: "flex", alignItems: "center", gap: 10 }}
                >
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: 4,
                      background:
                        lastPlay.status === "confirmed"
                          ? "var(--sol-teal)"
                          : lastPlay.status === "pending"
                            ? "var(--tx-2)"
                            : "var(--st-expired)",
                      boxShadow:
                        lastPlay.status === "confirmed"
                          ? "0 0 10px var(--sol-teal)"
                          : "none",
                    }}
                  />
                  <div>
                    <div
                      style={{
                        fontSize: 12,
                        color: "var(--tx-0)",
                        fontWeight: 500,
                      }}
                    >
                      {lastPlay.dmas.length > 0
                        ? formatDmas(lastPlay.dmas)
                        : "Unknown DMA"}
                    </div>
                    <div
                      style={{
                        fontSize: 10,
                        color: "var(--tx-2)",
                        fontFamily: "var(--font-mono)",
                      }}
                    >
                      {timeAgo(lastPlay.created_at)} ·{" "}
                      {truncateAddress(lastPlay.publisher_wallet, 4)} ·{" "}
                      {lastPlay.status === "confirmed"
                        ? "settled on-chain"
                        : lastPlay.status === "pending"
                          ? "queued"
                          : "settlement failed"}
                    </div>
                  </div>
                </div>
                {lastPlay.tx_hash && lastPlay.solscan_url && (
                  <Solscan href={lastPlay.solscan_url}>
                    {truncateAddress(lastPlay.tx_hash, 4)}
                  </Solscan>
                )}
              </div>
            ) : (
              <div
                style={{
                  marginTop: 8,
                  fontSize: 12,
                  color: "var(--tx-2)",
                  fontFamily: "var(--font-mono)",
                }}
              >
                no plays yet
              </div>
            )}
          </div>
        </div>

        {campaign.target_dmas && campaign.target_dmas.length > 0 && (
          <div style={{ marginTop: 18 }}>
            <LiveActivityMap
              targetDmas={campaign.target_dmas}
              playsByDma={stats.data?.plays_by_dma ?? {}}
            />
          </div>
        )}

        {actionError && (
          <p
            style={{
              marginTop: 12,
              color: "var(--st-expired)",
              fontSize: 12,
              fontFamily: "var(--font-mono)",
            }}
          >
            {actionError}
          </p>
        )}

        <hr className="x-hr" style={{ margin: "18px 0" }} />

        {/* Recent settlements */}
        <div>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 8,
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 600 }}>
              Recent settlements
            </div>
            <span
              style={{
                fontSize: 11,
                color: "var(--tx-2)",
                fontFamily: "var(--font-mono)",
              }}
            >
              last 10 · /proof verified
            </span>
          </div>
          <div
            className="x-stl-row"
            style={{
              display: "grid",
              gridTemplateColumns: "70px 90px 1fr 130px 110px 80px",
              padding: "8px 0",
              fontSize: 10,
              color: "var(--tx-3)",
              fontFamily: "var(--font-mono)",
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              borderBottom: "1px solid var(--line-1)",
            }}
          >
            <span>When</span>
            <span>Plays</span>
            <span>DMA</span>
            <span>Publisher</span>
            <span style={{ textAlign: "right" }}>Amount</span>
            <span style={{ textAlign: "right" }}>Tx</span>
          </div>
          {stats.isLoading && (
            <div
              style={{
                padding: "12px 0",
                fontSize: 12,
                color: "var(--tx-2)",
                fontFamily: "var(--font-mono)",
              }}
            >
              loading…
            </div>
          )}
          {stats.data && stats.data.recent_settlements.length === 0 && (
            <div
              style={{
                padding: "16px 0",
                fontSize: 12,
                color: "var(--tx-2)",
                fontFamily: "var(--font-mono)",
              }}
            >
              no settlements yet
            </div>
          )}
          {stats.data?.recent_settlements.map((s, i) => (
            <div
              key={s.tx_hash ?? s.id}
              className="x-stl-row"
              style={{
                display: "grid",
                gridTemplateColumns: "70px 90px 1fr 130px 110px 80px",
                alignItems: "center",
                padding: "11px 0",
                borderTop: i === 0 ? "none" : "1px solid var(--line-1)",
                fontSize: 12,
              }}
            >
              <span
                style={{
                  color: "var(--tx-2)",
                  fontFamily: "var(--font-mono)",
                }}
              >
                {timeAgo(s.created_at)}
              </span>
              <span
                className="x-mono"
                style={{
                  color: s.play_count > 1 ? "var(--tx-0)" : "var(--tx-2)",
                  fontSize: 11,
                  fontWeight: s.play_count > 1 ? 600 : 400,
                }}
              >
                {s.play_count > 1 ? `×${s.play_count}` : "—"}
              </span>
              <span
                title={s.dmas.length > 1 ? s.dmas.join(", ") : undefined}
                style={{
                  color: s.dmas.length > 0 ? "var(--tx-1)" : "var(--tx-3)",
                  fontSize: 11,
                  fontFamily:
                    s.dmas.length > 0
                      ? "var(--font-sans)"
                      : "var(--font-mono)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {formatDmas(s.dmas)}
              </span>
              <span
                className="x-mono"
                style={{ color: "var(--tx-1)", fontSize: 11 }}
              >
                {truncateAddress(s.publisher_wallet, 4)}
              </span>
              <span
                className="x-mono x-tnum"
                style={{
                  color:
                    s.status === "confirmed"
                      ? "var(--sol-teal)"
                      : s.status === "pending" || s.status === "flushing"
                        ? "var(--tx-2)"
                        : "var(--st-expired)",
                  textAlign: "right",
                }}
              >
                {s.status === "confirmed" ? "+" : ""}
                {formatUsdc(s.amount_usdc)}
              </span>
              <span style={{ textAlign: "right" }}>
                {s.tx_hash && s.solscan_url ? (
                  <Solscan href={s.solscan_url}>
                    {truncateAddress(s.tx_hash, 4)}
                  </Solscan>
                ) : s.status === "pending" || s.status === "flushing" ? (
                  <span
                    style={{
                      fontSize: 10,
                      color: "var(--tx-2)",
                      fontFamily: "var(--font-mono)",
                    }}
                  >
                    queued
                  </span>
                ) : (
                  <span
                    style={{
                      fontSize: 10,
                      color: "var(--st-expired)",
                      fontFamily: "var(--font-mono)",
                    }}
                  >
                    failed
                  </span>
                )}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  small,
  sub,
}: {
  label: string;
  value: ReactNode;
  small?: boolean;
  sub?: ReactNode;
}) {
  return (
    <div>
      <div
        style={{
          fontSize: 10,
          color: "var(--tx-2)",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          fontFamily: "var(--font-mono)",
        }}
      >
        {label}
      </div>
      <div
        className="x-display x-tnum"
        style={{
          fontSize: small ? 14 : 18,
          marginTop: 6,
          lineHeight: 1.1,
        }}
      >
        {value}
      </div>
      {sub && (
        <div
          style={{
            marginTop: 6,
            fontSize: 10,
            fontFamily: "var(--font-mono)",
            color: "var(--tx-2)",
            display: "flex",
            gap: 4,
            alignItems: "center",
          }}
        >
          {sub}
        </div>
      )}
    </div>
  );
}

