import { create } from "zustand";

/**
 * Small shared flag that lets any component ask WalletPanel to poll the
 * backend's /api/wallet for a short window. Devnet RPC typically lags 2–5s
 * behind finality, so a one-shot query invalidation right after a settled
 * tx usually still returns the stale balance. Components that know they
 * just moved money should call `startPolling(ms)` after success — the
 * WalletPanel will refetch every 2s until the window closes.
 */
interface WalletTrackState {
  isPolling: boolean;
  startPolling: (durationMs: number) => void;
}

let pendingTimeout: number | null = null;

export const useWalletTrack = create<WalletTrackState>((set) => ({
  isPolling: false,
  startPolling: (durationMs: number) => {
    if (pendingTimeout !== null) window.clearTimeout(pendingTimeout);
    set({ isPolling: true });
    pendingTimeout = window.setTimeout(() => {
      set({ isPolling: false });
      pendingTimeout = null;
    }, durationMs);
  },
}));
