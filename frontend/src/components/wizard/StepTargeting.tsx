import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useApi } from "../../lib/api";
import { humanizeError } from "../../lib/errors";
import Icon from "../ui/Icon";
import { Footer, Lbl } from "./Modal";

type Market = { dma: string; display_count: number };

export type TargetingSelection = {
  target_dmas: string[];
};

type Props = {
  initial: TargetingSelection | null;
  onBack: () => void;
  onComplete: (selection: TargetingSelection) => void;
};

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
  const totalMarkets = markets.data?.length ?? 0;

  return (
    <>
      <div style={{ padding: 22 }}>
        <Lbl>Pick markets (DMAs)</Lbl>
        <div style={{ marginTop: 6, fontSize: 12, color: "var(--tx-2)" }}>
          The campaign only bids when an impression comes from a screen in a
          selected market.
        </div>

        {markets.isLoading && (
          <p
            style={{
              marginTop: 12,
              fontSize: 12,
              color: "var(--tx-2)",
              fontFamily: "var(--font-mono)",
            }}
          >
            loading inventory…
          </p>
        )}
        {markets.isError && (
          <p
            style={{
              marginTop: 12,
              fontSize: 12,
              color: "var(--st-expired)",
              fontFamily: "var(--font-mono)",
            }}
          >
            {humanizeError(markets.error)}
          </p>
        )}

        {markets.data && (
          <div
            className="x-grid-sm-2"
            style={{
              marginTop: 14,
              display: "grid",
              gridTemplateColumns: "repeat(3, 1fr)",
              gap: 10,
            }}
          >
            {markets.data.map((m) => {
              const sel = selected.has(m.dma);
              return (
                <button
                  key={m.dma}
                  type="button"
                  onClick={() => toggle(m.dma)}
                  style={{
                    padding: 14,
                    borderRadius: 12,
                    background: sel
                      ? "rgba(20,241,149,0.06)"
                      : "var(--bg-2)",
                    border: `1px solid ${sel ? "rgba(20,241,149,0.30)" : "var(--line-1)"}`,
                    cursor: "pointer",
                    textAlign: "left",
                    color: "var(--tx-0)",
                    font: "inherit",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "flex-start",
                    }}
                  >
                    <div style={{ fontSize: 13, fontWeight: 600 }}>
                      {m.dma}
                    </div>
                    <div
                      style={{
                        width: 16,
                        height: 16,
                        borderRadius: 4,
                        border: `1px solid ${sel ? "var(--sol-teal)" : "var(--line-2)"}`,
                        background: sel ? "var(--sol-teal)" : "transparent",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        color: "#08070A",
                      }}
                    >
                      {sel && <Icon name="check" size={10} stroke={3} />}
                    </div>
                  </div>
                  <div
                    className="x-mono x-tnum"
                    style={{
                      fontSize: 16,
                      marginTop: 6,
                      color: sel ? "var(--tx-0)" : "var(--tx-1)",
                    }}
                  >
                    {m.display_count.toLocaleString()}
                  </div>
                  <div
                    style={{
                      fontSize: 10,
                      color: "var(--tx-2)",
                      fontFamily: "var(--font-mono)",
                    }}
                  >
                    screens
                  </div>
                </button>
              );
            })}
          </div>
        )}

        <div
          style={{
            marginTop: 16,
            padding: "12px 14px",
            borderRadius: 10,
            background: "var(--bg-2)",
            border: "1px solid var(--line-1)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div>
            <div
              style={{
                fontSize: 11,
                color: "var(--tx-2)",
                fontFamily: "var(--font-mono)",
              }}
            >
              REACH
            </div>
            <div
              className="x-display x-tnum"
              style={{ fontSize: 22, marginTop: 2 }}
            >
              {reach.toLocaleString()}{" "}
              <span style={{ fontSize: 12, color: "var(--tx-2)" }}>
                screens
              </span>
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div
              style={{
                fontSize: 11,
                color: "var(--tx-2)",
                fontFamily: "var(--font-mono)",
              }}
            >
              FREQUENCY
            </div>
            <div
              style={{
                fontSize: 13,
                marginTop: 4,
                fontFamily: "var(--font-mono)",
              }}
            >
              1 play every 5 min
            </div>
          </div>
        </div>
      </div>

      <Footer
        left={
          totalMarkets > 0 ? (
            <span
              style={{
                fontSize: 11,
                color: "var(--tx-2)",
                fontFamily: "var(--font-mono)",
              }}
            >
              {selected.size} of {totalMarkets} markets selected
            </span>
          ) : null
        }
        right={
          <>
            <button className="x-btn" onClick={onBack}>
              Back
            </button>
            <button
              className="x-btn x-btn-primary"
              disabled={!canContinue}
              onClick={() =>
                onComplete({ target_dmas: Array.from(selected) })
              }
            >
              Next <Icon name="arrowRight" size={12} stroke={2} />
            </button>
          </>
        }
      />
    </>
  );
}
