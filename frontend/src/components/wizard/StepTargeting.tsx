import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useApi } from "../../lib/api";
import { humanizeError } from "../../lib/errors";

type Market = { dma: string; display_count: number };

export type TargetingSelection = {
  target_dmas: string[];
};

type Props = {
  initial: TargetingSelection | null;
  onBack: () => void;
  onComplete: (selection: TargetingSelection) => void;
};

// Hardcoded for the demo — every screen plays the campaign once every 5
// minutes when eligible. Kept as a literal so the calculator step (Session 15)
// can compute plays/day from the same constant.
const FREQUENCY_LABEL = "Frequency per screen: 1 every 5 min";

export default function StepTargeting({ initial, onBack, onComplete }: Props) {
  const api = useApi();
  const markets = useQuery<Market[]>({
    queryKey: ["markets"],
    queryFn: async () => {
      const r = await api.get<Market[]>("/api/markets");
      return r.data;
    },
    staleTime: 5 * 60 * 1000,
  });

  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(initial?.target_dmas ?? []),
  );

  function toggle(dma: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(dma)) next.delete(dma);
      else next.add(dma);
      return next;
    });
  }

  const reach = (markets.data ?? [])
    .filter((m) => selected.has(m.dma))
    .reduce((sum, m) => sum + m.display_count, 0);

  const canContinue = selected.size >= 1;

  return (
    <div>
      <h3>Target markets</h3>
      <p className="muted footnote">
        Select one or more DMAs. The campaign only bids when an impression
        request comes from a screen in a selected market.
      </p>

      {markets.isLoading && <p className="muted footnote">Loading inventory…</p>}
      {markets.isError && <p className="error">{humanizeError(markets.error)}</p>}

      {markets.data && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
            gap: "0.5rem",
            marginTop: "0.75rem",
          }}
        >
          {markets.data.map((m) => {
            const active = selected.has(m.dma);
            return (
              <button
                key={m.dma}
                type="button"
                onClick={() => toggle(m.dma)}
                style={{
                  padding: "0.75rem",
                  borderRadius: 8,
                  border: active
                    ? "1px solid var(--accent, #6366f1)"
                    : "1px solid var(--border)",
                  background: active
                    ? "rgba(99,102,241,0.12)"
                    : "rgba(255,255,255,0.02)",
                  textAlign: "left",
                  cursor: "pointer",
                  color: "var(--text)",
                }}
              >
                <div style={{ fontWeight: 600 }}>{m.dma}</div>
                <div className="muted footnote" style={{ marginTop: "0.25rem" }}>
                  {m.display_count.toLocaleString()} screens
                </div>
              </button>
            );
          })}
        </div>
      )}

      <div
        style={{
          marginTop: "1rem",
          padding: "0.75rem",
          borderRadius: 8,
          border: "1px solid var(--border)",
          background: "rgba(255,255,255,0.03)",
        }}
      >
        <div style={{ fontSize: "1.1rem" }}>
          <strong>REACH:</strong> {reach.toLocaleString()} screens
        </div>
        <div className="muted footnote" style={{ marginTop: "0.25rem" }}>
          {FREQUENCY_LABEL}
        </div>
      </div>

      <div className="actions" style={{ marginTop: "1rem" }}>
        <button type="button" className="secondary" onClick={onBack}>
          Back
        </button>
        <button
          type="button"
          disabled={!canContinue}
          onClick={() => onComplete({ target_dmas: Array.from(selected) })}
        >
          Next
        </button>
        {!canContinue && (
          <span className="muted footnote">Select at least one market.</span>
        )}
      </div>
    </div>
  );
}
