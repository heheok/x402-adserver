import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { usePrivy } from "@privy-io/react-auth";
import { useSolanaWallets } from "@privy-io/react-auth/solana";
import { isAxiosError } from "axios";

import { useApi } from "../lib/api";
import { humanizeError } from "../lib/errors";
import {
  solscanAccountUrl,
  solscanTxUrl,
  truncateAddress,
} from "../lib/format";
import { parseUsdc } from "../lib/money";
import { useWalletTrack } from "../lib/walletTrack";
import Icon from "./ui/Icon";
import Solscan from "./ui/Solscan";

// Wire format: usdc_balance and amount are microUSDC strings (Session 16.9).
// We parse to float USDC once at this boundary for the chip's UI delta math
// (animating "+0.42 USDC inbound"). This is the ONE place float USDC is
// allowed — it's a pure UX indicator, never compared against a campaign
// budget. See worklog/session-16.9.md.
type WalletInfo = { wallet_address: string; usdc_balance: string };
type FaucetResponse = { amount: string; tx_hash: string };

const LOW_BALANCE_THRESHOLD = 1; // USDC

export default function WalletChip() {
  const api = useApi();
  const qc = useQueryClient();
  const { logout } = usePrivy();
  const { wallets, createWallet } = useSolanaWallets();
  const hasSolanaWallet = wallets.length > 0;

  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [copied, setCopied] = useState(false);
  const [lastFaucetTx, setLastFaucetTx] = useState<string | null>(null);
  const [pendingAmount, setPendingAmount] = useState<number | null>(null);
  const [balanceBefore, setBalanceBefore] = useState<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const isPolling = useWalletTrack((s) => s.isPolling);
  const startPolling = useWalletTrack((s) => s.startPolling);

  const wallet = useQuery<WalletInfo>({
    queryKey: ["wallet"],
    queryFn: async () => {
      const r = await api.get<WalletInfo>("/api/wallet");
      return r.data;
    },
    enabled: hasSolanaWallet,
    refetchInterval: isPolling ? 2000 : false,
    retry: (failureCount, error) => {
      if (failureCount >= 5) return false;
      if (isAxiosError(error)) {
        const s = error.response?.status;
        return s === 400 || s === 404;
      }
      return false;
    },
    retryDelay: 1500,
  });

  const faucet = useMutation<FaucetResponse>({
    mutationFn: async () => {
      const r = await api.post<FaucetResponse>("/api/faucet");
      return r.data;
    },
    onMutate: () => {
      setBalanceBefore(parseUsdc(wallet.data?.usdc_balance ?? "0"));
    },
    onSuccess: (data) => {
      setLastFaucetTx(data.tx_hash);
      setPendingAmount(parseUsdc(data.amount));
      startPolling(20_000);
      qc.invalidateQueries({ queryKey: ["wallet"] });
    },
  });

  // Clear the pending indicator when the new balance lands. The 1e-6
  // tolerance is a UI signal, not a money-correctness check — so float USDC
  // is fine here.
  useEffect(() => {
    if (pendingAmount === null || balanceBefore === null) return;
    const current = wallet.data?.usdc_balance;
    if (current === undefined) return;
    const currentUsdc = parseUsdc(current);
    if (currentUsdc >= balanceBefore + pendingAmount - 1e-6) {
      setPendingAmount(null);
      setBalanceBefore(null);
    }
  }, [wallet.data?.usdc_balance, pendingAmount, balanceBefore]);

  // Close dropdown on outside click + ESC.
  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function handleCreateWallet() {
    setCreating(true);
    try {
      await createWallet();
      window.setTimeout(
        () => qc.invalidateQueries({ queryKey: ["wallet"] }),
        1500,
      );
    } finally {
      setCreating(false);
    }
  }

  async function copyAddress() {
    if (!wallet.data) return;
    try {
      await navigator.clipboard.writeText(wallet.data.wallet_address);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  }

  // ── States ────────────────────────────────────────────────────────────────

  if (!hasSolanaWallet) {
    return (
      <button
        className="x-btn x-btn-sm"
        onClick={handleCreateWallet}
        disabled={creating}
      >
        <Icon name="wallet" size={13} />
        {creating ? "Creating…" : "Create Solana wallet"}
      </button>
    );
  }

  const balance = parseUsdc(wallet.data?.usdc_balance ?? "0");
  const isLow = wallet.data !== undefined && balance < LOW_BALANCE_THRESHOLD;
  const isPending = pendingAmount !== null;
  const accent = isLow ? "var(--st-paused)" : "var(--line-2)";

  return (
    <div ref={containerRef} style={{ position: "relative" }}>
      <button
        onClick={() => setOpen((v) => !v)}
        className={isLow ? "x-pulse" : undefined}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 8,
          height: 36,
          padding: "0 12px",
          background: "var(--bg-2)",
          color: "var(--tx-0)",
          border: `1px solid ${accent}`,
          borderRadius: 10,
          fontSize: 13,
          fontWeight: 500,
          cursor: "pointer",
        }}
      >
        <span
          style={{
            width: 18,
            height: 18,
            borderRadius: 5,
            background: "var(--tint-grad-strong)",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 9,
            color: "#08070A",
            fontWeight: 700,
            fontFamily: "var(--font-mono)",
          }}
        >
          $
        </span>
        <span
          style={{
            fontSize: 11,
            color: "var(--tx-2)",
            fontFamily: "var(--font-mono)",
          }}
        >
          Wallet
        </span>
        <span style={{ width: 1, height: 14, background: "var(--line-1)" }} />
        {isPending ? (
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
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
            <span className="x-tnum">+{pendingAmount?.toFixed(2)}</span>
            <span style={{ color: "var(--tx-2)", fontSize: 11 }}>USDC</span>
          </span>
        ) : (
          <span className="x-mono x-tnum" style={{ fontWeight: 500 }}>
            {balance.toLocaleString("en-US", {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
            <span style={{ color: "var(--tx-2)", marginLeft: 4, fontSize: 11 }}>
              USDC
            </span>
          </span>
        )}
        <Icon name={open ? "chevronUp" : "chevron"} size={11} stroke={2} />
      </button>

      {open && wallet.data && (
        <div
          className="x-card"
          style={{
            position: "absolute",
            top: 44,
            right: 0,
            width: 320,
            padding: 16,
            boxShadow: "var(--shadow-card)",
            zIndex: 50,
            background: "var(--bg-1)",
          }}
        >
          <div
            style={{
              fontSize: 10,
              color: "var(--tx-2)",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              fontFamily: "var(--font-mono)",
            }}
          >
            Wallet address
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              marginTop: 6,
            }}
          >
            <span
              className="x-mono"
              style={{ fontSize: 12, color: "var(--tx-1)" }}
            >
              {truncateAddress(wallet.data.wallet_address, 4)}
            </span>
            <button
              type="button"
              onClick={copyAddress}
              title={copied ? "Copied" : "Copy address"}
              style={{
                width: 22,
                height: 22,
                border: 0,
                borderRadius: 5,
                background: "var(--bg-3)",
                color: copied ? "var(--sol-teal)" : "var(--tx-2)",
                cursor: "pointer",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Icon
                name={copied ? "check" : "copy"}
                size={11}
                stroke={1.6}
              />
            </button>
            <Solscan href={solscanAccountUrl(wallet.data.wallet_address)}>
              View on Solscan
            </Solscan>
          </div>

          <div
            style={{
              marginTop: 14,
              padding: 14,
              borderRadius: 10,
              background:
                "linear-gradient(135deg, rgba(153,69,255,0.10), rgba(20,241,149,0.06))",
              border: "1px solid var(--line-1)",
            }}
          >
            <div
              style={{
                fontSize: 10,
                color: "var(--tx-2)",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                fontFamily: "var(--font-mono)",
              }}
            >
              Balance
            </div>
            <div
              className="x-mono x-tnum"
              style={{
                fontSize: 24,
                fontWeight: 500,
                marginTop: 4,
                letterSpacing: "-0.02em",
              }}
            >
              {balance.toLocaleString("en-US", { minimumFractionDigits: 2 })}
              <span
                style={{
                  fontSize: 12,
                  color: "var(--tx-2)",
                  marginLeft: 6,
                  fontWeight: 500,
                }}
              >
                USDC
              </span>
            </div>
            {isLow && !isPending && (
              <div
                style={{
                  marginTop: 8,
                  fontSize: 11,
                  color: "var(--st-paused)",
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                <Icon name="info" size={12} /> Low balance — use the faucet to
                start a campaign.
              </div>
            )}
            {isPending && pendingAmount !== null && (
              <div
                style={{
                  marginTop: 8,
                  fontSize: 11,
                  color: "var(--sol-teal)",
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
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
                inbound +{pendingAmount.toFixed(2)} USDC · confirming…
              </div>
            )}
          </div>

          <button
            className="x-btn x-btn-grad"
            style={{ width: "100%", marginTop: 12, height: 40 }}
            onClick={() => faucet.mutate()}
            disabled={faucet.isPending}
          >
            <Icon name="plus" size={13} stroke={2} />
            {faucet.isPending ? "Sending…" : "Get test USDC"}
          </button>

          {faucet.isError && (
            <div
              style={{
                marginTop: 8,
                fontSize: 11,
                color: "var(--st-expired)",
              }}
            >
              {humanizeError(faucet.error)}
            </div>
          )}
          {lastFaucetTx && !faucet.isError && (
            <div
              style={{
                marginTop: 8,
                fontSize: 11,
                color: "var(--tx-2)",
                fontFamily: "var(--font-mono)",
                display: "flex",
                gap: 6,
                alignItems: "center",
              }}
            >
              last faucet tx
              <Solscan href={solscanTxUrl(lastFaucetTx)}>
                {truncateAddress(lastFaucetTx, 4)}
              </Solscan>
            </div>
          )}

          <div
            style={{
              marginTop: 12,
              paddingTop: 12,
              borderTop: "1px solid var(--line-1)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span
              style={{
                fontSize: 11,
                color: "var(--tx-2)",
                fontFamily: "var(--font-mono)",
              }}
            >
              Privy embedded · devnet
            </span>
            <button
              onClick={() => {
                setOpen(false);
                logout();
              }}
              style={{
                background: "transparent",
                border: 0,
                color: "var(--tx-2)",
                fontSize: 11,
                cursor: "pointer",
                fontFamily: "var(--font-mono)",
              }}
            >
              Disconnect
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
