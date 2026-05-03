// Session 16.9: every money field on the wire is an integer-microUSDC string
// (e.g. "422000" = $0.422). 1 USDC = 1_000_000 microUSDC. See lib/money.ts
// for parse/format/sum helpers — never do raw arithmetic on these strings
// (use BigInt or sumMicro/subMicro).

export type CampaignRow = {
  id: string;
  name: string;
  status: string;
  budget: string; // microUSDC string
  spent: string;
  remaining: string;
  wallet_address: string;
  target_dmas?: string[] | null;
  start_date?: string | null;
  end_date?: string | null;
  protocol_fee_amount?: string | null;
  protocol_fee_tx_hash?: string | null;
  protocol_fee_solscan_url?: string | null;
};

// One row per batch — the backend (services/batches.py) collapses raw
// Settlement rows by tx_hash for confirmed plays and by (campaign,
// publisher) for queued ones, so the dashboard shows one row per batch
// across the whole pending → confirmed lifecycle. See backend
// app/schemas.py:SettlementSummary for the full lifecycle notes.
export type SettlementRow = {
  id: string; // tx_hash if confirmed, else `pending:{cid}:{pubw}`
  publisher_wallet: string;
  amount_usdc: string; // microUSDC string (sum across plays in the batch)
  tx_hash: string | null;
  solscan_url: string | null;
  status: string;
  created_at: string; // latest play in the batch
  play_count: number;
  dmas: string[];
};

export type StatsRow = {
  campaign_id: string;
  // Session 16.8: total_plays + last_24h_plays count pending+confirmed
  // (plays that happened, regardless of on-chain settlement state).
  // pending_plays surfaces the unflushed queue length so the UI can show
  // an "N queued" indicator. total_confirmed_usdc stays confirmed-only.
  total_plays: number;
  last_24h_plays: number;
  pending_plays?: number;
  total_confirmed_usdc: string; // microUSDC string
  plays_by_dma?: Record<string, number>;
  recent_settlements: SettlementRow[];
};

export function byStatus(rows: CampaignRow[]): Record<string, number> {
  const out: Record<string, number> = {
    draft: 0,
    active: 0,
    paused: 0,
    completed: 0,
    expired: 0,
    refunded: 0,
  };
  for (const r of rows) {
    out[r.status] = (out[r.status] ?? 0) + 1;
  }
  return out;
}

export function expiringSoon(rows: CampaignRow[], withinDays = 3): number {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const cutoffMs = today.getTime() + withinDays * 86400000;
  let n = 0;
  for (const r of rows) {
    if (r.status !== "active" || !r.end_date) continue;
    const end = new Date(`${r.end_date}T00:00:00`).getTime();
    if (Number.isNaN(end)) continue;
    if (end >= today.getTime() && end <= cutoffMs) n++;
  }
  return n;
}

/** Render a batch's DMA set compactly: "NY", "NY · LA", "NY +2". */
export function formatDmas(dmas: string[]): string {
  if (dmas.length === 0) return "—";
  if (dmas.length === 1) return dmas[0];
  if (dmas.length === 2) return `${dmas[0]} · ${dmas[1]}`;
  return `${dmas[0]} +${dmas.length - 1}`;
}

// "32s ago" / "4m ago" / "2h ago" / "3d ago".
export function timeAgo(iso: string, now: number = Date.now()): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "—";
  const sec = Math.max(0, Math.round((now - t) / 1000));
  if (sec < 60) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  return `${day}d ago`;
}
