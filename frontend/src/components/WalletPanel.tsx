import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSolanaWallets } from "@privy-io/react-auth/solana";
import { isAxiosError } from "axios";

import { useApi } from "../lib/api";
import {
  solscanAccountUrl,
  solscanTxUrl,
  truncateAddress,
} from "../lib/format";
import { useWalletTrack } from "../lib/walletTrack";

type WalletInfo = { wallet_address: string; usdc_balance: number };
type FaucetResponse = { amount: number; tx_hash: string };

export default function WalletPanel() {
  const api = useApi();
  const qc = useQueryClient();
  const { wallets, createWallet } = useSolanaWallets();
  const hasSolanaWallet = wallets.length > 0;

  const [lastFaucetTx, setLastFaucetTx] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  // "+X USDC inbound" indicator while we wait for devnet confirmation.
  const [pendingAmount, setPendingAmount] = useState<number | null>(null);
  const [balanceBefore, setBalanceBefore] = useState<number | null>(null);
  const isPolling = useWalletTrack((s) => s.isPolling);
  const startPolling = useWalletTrack((s) => s.startPolling);

  // Only query the backend once Privy has a Solana wallet for this user —
  // otherwise /api/wallet returns 400 (no Solana wallet linked). Also retry
  // 400/404 a few times with short backoff for the fresh-signup race where
  // Privy's server-side link lags the client-side wallet creation.
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
      // Snapshot the balance at click time so we can detect when the
      // deposit has actually landed (vs. the query just refetching the
      // same number).
      setBalanceBefore(wallet.data?.usdc_balance ?? 0);
    },
    onSuccess: (data) => {
      setLastFaucetTx(data.tx_hash);
      setPendingAmount(data.amount);
      startPolling(20_000);
      qc.invalidateQueries({ queryKey: ["wallet"] });
    },
  });

  // Clear the pending indicator the moment the new balance shows up.
  useEffect(() => {
    if (pendingAmount === null || balanceBefore === null) return;
    const current = wallet.data?.usdc_balance;
    if (current === undefined) return;
    // Small tolerance for floating-point noise from Solana's 6-decimal USDC.
    if (current >= balanceBefore + pendingAmount - 1e-6) {
      setPendingAmount(null);
      setBalanceBefore(null);
    }
  }, [wallet.data?.usdc_balance, pendingAmount, balanceBefore]);

  async function handleCreateWallet() {
    setCreating(true);
    try {
      await createWallet();
      // Give Privy's server a beat to link the wallet to the user, then
      // kick the query. Retry logic on the query handles the rest.
      window.setTimeout(
        () => qc.invalidateQueries({ queryKey: ["wallet"] }),
        1500,
      );
    } finally {
      setCreating(false);
    }
  }

  // --- render paths ---------------------------------------------------------

  if (!hasSolanaWallet) {
    return (
      <section className="card">
        <h2>Your wallet</h2>
        <p className="muted">
          You don't have a Solana wallet yet. Create one to fund campaigns.
        </p>
        <div className="actions">
          <button onClick={handleCreateWallet} disabled={creating}>
            {creating ? "Creating…" : "Create Solana wallet"}
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="card">
      <h2>Your wallet</h2>

      {wallet.isLoading && <p className="muted">Loading…</p>}
      {wallet.isError && !wallet.isFetching && (
        <p className="error">
          Could not load wallet: {(wallet.error as Error).message}
        </p>
      )}

      {wallet.data && (
        <div className="kv">
          <div>
            <span className="muted">Address</span>
            <a
              href={solscanAccountUrl(wallet.data.wallet_address)}
              target="_blank"
              rel="noreferrer"
            >
              <code>{truncateAddress(wallet.data.wallet_address, 6)}</code>
            </a>
          </div>
          <div>
            <span className="muted">Balance</span>
            <strong>{wallet.data.usdc_balance.toFixed(4)} USDC</strong>
          </div>
          {pendingAmount !== null && (
            <div className="pending">
              <span className="muted">Inbound</span>
              <span>
                <span className="pulse" aria-hidden>
                  ●
                </span>{" "}
                +{pendingAmount.toFixed(4)} USDC · confirming on devnet…
              </span>
            </div>
          )}
        </div>
      )}

      <div className="actions">
        <button
          onClick={() => faucet.mutate()}
          disabled={faucet.isPending || wallet.isLoading || !wallet.data}
        >
          {faucet.isPending ? "Sending…" : "Get test USDC"}
        </button>
      </div>

      {faucet.isError && (
        <p className="error">
          Faucet failed: {(faucet.error as Error).message}
        </p>
      )}
      {lastFaucetTx && (
        <p className="footnote muted">
          Last faucet tx:{" "}
          <a href={solscanTxUrl(lastFaucetTx)} target="_blank" rel="noreferrer">
            {truncateAddress(lastFaucetTx, 6)}
          </a>
        </p>
      )}
    </section>
  );
}
