import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSolanaWallets } from "@privy-io/react-auth/solana";

import { useApi } from "../../lib/api";
import { humanizeError } from "../../lib/errors";
import { cmpMicro, formatUsdc, parseUsdc, subMicro } from "../../lib/money";
import Icon from "../ui/Icon";
import { Footer, Lbl } from "./Modal";
import type { ScheduleWindow } from "./StepSchedule";
import type { TargetingSelection } from "./StepTargeting";

// Money fields are microUSDC strings (Session 16.9). 1 USDC = 1e6 micro.
export type Quote = {
  screens: number;
  plays_per_screen_per_day: number;
  days: number;
  total_plays: number;
  cpm_price: string; // microUSDC per 1000 plays
  total_usdc: string;
  protocol_fee_pct: number; // display ratio (0.025 = 2.5%)
  protocol_fee_usdc: string;
  total_to_escrow_usdc: string;
};

type WalletInfo = { wallet_address: string; usdc_balance: string };

type Props = {
  targeting: TargetingSelection;
  schedule: ScheduleWindow;
  onBack: () => void;
  onComplete: (quote: Quote) => void;
};

export default function StepCalculator({
  targeting,
  schedule,
  onBack,
  onComplete,
}: Props) {
  const api = useApi();
  const { wallets } = useSolanaWallets();

  const quote = useQuery<Quote>({
    queryKey: [
      "quote",
      targeting.target_dmas.slice().sort().join(","),
      schedule.start_date,
      schedule.end_date,
    ],
    queryFn: async () => {
      const r = await api.post<Quote>("/api/campaigns/quote", {
        target_dmas: targeting.target_dmas,
        start_date: schedule.start_date,
        end_date: schedule.end_date,
      });
      return r.data;
    },
    staleTime: 30_000,
  });

  const wallet = useQuery<WalletInfo>({
    queryKey: ["wallet"],
    queryFn: async () => {
      const r = await api.get<WalletInfo>("/api/wallet");
      return r.data;
    },
    enabled: wallets.length > 0,
  });

  const q = quote.data;
  const balanceMicro = wallet.data?.usdc_balance ?? "0";
  const balance = parseUsdc(balanceMicro);
  // Exact integer compare in micro — no float drift, no epsilon.
  const insufficient =
    q !== undefined &&
    wallet.data !== undefined &&
    cmpMicro(q.total_to_escrow_usdc, balanceMicro) > 0;

  return (
    <>
      <div style={{ padding: 22 }}>
        <Lbl>Budget · auto-derived</Lbl>
        <div style={{ marginTop: 6, fontSize: 12, color: "var(--tx-2)" }}>
          CPM is locked during devnet. Server computes the breakdown from your
          DMA selection × schedule.
        </div>

        {quote.isLoading && (
          <div
            style={{
              marginTop: 14,
              padding: 16,
              fontSize: 12,
              color: "var(--tx-2)",
              fontFamily: "var(--font-mono)",
              borderRadius: 12,
              background: "var(--bg-2)",
              border: "1px solid var(--line-1)",
            }}
          >
            computing quote…
          </div>
        )}
        {quote.isError && (
          <p
            style={{
              marginTop: 14,
              fontSize: 12,
              color: "var(--st-expired)",
              fontFamily: "var(--font-mono)",
            }}
          >
            {humanizeError(quote.error)}
          </p>
        )}

        {q && (
          <div
            className="x-card"
            style={{ marginTop: 14, background: "var(--bg-2)" }}
          >
            <Calc label="Screens" value={q.screens.toLocaleString()} mono />
            <Calc
              label="Plays / screen / day"
              value={q.plays_per_screen_per_day}
              mono
            />
            <Calc label="Days" value={q.days} mono />
            <Calc
              label="Total plays"
              value={q.total_plays.toLocaleString()}
              bold
              mono
            />
            <Calc
              label={
                <span>
                  CPM <span style={{ color: "var(--tx-3)" }}>(locked)</span>
                </span>
              }
              value={`${formatUsdc(q.cpm_price, 2)} USDC`}
              mono
            />
            <Calc
              label="Total"
              value={`${formatUsdc(q.total_usdc, 2)} USDC`}
              mono
              bold
            />
            <Calc
              label={`Protocol fee · ${(q.protocol_fee_pct * 100).toFixed(1)}%`}
              value={`${formatUsdc(q.protocol_fee_usdc, 2)} USDC`}
              mono
              muted
            />
            <Calc
              label="Total to escrow"
              value={`${formatUsdc(q.total_to_escrow_usdc, 2)} USDC`}
              highlight
            />
          </div>
        )}

        {q && wallet.data && (
          <div
            style={{
              marginTop: 12,
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "10px 14px",
              borderRadius: 10,
              background: insufficient
                ? "rgba(255,122,69,0.06)"
                : "var(--bg-2)",
              border: `1px solid ${insufficient ? "rgba(255,122,69,0.30)" : "var(--line-1)"}`,
            }}
          >
            <div
              style={{ display: "flex", alignItems: "center", gap: 10 }}
            >
              <Icon name="wallet" size={14} />
              <span style={{ fontSize: 12, color: "var(--tx-1)" }}>
                Wallet balance
              </span>
            </div>
            <span
              className="x-mono x-tnum"
              style={{
                fontWeight: 500,
                color: insufficient
                  ? "var(--st-expired)"
                  : "var(--tx-0)",
              }}
            >
              {balance.toLocaleString("en-US", { minimumFractionDigits: 2 })}{" "}
              USDC
            </span>
          </div>
        )}

        {insufficient && q && (
          <div
            style={{
              marginTop: 8,
              fontSize: 11,
              color: "var(--st-expired)",
              fontFamily: "var(--font-mono)",
            }}
          >
            Insufficient balance · need{" "}
            {formatUsdc(subMicro(q.total_to_escrow_usdc, balanceMicro), 2)} more
            USDC. Use the faucet from the wallet menu.
          </div>
        )}
      </div>

      <Footer
        right={
          <>
            <button className="x-btn" onClick={onBack}>
              Back
            </button>
            <button
              className="x-btn x-btn-primary"
              disabled={!q || insufficient}
              onClick={() => q && onComplete(q)}
            >
              Next <Icon name="arrowRight" size={12} stroke={2} />
            </button>
          </>
        }
      />
    </>
  );
}

function Calc({
  label,
  value,
  bold,
  mono,
  muted,
  highlight,
}: {
  label: ReactNode;
  value: ReactNode;
  bold?: boolean;
  mono?: boolean;
  muted?: boolean;
  highlight?: boolean;
}) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "10px 14px",
        borderTop: "1px solid var(--line-1)",
        background: highlight
          ? "linear-gradient(135deg, rgba(153,69,255,0.08), rgba(20,241,149,0.04))"
          : "transparent",
      }}
    >
      <span
        style={{
          fontSize: 12,
          color: muted ? "var(--tx-2)" : "var(--tx-1)",
        }}
      >
        {label}
      </span>
      <span
        className={mono ? "x-mono x-tnum" : "x-tnum"}
        style={{
          fontSize: highlight ? 15 : 13,
          fontWeight: bold || highlight ? 600 : 500,
          color: highlight
            ? "var(--tx-0)"
            : muted
              ? "var(--tx-2)"
              : "var(--tx-0)",
        }}
      >
        {value}
      </span>
    </div>
  );
}
