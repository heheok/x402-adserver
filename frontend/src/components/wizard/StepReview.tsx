import type { ReactNode } from "react";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { usePrivy } from "@privy-io/react-auth";
import { useSolanaWallets } from "@privy-io/react-auth/solana";
import { createX402Client } from "x402-solana/client";

import { useApi } from "../../lib/api";
import { solanaRpcUrl } from "../../lib/rpc";
import { humanizeError } from "../../lib/errors";
import { solscanTxUrl, truncateAddress } from "../../lib/format";
import { cmpMicro, formatUsdc } from "../../lib/money";
import { useWalletTrack } from "../../lib/walletTrack";
import Icon from "../ui/Icon";
import Solscan from "../ui/Solscan";
import { Footer, Lbl } from "./Modal";
import type { CreativeAsset } from "./StepImage";
import type { Quote } from "./StepCalculator";
import type { ScheduleWindow } from "./StepSchedule";
import type { TargetingSelection } from "./StepTargeting";

type WalletInfo = { wallet_address: string; usdc_balance: string };

type CampaignSummary = {
  id: string;
  name: string;
  status: string;
  budget: string;
  spent: string;
  remaining: string;
  wallet_address: string;
  protocol_fee_amount?: string | null;
  protocol_fee_tx_hash?: string | null;
  protocol_fee_solscan_url?: string | null;
};

export type CreatedCampaign = CampaignSummary & { tx_hash?: string };

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

type FundStage = "preparing" | "signing" | "settling";

type Props = {
  creative: CreativeAsset;
  targeting: TargetingSelection;
  schedule: ScheduleWindow;
  quote: Quote;
  onBack: () => void;
  onCreated?: (campaign: CreatedCampaign) => void;
  onClose: () => void;
  onDone?: (campaign: CreatedCampaign) => void;
  onFundingStateChange?: (busy: boolean) => void;
};

