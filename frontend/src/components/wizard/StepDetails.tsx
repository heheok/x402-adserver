import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { usePrivy } from "@privy-io/react-auth";
import { useSolanaWallets } from "@privy-io/react-auth/solana";
import { createX402Client } from "x402-solana/client";

import { useApi } from "../../lib/api";
import { humanizeError } from "../../lib/errors";
import { solscanTxUrl, truncateAddress } from "../../lib/format";
import { useWalletTrack } from "../../lib/walletTrack";
import type { CreativeAsset } from "./StepImage";

type WalletInfo = { wallet_address: string; usdc_balance: number };

type CampaignSummary = {
  id: string;
  name: string;
  status: string;
  budget: number;
  spent: number;
  remaining: number;
  wallet_address: string;
};

export type CreatedCampaign = CampaignSummary & { tx_hash?: string };

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const DEFAULT_FORM = {
  name: "Demo campaign",
  cpm_price: 1.0,
  budget: 0.1,
  duration: 15,
};

type Props = {
  creative: CreativeAsset;
  onBack: () => void;
  onCreated?: (campaign: CreatedCampaign) => void;
};

export default function StepDetails({ creative, onBack, onCreated }: Props) {
  const api = useApi();
  const qc = useQueryClient();
  const { wallets } = useSolanaWallets();
  const { getAccessToken } = usePrivy();
  const startPolling = useWalletTrack((s) => s.startPolling);

  const wallet = useQuery<WalletInfo>({
    queryKey: ["wallet"],
    queryFn: async () => {
      const r = await api.get<WalletInfo>("/api/wallet");
      return r.data;
    },
    enabled: wallets.length > 0,
  });

  const [form, setForm] = useState(() => ({ ...DEFAULT_FORM }));
  const [stage, setStage] = useState<
    "idle" | "preparing" | "signing" | "settling"
  >("idle");
  const [result, setResult] = useState<CreatedCampaign | null>(null);

  const submit = useMutation<CreatedCampaign>({
    mutationFn: async () => {
      if (!wallets[0]) throw new Error("No Solana wallet connected");
      const token = await getAccessToken();
      if (!token) throw new Error("Not authenticated — sign in again");

      let fetchIndex = 0;
      const instrumentedFetch: typeof fetch = async (input, init) => {
        const idx = fetchIndex++;
        if (idx === 1) setStage("settling");
        const response = await fetch(input, init);
        if (idx === 0) setStage("signing");
        return response;
      };

      const client = createX402Client({
        wallet: wallets[0],
        network: "solana-devnet",
        amount: BigInt(Math.ceil(form.budget * 1.05 * 1e6)),
        customFetch: instrumentedFetch,
      });

      const body = {
        ...form,
        creative_url: creative.creative_url,
        creative_id: creative.creative_id,
      };

      const res = await client.fetch(`${API_BASE}/api/campaigns`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Backend ${res.status}: ${text.slice(0, 300)}`);
      }

      const responseBody: CampaignSummary = await res.json();

      const header = res.headers.get("X-PAYMENT-RESPONSE");
      let tx_hash: string | undefined;
      if (header) {
        try {
          const decoded = JSON.parse(atob(header));
          tx_hash = decoded.transaction;
        } catch {
          tx_hash = header;
        }
      }

      return { ...responseBody, tx_hash };
    },
    onMutate: () => {
      setResult(null);
      setStage("preparing");
    },
    onSuccess: (data) => {
      setStage("idle");
      setResult(data);
      qc.invalidateQueries({ queryKey: ["campaigns"] });
      qc.invalidateQueries({ queryKey: ["wallet"] });
      startPolling(20_000);
      onCreated?.(data);
    },
    onError: () => {
      setStage("idle");
    },
  });

  const busy = submit.isPending;
  const balance = wallet.data?.usdc_balance ?? 0;
  const insufficientBalance =
    wallet.data !== undefined && form.budget > balance + 1e-9;
  const canSubmit =
    !busy &&
    wallets.length > 0 &&
    form.name.trim().length > 0 &&
    form.cpm_price > 0 &&
    form.budget > 0 &&
    !insufficientBalance;

  const stageLabel =
    stage === "preparing"
      ? "Creating campaign wallet on devnet (bootstrap + USDC ATA, ~5s)…"
      : stage === "signing"
        ? "Approve the USDC transfer in your wallet popup…"
        : stage === "settling"
          ? "Facilitator settling on devnet (~5–10s)…"
          : null;

  return (
    <div>
      <h3>Campaign details</h3>
      <p className="muted footnote">
        Funds via the x402 handshake: signing transfers USDC from your wallet to
        a fresh campaign wallet owned by the ad server.
      </p>

      <div
        style={{
          display: "flex",
          gap: "0.75rem",
          alignItems: "center",
          margin: "0.75rem 0",
          padding: "0.5rem",
          border: "1px solid var(--border)",
          borderRadius: 8,
          background: "rgba(255,255,255,0.02)",
        }}
      >
        <img
          src={creative.preview_data_url || creative.creative_url}
          alt="creative"
          style={{ width: 96, height: 54, objectFit: "cover", borderRadius: 4 }}
        />
        <div style={{ minWidth: 0, flex: 1 }}>
          <p className="muted footnote" style={{ margin: 0 }}>
            Creative
          </p>
          <code
            style={{
              display: "block",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {truncateAddress(creative.creative_id, 8)}
          </code>
        </div>
      </div>

      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          submit.mutate();
        }}
      >
        <label>
          <span>Name</span>
          <input
            type="text"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            disabled={busy}
            required
          />
        </label>

        <div className="row">
          <label>
            <span>CPM (USDC)</span>
            <input
              type="number"
              step="0.01"
              min="0.01"
              value={form.cpm_price}
              onChange={(e) =>
                setForm({ ...form, cpm_price: Number(e.target.value) })
              }
              disabled={busy}
              required
            />
          </label>

          <label>
            <span>Budget (USDC)</span>
            <input
              type="number"
              step="0.001"
              min="0.001"
              value={form.budget}
              onChange={(e) =>
                setForm({ ...form, budget: Number(e.target.value) })
              }
              disabled={busy}
              required
            />
          </label>

          <label>
            <span>Duration (s)</span>
            <input
              type="number"
              min="1"
              max="30"
              value={form.duration}
              onChange={(e) =>
                setForm({ ...form, duration: Number(e.target.value) })
              }
              disabled={busy}
              required
            />
          </label>
        </div>

        <div className="actions">
          <button type="button" className="secondary" onClick={onBack} disabled={busy}>
            Back
          </button>
          <button type="submit" disabled={!canSubmit}>
            {busy ? "Funding…" : `Create & fund (${form.budget} USDC)`}
          </button>
          {stageLabel && (
            <span className="pending">
              <span className="pulse" aria-hidden>
                ●
              </span>{" "}
              {stageLabel}
            </span>
          )}
        </div>
      </form>

      {insufficientBalance && !submit.isError && (
        <p className="error">
          Budget {form.budget} USDC exceeds your wallet balance of{" "}
          {balance.toFixed(4)} USDC. Hit "Get test USDC" first.
        </p>
      )}

      {submit.isError && <p className="error">{humanizeError(submit.error)}</p>}

      {result && (
        <div className="success">
          <p>
            <strong>Campaign funded.</strong> id <code>{result.id}</code>,
            wallet <code>{truncateAddress(result.wallet_address, 6)}</code>.
          </p>
          {result.tx_hash && (
            <p className="footnote">
              Funding tx:{" "}
              <a
                href={solscanTxUrl(result.tx_hash)}
                target="_blank"
                rel="noreferrer"
              >
                {truncateAddress(result.tx_hash, 6)}
              </a>
            </p>
          )}
        </div>
      )}
    </div>
  );
}
