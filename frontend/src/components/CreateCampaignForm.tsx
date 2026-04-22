import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { usePrivy } from "@privy-io/react-auth";
import { useSolanaWallets } from "@privy-io/react-auth/solana";
import { createX402Client } from "x402-solana/client";

import { useApi } from "../lib/api";
import { humanizeError } from "../lib/errors";
import { solscanTxUrl, truncateAddress } from "../lib/format";
import { useWalletTrack } from "../lib/walletTrack";

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

type CreatedCampaign = CampaignSummary & { tx_hash?: string };

type Props = {
  onCreated?: (campaign: CreatedCampaign) => void;
};

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const DEFAULT_FORM = {
  name: "Demo campaign",
  creative_url: "https://example.com/creative.mp4",
  creative_id: "",
  cpm_price: 1.0,
  budget: 0.1,
  duration: 15,
};

export default function CreateCampaignForm({ onCreated }: Props = {}) {
  const api = useApi();
  const qc = useQueryClient();
  const { wallets } = useSolanaWallets();
  const { getAccessToken } = usePrivy();
  const startPolling = useWalletTrack((s) => s.startPolling);

  // Re-uses WalletPanel's cache so no extra network request.
  const wallet = useQuery<WalletInfo>({
    queryKey: ["wallet"],
    queryFn: async () => {
      const r = await api.get<WalletInfo>("/api/wallet");
      return r.data;
    },
    enabled: wallets.length > 0,
  });

  const [form, setForm] = useState(() => ({
    ...DEFAULT_FORM,
    creative_id: `creative-${Math.random().toString(36).slice(2, 10)}`,
  }));
  const [stage, setStage] = useState<
    "idle" | "preparing" | "signing" | "settling"
  >("idle");
  const [result, setResult] = useState<CreatedCampaign | null>(null);

  const submit = useMutation<CreatedCampaign>({
    mutationFn: async () => {
      if (!wallets[0]) throw new Error("No Solana wallet connected");
      const token = await getAccessToken();
      if (!token) throw new Error("Not authenticated — sign in again");

      // Instrument the fetch so we can move the stage indicator through the
      // 402 handshake's real phases. The x402 client calls customFetch twice:
      // first for the initial POST (bootstrap + 402), then for the retry with
      // the signed X-PAYMENT payload (facilitator settlement).
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
        // Safety cap — client refuses to sign above this. Pad slightly above
        // our declared budget so float-math doesn't accidentally trip it.
        amount: BigInt(Math.ceil(form.budget * 1.05 * 1e6)),
        customFetch: instrumentedFetch,
      });

      const res = await client.fetch(`${API_BASE}/api/campaigns`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(form),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Backend ${res.status}: ${text.slice(0, 300)}`);
      }

      const body: CampaignSummary = await res.json();

      // X-PAYMENT-RESPONSE is base64(JSON{transaction,...}) per x402 v1 spec;
      // our backend currently returns the raw tx signature as a plain string.
      // Try the spec-correct parse first, fall back to raw.
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

      return { ...body, tx_hash };
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
      // Devnet RPC lags a few seconds behind finality — ask WalletPanel
      // to poll /api/wallet until the debit shows up in the balance.
      startPolling(20_000);
      setForm((f) => ({
        ...f,
        name: "",
        creative_id: `creative-${Math.random().toString(36).slice(2, 10)}`,
      }));
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
    form.creative_url.trim().length > 0 &&
    form.creative_id.trim().length > 0 &&
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
    <div className="subform">
      <h3>Create campaign</h3>
      <p className="muted footnote">
        Funds via the x402 handshake: signing transfers USDC from your wallet to
        a fresh campaign wallet owned by the ad server.
      </p>

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

        <label>
          <span>Creative URL</span>
          <input
            type="url"
            value={form.creative_url}
            onChange={(e) => setForm({ ...form, creative_url: e.target.value })}
            disabled={busy}
            required
          />
        </label>

        <label>
          <span>Creative ID</span>
          <input
            type="text"
            value={form.creative_id}
            onChange={(e) => setForm({ ...form, creative_id: e.target.value })}
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

      {submit.isError && (
        <p className="error">{humanizeError(submit.error)}</p>
      )}

      {result && (
        <div className="success">
          <p>
            <strong>Campaign funded.</strong> id <code>{result.id}</code>,
            wallet{" "}
            <code>{truncateAddress(result.wallet_address, 6)}</code>.
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