export default function StepReview({
  creative,
  targeting,
  schedule,
  quote,
  onBack,
  onCreated,
  onClose,
  onDone,
  onFundingStateChange,
}: Props) {
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

  const [name, setName] = useState("");
  const [stage, setStage] = useState<FundStage | null>(null);
  const [completedStages, setCompletedStages] = useState<Set<FundStage>>(
    new Set(),
  );
  const [result, setResult] = useState<CreatedCampaign | null>(null);

  function setStageWithCompletion(next: FundStage) {
    setStage((prev) => {
      if (prev && prev !== next) {
        setCompletedStages((s) => {
          const n = new Set(s);
          n.add(prev);
          return n;
        });
      }
      return next;
    });
  }

  const submit = useMutation<CreatedCampaign>({
    mutationFn: async () => {
      if (!wallets[0]) throw new Error("No Solana wallet connected");
      const token = await getAccessToken();
      if (!token) throw new Error("Not authenticated — sign in again");

      let fetchIndex = 0;
      const instrumentedFetch: typeof fetch = async (input, init) => {
        const idx = fetchIndex++;
        if (idx === 1) setStageWithCompletion("settling");
        const response = await fetch(input, init);
        if (idx === 0) setStageWithCompletion("signing");
        return response;
      };

      const client = createX402Client({
        wallet: wallets[0],
        network: "solana-devnet",
        // x402-solana defaults to https://api.devnet.solana.com which the
        // browser can't reach reliably (CORS / rate limits). Prod build
        // points this at the Caddy /solana-rpc proxy.
        rpcUrl: solanaRpcUrl(),
        // Session 16.9: amount is exact integer micro from the server quote.
        // The historical *1.05 slack was a float-drift safety margin; gone now.
        amount: BigInt(quote.total_to_escrow_usdc),
        customFetch: instrumentedFetch,
      });

      const body = {
        name,
        creative_url: creative.creative_url,
        creative_id: creative.creative_id,
        target_dmas: targeting.target_dmas,
        start_date: schedule.start_date,
        end_date: schedule.end_date,
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
      setCompletedStages(new Set());
      setStage("preparing");
      onFundingStateChange?.(true);
    },
    onSuccess: (data) => {
      setCompletedStages(new Set(["preparing", "signing", "settling"]));
      setStage(null);
      setResult(data);
      qc.invalidateQueries({ queryKey: ["campaigns"] });
      qc.invalidateQueries({ queryKey: ["wallet"] });
      startPolling(20_000);
      onCreated?.(data);
      onFundingStateChange?.(false);
    },
    onError: () => {
      setStage(null);
      onFundingStateChange?.(false);
    },
  });

  const balanceMicro = wallet.data?.usdc_balance ?? "0";
  const insufficient =
    wallet.data !== undefined &&
    cmpMicro(quote.total_to_escrow_usdc, balanceMicro) > 0;
  const canSubmit =
    !submit.isPending &&
    wallets.length > 0 &&
    name.trim().length > 0 &&
    !insufficient;

  // Success view ------------------------------------------------------------
  if (result) {
    return (
      <>
        <div style={{ padding: "40px 22px 24px", textAlign: "center" }}>
          <div
            style={{
              width: 64,
              height: 64,
              margin: "0 auto",
              borderRadius: 32,
              background: "rgba(20,241,149,0.12)",
              border: "1px solid rgba(20,241,149,0.40)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 12px 40px rgba(20,241,149,0.25)",
              color: "var(--sol-teal)",
            }}
          >
            <Icon name="check" size={26} stroke={2.4} />
          </div>
          <div
            className="x-display"
            style={{
              fontSize: 22,
              marginTop: 18,
              letterSpacing: "-0.02em",
            }}
          >
            <span className="x-grad-text">{result.name}</span> is live
          </div>
          <div
            style={{
              fontSize: 12,
              color: "var(--tx-2)",
              marginTop: 8,
              fontFamily: "var(--font-mono)",
            }}
          >
            {formatUsdc(quote.total_to_escrow_usdc, 2)} USDC escrowed · campaign
            wallet {truncateAddress(result.wallet_address, 4)}
          </div>

          <div
            style={{
              marginTop: 22,
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 10,
            }}
          >
            <SuccessTx
              label="Funding tx"
              tx={result.tx_hash ?? null}
              url={result.tx_hash ? solscanTxUrl(result.tx_hash) : null}
            />
            <SuccessTx
              label="Protocol fee tx"
              tx={result.protocol_fee_tx_hash ?? null}
              url={result.protocol_fee_solscan_url ?? null}
            />
          </div>
        </div>
        <Footer
          left={
            <span
              style={{
                fontSize: 11,
                color: "var(--tx-2)",
                fontFamily: "var(--font-mono)",
              }}
            >
              publishers will start bidding within ~30s
            </span>
          }
          right={
            <button
              className="x-btn x-btn-primary"
              onClick={() => (onDone ? onDone(result) : onClose())}
            >
              Done
            </button>
          }
        />
      </>
    );
  }

  // Funding-in-progress view -----------------------------------------------
  if (submit.isPending && stage) {
    return <FundingProgress stage={stage} completed={completedStages} />;
  }

  // Review view (default) --------------------------------------------------
  return (
    <>
      <div style={{ padding: 22 }}>
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            gap: 12,
          }}
        >
          <Lbl>Campaign name</Lbl>
          <span
            style={{
              fontSize: 10,
              color: name.trim()
                ? "var(--sol-teal)"
                : "var(--st-expired)",
              fontFamily: "var(--font-mono)",
              letterSpacing: "0.06em",
              textTransform: "uppercase",
            }}
          >
            {name.trim() ? "✓ ready" : "Required"}
          </span>
        </div>
        <input
          className="x-input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          style={{
            marginTop: 6,
            borderColor:
              name.trim() || submit.isPending
                ? undefined
                : "rgba(255,122,69,0.45)",
          }}
          placeholder="e.g. Spring · launch"
          disabled={submit.isPending}
          autoFocus
        />

        <div
          className="x-card"
          style={{
            marginTop: 16,
            background: "var(--bg-2)",
            overflow: "hidden",
          }}
        >
          <ReviewRow
            label="Creative"
            value={
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  justifyContent: "flex-end",
                }}
              >
                {creative.preview_data_url ? (
                  <img
                    src={creative.preview_data_url}
                    alt=""
                    style={{
                      width: 36,
                      height: 20,
                      borderRadius: 4,
                      objectFit: "cover",
                    }}
                  />
                ) : (
                  <div
                    style={{
                      width: 36,
                      height: 20,
                      borderRadius: 4,
                      background: "var(--tint-grad-strong)",
                    }}
                  />
                )}
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 12,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    maxWidth: 220,
                  }}
                >
                  {creative.filename}
                </span>
              </div>
            }
          />
          <ReviewRow
            label="Markets"
            value={targeting.target_dmas.join(" · ")}
            sub={`${quote.screens.toLocaleString()} screens`}
          />
          <ReviewRow
            label="Schedule"
            value={`${schedule.start_date} → ${schedule.end_date}`}
            sub={`${quote.days} day${quote.days === 1 ? "" : "s"}`}
          />
          <ReviewRow
            label="Plays projected"
            value={quote.total_plays.toLocaleString()}
            mono
          />
          <ReviewRow
            label="CPM"
            value={`${formatUsdc(quote.cpm_price, 2)} USDC`}
            mono
          />
          <ReviewRow
            label={`Protocol fee · ${(quote.protocol_fee_pct * 100).toFixed(1)}%`}
            value={`${formatUsdc(quote.protocol_fee_usdc, 2)} USDC`}
            mono
            muted
          />
          <ReviewRow
            label="Total to escrow"
            value={`${formatUsdc(quote.total_to_escrow_usdc, 2)} USDC`}
            highlight
          />
        </div>

        <div
          style={{
            marginTop: 12,
            display: "flex",
            alignItems: "flex-start",
            gap: 10,
            padding: 12,
            borderRadius: 10,
            background: "rgba(61,90,254,0.06)",
            border: "1px solid rgba(61,90,254,0.20)",
          }}
        >
          <Icon name="info" size={14} stroke={1.8} />
          <div
            style={{
              fontSize: 11,
              color: "var(--tx-1)",
              lineHeight: 1.5,
            }}
          >
            We'll spin up a{" "}
            <span style={{ fontFamily: "var(--font-mono)" }}>
              fresh per-campaign Privy server wallet
            </span>
            , transfer escrow via x402, and skim the 2.5% protocol fee in the
            same flow.
          </div>
        </div>

        {insufficient && (
          <p
            style={{
              marginTop: 10,
              fontSize: 12,
              color: "var(--st-expired)",
              fontFamily: "var(--font-mono)",
            }}
          >
            Total to escrow {formatUsdc(quote.total_to_escrow_usdc, 2)} USDC
            exceeds your wallet balance of {formatUsdc(balanceMicro, 2)} USDC.
            Hit "Get test USDC" first.
          </p>
        )}
        {submit.isError && (
          <p
            style={{
              marginTop: 10,
              fontSize: 12,
              color: "var(--st-expired)",
              fontFamily: "var(--font-mono)",
            }}
          >
            {humanizeError(submit.error)}
          </p>
        )}
      </div>
      <Footer
        left={
          !name.trim() && !insufficient && !submit.isPending ? (
            <span
              style={{
                fontSize: 11,
                color: "var(--st-expired)",
                fontFamily: "var(--font-mono)",
              }}
            >
              Add a campaign name to continue
            </span>
          ) : null
        }
        right={
          <>
            <button
              className="x-btn"
              onClick={onBack}
              disabled={submit.isPending}
            >
              Back
            </button>
            <button
              className="x-btn x-btn-grad x-btn-lg"
              style={{ height: 40 }}
              disabled={!canSubmit}
              onClick={() => submit.mutate()}
            >
              <Icon name="check" size={12} stroke={2.4} /> Confirm &amp; Fund
            </button>
          </>
        }
      />
    </>
  );
}

