import { useQuery } from "@tanstack/react-query";

import { useApi } from "../../lib/api";
import { humanizeError } from "../../lib/errors";
import type { ScheduleWindow } from "./StepSchedule";
import type { TargetingSelection } from "./StepTargeting";

export type Quote = {
  screens: number;
  plays_per_screen_per_day: number;
  days: number;
  total_plays: number;
  cpm_price: number;
  total_usdc: number;
  protocol_fee_pct: number;
  protocol_fee_usdc: number;
  total_to_escrow_usdc: number;
};

type Props = {
  targeting: TargetingSelection;
  schedule: ScheduleWindow;
  onBack: () => void;
  onComplete: (quote: Quote) => void;
};

function fmtUsdc(n: number): string {
  // 4 dp is the practical demo precision. USDC's full 6 dp is overkill on
  // this many digits.
  return n.toFixed(4);
}

export default function StepCalculator({
  targeting,
  schedule,
  onBack,
  onComplete,
}: Props) {
  const api = useApi();

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

  const q = quote.data;

  return (
    <div>
      <h3>Budget</h3>
      <p className="muted footnote">
        Server-derived from your selections. CPM is locked at the demo rate; the
        protocol fee is a flat 2.5% of campaign total.
      </p>

      {quote.isLoading && <p className="muted footnote">Computing quote…</p>}
      {quote.isError && <p className="error">{humanizeError(quote.error)}</p>}

      {q && (
        <div
          style={{
            marginTop: "0.75rem",
            border: "1px solid var(--border)",
            borderRadius: 8,
            background: "rgba(255,255,255,0.03)",
            padding: "0.75rem",
            display: "grid",
            gridTemplateColumns: "auto 1fr",
            rowGap: "0.4rem",
            columnGap: "1rem",
          }}
        >
          <span className="muted">Screens</span>
          <span>{q.screens.toLocaleString()}</span>

          <span className="muted">Frequency / screen / day</span>
          <span>
            {q.plays_per_screen_per_day} plays (1 every 5 min, 12 h/day)
          </span>

          <span className="muted">Duration</span>
          <span>
            {q.days} day{q.days === 1 ? "" : "s"}
          </span>

          <span className="muted">Total plays</span>
          <span>{q.total_plays.toLocaleString()}</span>

          <span className="muted">CPM (locked)</span>
          <span>{fmtUsdc(q.cpm_price)} USDC</span>

          <span className="muted">Campaign total</span>
          <span>{fmtUsdc(q.total_usdc)} USDC</span>

          <span className="muted">
            Protocol fee ({(q.protocol_fee_pct * 100).toFixed(1)}%)
          </span>
          <span>{fmtUsdc(q.protocol_fee_usdc)} USDC</span>

          <span style={{ fontWeight: 600 }}>Total to escrow</span>
          <span style={{ fontWeight: 600 }}>
            {fmtUsdc(q.total_to_escrow_usdc)} USDC
          </span>
        </div>
      )}

      <div className="actions" style={{ marginTop: "1rem" }}>
        <button type="button" className="secondary" onClick={onBack}>
          Back
        </button>
        <button
          type="button"
          disabled={!q || quote.isError}
          onClick={() => q && onComplete(q)}
        >
          Next
        </button>
      </div>
    </div>
  );
}
