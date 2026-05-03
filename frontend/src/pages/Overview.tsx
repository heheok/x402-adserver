import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useApi, api } from "../lib/api";
import {
  byStatus,
  expiringSoon,
  formatDmas,
  groupByBatch,
  timeAgo,
  type CampaignRow,
} from "../lib/aggregations";
import { humanizeError } from "../lib/errors";
import { truncateAddress } from "../lib/format";
import { formatUsdc, sumMicro } from "../lib/money";
import Icon from "../components/ui/Icon";
import Solscan from "../components/ui/Solscan";
import StatCard from "../components/ui/StatCard";
import StatusBadge from "../components/ui/StatusBadge";

type AutoPlayStatus = { enabled: boolean; interval_seconds: number };

type ActivityRow = {
  id: string;
  nonce: string;
  campaign_id: string;
  campaign_name: string;
  publisher_wallet: string;
  amount_usdc: string; // microUSDC string
  tx_hash: string | null;
  solscan_url: string | null;
  status: string;
  created_at: string;
  dma: string | null;
};

type DashboardSummary = {
  total_plays: number;
  last_24h_plays: number;
  recent_activity: ActivityRow[];
};

type Props = {
  onNewCampaign: () => void;
  onJumpToCampaigns: () => void;
};

export default function Overview({ onNewCampaign, onJumpToCampaigns }: Props) {
  const authedApi = useApi();

  const autoPlay = useQuery<AutoPlayStatus>({
    queryKey: ["auto-play-status"],
    queryFn: async () => {
      const r = await api.get<AutoPlayStatus>("/api/auto-play-status");
      return r.data;
    },
    staleTime: 60_000,
  });

  // Always poll while the Overview tab is mounted — plays can come from
  // auto-play or real publisher /proof calls, none of which we can predict
  // from a single config flag. 5s is cheap at demo scale (≤10 campaigns)
  // and keeps the totals visibly live.
  // When auto-play is on we tighten to its tick so settlements land on the
  // same rhythm the user sees in the activity feed.
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

  // One server-side aggregate query replaces the previous N-campaign
  // /stats fan-out. See PLAN Session 16 — keeps Overview at 2 req/poll
  // regardless of campaign count.
  const summary = useQuery<DashboardSummary>({
    queryKey: ["dashboard-summary"],
    queryFn: async () => {
      const r = await authedApi.get<DashboardSummary>("/api/dashboard-summary");
      return r.data;
    },
    refetchInterval: pollMs,
  });

  const rows = campaigns.data ?? [];
  const totalSpentMicro = sumMicro(rows.map((c) => c.spent));
  const activeCount = rows.filter((c) => c.status === "active").length;
  const counts = byStatus(rows);
  const expiring = expiringSoon(rows, 3);
  const totalPlays = summary.data?.total_plays ?? 0;
  const last24hPlays = summary.data?.last_24h_plays ?? 0;
  const activity: ActivityRow[] = summary.data?.recent_activity ?? [];

  // Hook must be called unconditionally — passing the latest ID list lets the
  // hook diff against its own previous state to find newly-arrived rows.
  const flashIds = useFlashOnArrival(activity.map((a) => a.id));

  if (campaigns.isLoading) {
    return <Skeleton />;
  }

  if (campaigns.isError) {
    return (
      <div style={{ padding: "32px 28px" }}>
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

  if (rows.length === 0) {
    return <Empty onNewCampaign={onNewCampaign} />;
  }

  return (
    <div
      className="x-page"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 24,
      }}
    >
      <div
        className="x-flex-sm-col"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-end",
          gap: 12,
        }}
      >
        <div>
          <div
            className="x-display"
            style={{ fontSize: 28, letterSpacing: "-0.025em" }}
          >
            Overview
          </div>
          <div
            style={{ fontSize: 13, color: "var(--tx-2)", marginTop: 4 }}
          >
            Real-time campaign performance across the Solboards network.
          </div>
        </div>
        {autoPlay.data?.enabled && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              fontSize: 11,
              color: "var(--sol-teal)",
              fontFamily: "var(--font-mono)",
            }}
          >
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: 3,
                background: "var(--sol-teal)",
                boxShadow: "0 0 8px var(--sol-teal)",
              }}
            />
            Auto-simulating · every {autoPlay.data.interval_seconds}s
          </div>
        )}
      </div>

      {/* Stat grid */}
      <div
        className="x-grid-md-2 x-grid-sm-1"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: 16,
        }}
      >
        <StatCard
          label="Active campaigns"
          value={activeCount}
          sub={`of ${rows.length} total`}
          accent="var(--tint-grad-strong)"
        />
        <StatCard
          label="Total spent"
          value={
            <>
              {formatUsdc(totalSpentMicro)}{" "}
              <span style={{ fontSize: 14, color: "var(--tx-2)" }}>USDC</span>
            </>
          }
          sub="across all campaigns"
          accent="var(--x402-blue)"
        />
        <StatCard
          label="Total plays"
          value={totalPlays.toLocaleString()}
          sub="confirmed on-chain"
          accent="var(--sol-purple)"
        />
        <StatCard
          label="Last 24h plays"
          value={last24hPlays.toLocaleString()}
          sub="recent settlement activity"
          accent="var(--sol-teal)"
        />
      </div>

      {/* Status breakdown */}
      <div
        className="x-card x-status-row"
        style={{ display: "flex", overflow: "hidden" }}
      >
        <StatusChip status="active" count={counts.active} />
        <StatusChip status="paused" count={counts.paused} />
        <StatusChip status="completed" count={counts.completed} />
        <StatusChip status="expired" count={counts.expired} />
        <div
          style={{
            flex: 1,
            padding: "14px 16px",
            display: "flex",
            flexDirection: "column",
            gap: 4,
          }}
        >
          <div
            style={{ display: "flex", alignItems: "center", gap: 8 }}
          >
            <span
              className="x-badge"
              style={{
                color: "var(--st-paused)",
                background: "rgba(255,181,71,0.10)",
                border: "1px solid rgba(255,181,71,0.25)",
              }}
            >
              <span className="dot" />
              Expiring soon
            </span>
          </div>
          <div
            className="x-display x-tnum"
            style={{ fontSize: 22, marginTop: 4 }}
          >
            {expiring}
          </div>
          <div
            style={{
              fontSize: 10,
              color: "var(--tx-2)",
              fontFamily: "var(--font-mono)",
            }}
          >
            ≤ 3 days left
          </div>
        </div>
      </div>

      {/* Activity feed */}
      <div className="x-card" style={{ padding: "18px 20px 8px" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 6,
          }}
        >
          <div>
            <div style={{ fontSize: 14, fontWeight: 600 }}>Recent activity</div>
            <div
              style={{
                fontSize: 11,
                color: "var(--tx-2)",
                fontFamily: "var(--font-mono)",
                marginTop: 2,
              }}
            >
              last 10 settlements · all campaigns
            </div>
          </div>
          <button
            className="x-btn x-btn-sm x-btn-ghost"
            style={{
              background: "transparent",
              borderColor: "transparent",
              color: "var(--tx-2)",
            }}
            onClick={onJumpToCampaigns}
          >
            View all <Icon name="arrowRight" size={11} />
          </button>
        </div>
        <div
          className="x-act-row"
          style={{
            display: "grid",
            gridTemplateColumns: "90px 1fr 130px 110px 80px",
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
          <span>Campaign</span>
          <span>DMA</span>
          <span style={{ textAlign: "right" }}>Amount</span>
          <span style={{ textAlign: "right" }}>Tx</span>
        </div>
        {activity.length === 0 ? (
          <div
            style={{
              padding: "32px 0",
              textAlign: "center",
              color: "var(--tx-2)",
              fontSize: 12,
            }}
          >
            No plays yet — your campaigns are live but no impressions have
            settled.
          </div>
        ) : (
          groupByBatch(activity).map((s, i) => (
            <div
              key={s.tx_hash ?? s.id}
              className={
                flashIds.has(s.id) ? "x-act-row x-row-flash" : "x-act-row"
              }
              style={{
                display: "grid",
                gridTemplateColumns: "90px 1fr 130px 110px 80px",
                alignItems: "center",
                padding: "12px 0",
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
                style={{
                  color: "var(--tx-0)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {s.campaign_name}
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
                {formatUsdc(s.amount_usdc)}{" "}
                <span style={{ color: "var(--tx-2)", fontSize: 10 }}>USDC</span>
                {s.play_count > 1 && (
                  <span
                    style={{
                      color: "var(--tx-2)",
                      fontSize: 10,
                      marginLeft: 6,
                    }}
                  >
                    ×{s.play_count}
                  </span>
                )}
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
          ))
        )}
      </div>
    </div>
  );
}

function StatusChip({ status, count }: { status: string; count: number }) {
  return (
    <div
      style={{
        flex: 1,
        padding: "14px 16px",
        display: "flex",
        flexDirection: "column",
        gap: 4,
        borderRight: "1px solid var(--line-1)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <StatusBadge status={status} />
      </div>
      <div
        className="x-display x-tnum"
        style={{ fontSize: 22, marginTop: 4 }}
      >
        {count}
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
        Overview
      </div>
      <div style={{ fontSize: 13, color: "var(--tx-2)", marginTop: 4 }}>
        Real-time campaign performance across the Solboards network.
      </div>

      <div
        className="x-card"
        style={{
          marginTop: 28,
          padding: "64px 32px",
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
            style={{
              width: 56,
              height: 56,
              margin: "0 auto",
              borderRadius: 14,
              background: "var(--tint-grad-strong)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 12px 40px rgba(153,69,255,0.3)",
              color: "#08070A",
            }}
          >
            <Icon name="plus" size={22} stroke={2.4} />
          </div>
          <div
            className="x-display"
            style={{
              fontSize: 22,
              marginTop: 18,
              letterSpacing: "-0.02em",
            }}
          >
            Run your first <span className="x-grad-text">on-chain</span> ad
            campaign
          </div>
          <div
            style={{
              fontSize: 13,
              color: "var(--tx-1)",
              marginTop: 8,
              maxWidth: 420,
              marginInline: "auto",
              lineHeight: 1.55,
            }}
          >
            Upload a creative, pick markets, fund in USDC. Publishers serve your
            ad and settle every play on Solana.
          </div>
          <button
            className="x-btn x-btn-grad x-btn-lg"
            style={{ marginTop: 22 }}
            onClick={onNewCampaign}
          >
            <Icon name="plus" size={13} stroke={2} /> New campaign
          </button>
          <div
            style={{
              marginTop: 14,
              fontSize: 11,
              color: "var(--tx-2)",
              fontFamily: "var(--font-mono)",
            }}
          >
            devnet · CPM locked · 2.5% protocol fee
          </div>
        </div>
      </div>

      <div
        className="x-grid-sm-1"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: 16,
          marginTop: 16,
        }}
      >
        {[
          { n: "01", t: "Build", d: "Upload creative, pick DMAs, set dates." },
          {
            n: "02",
            t: "Fund",
            d: "One x402 transfer escrows your budget into a fresh campaign wallet on Solana.",
          },
          {
            n: "03",
            t: "Settle",
            d: "Devices call /bid + /proof. Publishers get paid per play, on-chain.",
          },
        ].map((s) => (
          <div key={s.n} className="x-card" style={{ padding: 18 }}>
            <div
              className="x-mono"
              style={{ fontSize: 11, color: "var(--tx-2)" }}
            >
              {s.n}
            </div>
            <div
              className="x-display"
              style={{ fontSize: 16, marginTop: 8 }}
            >
              {s.t}
            </div>
            <div
              style={{
                fontSize: 12,
                color: "var(--tx-1)",
                marginTop: 6,
                lineHeight: 1.5,
              }}
            >
              {s.d}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Skeleton() {
  return (
    <div
      className="x-page"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 24,
      }}
    >
      <style>{`@keyframes sk-shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }`}</style>
      <div>
        <Sk w={140} h={28} r={6} />
        <div style={{ marginTop: 8 }}>
          <Sk w={300} h={12} />
        </div>
      </div>
      <div
        className="x-grid-md-2 x-grid-sm-1"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: 16,
        }}
      >
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="x-card"
            style={{
              padding: 16,
              height: 110,
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
            }}
          >
            <Sk w={90} h={10} />
            <Sk w={120} h={26} r={6} />
            <Sk w={70} h={10} />
          </div>
        ))}
      </div>
    </div>
  );
}

function Sk({
  w,
  h = 12,
  r = 4,
}: {
  w: number | string;
  h?: number;
  r?: number;
}) {
  return (
    <span
      style={{
        display: "inline-block",
        width: w,
        height: h,
        borderRadius: r,
        background:
          "linear-gradient(90deg, var(--bg-2) 0%, var(--bg-3) 50%, var(--bg-2) 100%)",
        backgroundSize: "200% 100%",
        animation: "sk-shimmer 1.5s ease-in-out infinite",
      }}
    />
  );
}

// Returns the set of IDs that just appeared (weren't present in the previous
// non-empty list). The very first non-empty list is treated as "already
// seen" — we don't want every row to flash on initial mount. Each new ID
// stays in the returned set for FLASH_MS so the CSS animation has time to
// play, then the set is cleared and the next batch of arrivals can re-fill.
const FLASH_MS = 1800;

function useFlashOnArrival(currentIds: string[]): Set<string> {
  // Stable string key so the effect doesn't fire on every parent re-render
  // (useQueries returns new array refs even when data is unchanged).
  const idKey = currentIds.join(",");
  const seenRef = useRef<Set<string>>(new Set());
  const initializedRef = useRef(false);
  const [flashIds, setFlashIds] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    const newIds = new Set<string>();
    for (const id of currentIds) {
      if (!seenRef.current.has(id)) {
        if (initializedRef.current) newIds.add(id);
        seenRef.current.add(id);
      }
    }
    if (!initializedRef.current && currentIds.length > 0) {
      initializedRef.current = true;
    }
    if (newIds.size === 0) return;
    setFlashIds(newIds);
    const t = window.setTimeout(() => setFlashIds(new Set()), FLASH_MS);
    return () => window.clearTimeout(t);
    // We intentionally key on the joined IDs, not the array reference.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idKey]);

  return flashIds;
}