function ReviewRow({
  label,
  value,
  sub,
  mono,
  muted,
  highlight,
}: {
  label: ReactNode;
  value: ReactNode;
  sub?: ReactNode;
  mono?: boolean;
  muted?: boolean;
  highlight?: boolean;
}) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "160px 1fr",
        gap: 16,
        padding: "12px 14px",
        borderTop: "1px solid var(--line-1)",
        background: highlight
          ? "linear-gradient(135deg, rgba(153,69,255,0.08), rgba(20,241,149,0.04))"
          : "transparent",
      }}
    >
      <span
        style={{
          fontSize: 11,
          color: "var(--tx-2)",
          fontFamily: "var(--font-mono)",
          textTransform: "uppercase",
          letterSpacing: "0.06em",
        }}
      >
        {label}
      </span>
      <div style={{ textAlign: "right" }}>
        <div
          className={mono ? "x-mono x-tnum" : "x-tnum"}
          style={{
            fontSize: highlight ? 16 : 13,
            fontWeight: highlight ? 600 : 500,
            color: muted ? "var(--tx-2)" : "var(--tx-0)",
          }}
        >
          {value}
        </div>
        {sub && (
          <div
            style={{
              fontSize: 11,
              color: "var(--tx-2)",
              fontFamily: "var(--font-mono)",
              marginTop: 2,
            }}
          >
            {sub}
          </div>
        )}
      </div>
    </div>
  );
}

