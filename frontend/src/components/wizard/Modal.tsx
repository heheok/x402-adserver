import type { ReactNode } from "react";
import { useEffect } from "react";

import Icon from "../ui/Icon";

export const STEPS = [
  { id: 1, label: "Creative" },
  { id: 2, label: "Targeting" },
  { id: 3, label: "Schedule" },
  { id: 4, label: "Budget" },
  { id: 5, label: "Review" },
] as const;

export type StepId = 1 | 2 | 3 | 4 | 5;

type Props = {
  step: StepId;
  title?: string;
  onBack?: () => void;
  onClose: () => void;
  /** Disable the close button (e.g. while funding is in progress). */
  closeDisabled?: boolean;
  children: ReactNode;
};

export default function Modal({
  step,
  title = "New campaign",
  onBack,
  onClose,
  closeDisabled = false,
  children,
}: Props) {
  // ESC dismisses (unless closing is disabled mid-flow).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !closeDisabled) {
        onClose();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, closeDisabled]);

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(4,5,9,0.66)",
        backdropFilter: "blur(6px)",
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "center",
        padding: "60px 16px",
        zIndex: 100,
        overflow: "auto",
      }}
      onClick={(e) => {
        // Click on the dim background (not the card) closes — except mid-flow.
        if (e.target === e.currentTarget && !closeDisabled) onClose();
      }}
    >
      <div
        className="x-card"
        style={{
          width: "100%",
          maxWidth: 640,
          background: "var(--bg-1)",
          boxShadow: "var(--shadow-card)",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            padding: "20px 22px 16px",
            borderBottom: "1px solid var(--line-1)",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              {onBack && (
                <button
                  className="x-btn x-btn-sm"
                  style={{ width: 28, padding: 0 }}
                  onClick={onBack}
                  aria-label="Back"
                >
                  <Icon name="chevronLeft" size={11} stroke={2} />
                </button>
              )}
              <div>
                <div className="x-display" style={{ fontSize: 16 }}>
                  {title}
                </div>
                <div
                  style={{
                    fontSize: 11,
                    color: "var(--tx-2)",
                    fontFamily: "var(--font-mono)",
                    marginTop: 2,
                  }}
                >
                  step {step} of 5
                </div>
              </div>
            </div>
            <button
              onClick={() => !closeDisabled && onClose()}
              disabled={closeDisabled}
              aria-label="Close"
              style={{
                width: 28,
                height: 28,
                border: 0,
                background: "transparent",
                color: "var(--tx-2)",
                cursor: closeDisabled ? "not-allowed" : "pointer",
                borderRadius: 6,
                opacity: closeDisabled ? 0.4 : 1,
              }}
            >
              <Icon name="close" size={14} stroke={1.8} />
            </button>
          </div>
          <div style={{ marginTop: 18 }}>
            <StepDots current={step} />
          </div>
        </div>
        {children}
      </div>
    </div>
  );
}

function StepDots({ current }: { current: StepId }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 0,
        padding: "0 4px",
      }}
    >
      {STEPS.map((s, i) => {
        const done = current > s.id;
        const active = current === s.id;
        return (
          <span
            key={s.id}
            style={{ display: "contents" }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div
                style={{
                  width: 22,
                  height: 22,
                  borderRadius: 11,
                  fontSize: 11,
                  fontWeight: 600,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontFamily: "var(--font-mono)",
                  background: done
                    ? "var(--tint-grad-strong)"
                    : active
                      ? "var(--bg-3)"
                      : "transparent",
                  color: done
                    ? "#08070A"
                    : active
                      ? "var(--tx-0)"
                      : "var(--tx-3)",
                  border: active
                    ? "1px solid var(--line-3)"
                    : done
                      ? "none"
                      : "1px solid var(--line-1)",
                }}
              >
                {done ? <Icon name="check" size={11} stroke={2.4} /> : s.id}
              </div>
              <span
                style={{
                  fontSize: 11,
                  color: active ? "var(--tx-0)" : "var(--tx-2)",
                  fontWeight: active ? 600 : 500,
                  letterSpacing: "-0.005em",
                }}
              >
                {s.label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div
                style={{
                  flex: 1,
                  height: 1,
                  background: done
                    ? "var(--tint-grad-strong)"
                    : "var(--line-1)",
                  margin: "0 12px",
                }}
              />
            )}
          </span>
        );
      })}
    </div>
  );
}

export function Footer({
  left,
  right,
}: {
  left?: ReactNode;
  right?: ReactNode;
}) {
  return (
    <div
      style={{
        padding: "16px 22px",
        borderTop: "1px solid var(--line-1)",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        background: "var(--bg-1)",
        gap: 16,
      }}
    >
      <div style={{ minWidth: 0 }}>{left}</div>
      <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>{right}</div>
    </div>
  );
}

export function Lbl({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        fontSize: 11,
        color: "var(--tx-2)",
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        fontFamily: "var(--font-mono)",
      }}
    >
      {children}
    </div>
  );
}