function SuccessTx({
  label,
  tx,
  url,
}: {
  label: string;
  tx: string | null;
  url: string | null;
}) {
  return (
    <div
      className="x-card"
      style={{
        padding: "12px 14px",
        textAlign: "left",
        background: "var(--bg-2)",
      }}
    >
      <Lbl>{label}</Lbl>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginTop: 6,
        }}
      >
        <span className="x-mono" style={{ fontSize: 12 }}>
          {tx ? truncateAddress(tx, 4) : "—"}
        </span>
        {tx && url ? (
          <Solscan href={url}>view</Solscan>
        ) : (
          <span
            style={{
              fontSize: 11,
              color: "var(--tx-3)",
              fontFamily: "var(--font-mono)",
            }}
          >
            n/a
          </span>
        )}
      </div>
    </div>
  );
}

function FundingProgress({
  stage,
  completed,
}: {
  stage: FundStage;
  completed: Set<FundStage>;
}) {
  const steps: Array<{ id: FundStage; label: string; detail: string }> = [
    {
      id: "preparing",
      label: "Creating campaign wallet",
      detail: "Privy · server-side bootstrap + USDC ATA",
    },
    {
      id: "signing",
      label: "Signing x402 payment",
      detail: "Using Privy embedded wallet",
    },
    {
      id: "settling",
      label: "Settling on Solana",
      detail: "devnet RPC · facilitator co-sign",
    },
  ];

  return (
    <>
      <div style={{ padding: "40px 22px 28px" }}>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 8,
          }}
        >
          <div style={{ position: "relative", width: 64, height: 64 }}>
            <div
              style={{
                position: "absolute",
                inset: 0,
                borderRadius: 32,
                background: "var(--tint-grad-strong)",
                filter: "blur(20px)",
                opacity: 0.6,
              }}
            />
            <div
              style={{
                position: "relative",
                width: 64,
                height: 64,
                borderRadius: 32,
                background:
                  "conic-gradient(from 0deg, var(--sol-purple), var(--sol-teal), var(--sol-purple))",
                maskImage:
                  "radial-gradient(circle, transparent 26px, #000 27px)",
                WebkitMaskImage:
                  "radial-gradient(circle, transparent 26px, #000 27px)",
                animation: "fund-spin 1.4s linear infinite",
              }}
            />
            <style>{`@keyframes fund-spin{ to{ transform: rotate(360deg) } }`}</style>
          </div>
          <div className="x-display" style={{ fontSize: 18, marginTop: 6 }}>
            Funding campaign
          </div>
        </div>

        <div
          style={{
            marginTop: 24,
            display: "flex",
            flexDirection: "column",
            gap: 4,
          }}
        >
          {steps.map((s) => {
            const done = completed.has(s.id);
            const cur = stage === s.id;
            return (
              <div
                key={s.id}
                style={{
                  padding: "12px 14px",
                  borderRadius: 10,
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  background: cur ? "var(--bg-2)" : "transparent",
                  border: `1px solid ${cur ? "var(--line-2)" : "transparent"}`,
                }}
              >
                <div
                  style={{
                    width: 22,
                    height: 22,
                    borderRadius: 11,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    background: done
                      ? "var(--sol-teal)"
                      : cur
                        ? "transparent"
                        : "var(--bg-3)",
                    border: cur ? "2px solid var(--sol-purple)" : "none",
                    color: "#08070A",
                  }}
                >
                  {done ? (
                    <Icon name="check" size={12} stroke={3} />
                  ) : cur ? (
                    <span
                      style={{
                        width: 6,
                        height: 6,
                        borderRadius: 3,
                        background: "var(--sol-purple)",
                      }}
                    />
                  ) : null}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      fontSize: 13,
                      color: cur
                        ? "var(--tx-0)"
                        : done
                          ? "var(--tx-1)"
                          : "var(--tx-3)",
                      fontWeight: cur ? 600 : 500,
                    }}
                  >
                    {s.label}
                  </div>
                  <div
                    style={{
                      fontSize: 11,
                      color: "var(--tx-2)",
                      fontFamily: "var(--font-mono)",
                      marginTop: 2,
                    }}
                  >
                    {s.detail}
                  </div>
                </div>
                {cur && (
                  <span
                    style={{
                      fontSize: 11,
                      color: "var(--sol-teal)",
                      fontFamily: "var(--font-mono)",
                    }}
                  >
                    pending…
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>
      <Footer
        left={
          <span
            style={{
              fontSize: 11,
              color: "var(--tx-2)",
              fontFamily: "var(--font-mono)",
            }}
          >
            do not close this window
          </span>
        }
        right={
          <button
            className="x-btn"
            disabled
            style={{ opacity: 0.5, pointerEvents: "none" }}
          >
            Cancel
          </button>
        }
      />
    </>
  );
}
