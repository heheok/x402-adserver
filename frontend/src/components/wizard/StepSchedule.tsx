import { useMemo, useRef, useState } from "react";

import Icon from "../ui/Icon";
import { Footer, Lbl } from "./Modal";

export type ScheduleWindow = {
  start_date: string;
  end_date: string;
};

type Props = {
  initial: ScheduleWindow | null;
  onBack: () => void;
  onComplete: (schedule: ScheduleWindow) => void;
};

function todayIso(): string {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function addDays(iso: string, days: number): string {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + days);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

function fmt(iso: string): { label: string; weekday: string } {
  const d = new Date(iso + "T00:00:00");
  if (Number.isNaN(d.getTime())) return { label: iso, weekday: "" };
  return {
    label: `${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`,
    weekday: WEEKDAYS[d.getDay()],
  };
}

export default function StepSchedule({ initial, onBack, onComplete }: Props) {
  const today = useMemo(todayIso, []);
  const [start, setStart] = useState<string>(initial?.start_date ?? today);
  const [end, setEnd] = useState<string>(
    initial?.end_date ?? addDays(today, 2),
  );

  const startInPast = start < today;
  const endBeforeStart = end < start;
  const valid = !startInPast && !endBeforeStart;

  const days =
    Math.max(
      0,
      Math.round(
        (new Date(end + "T00:00:00").getTime() -
          new Date(start + "T00:00:00").getTime()) /
          86400000,
      ),
    ) + 1;

  return (
    <>
      <div style={{ padding: 22 }}>
        <Lbl>Schedule</Lbl>
        <div style={{ marginTop: 6, fontSize: 12, color: "var(--tx-2)" }}>
          Plays start at 00:00 UTC on the start date and stop at 00:00 UTC the
          day after the end date.
        </div>

        <div
          className="x-sched-grid"
          style={{
            marginTop: 14,
            display: "grid",
            gridTemplateColumns: "1fr 24px 1fr",
            alignItems: "center",
            gap: 14,
          }}
        >
          <DateField
            label="Start date"
            value={start}
            min={today}
            onChange={setStart}
          />
          <span className="x-sched-arrow" style={{ display: "inline-flex" }}>
            <Icon name="arrowRight" size={14} />
          </span>
          <DateField
            label="End date"
            value={end}
            min={start}
            onChange={setEnd}
          />
        </div>

        <div
          style={{
            marginTop: 14,
            padding: "12px 14px",
            borderRadius: 10,
            background: "var(--bg-2)",
            border: "1px solid var(--line-1)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div style={{ fontSize: 12, color: "var(--tx-1)" }}>Duration</div>
          <div
            className="x-mono"
            style={{ fontSize: 13, fontWeight: 500 }}
          >
            {valid ? `${days} day${days === 1 ? "" : "s"}` : "—"}
          </div>
        </div>

        {startInPast && (
          <p
            style={{
              marginTop: 10,
              fontSize: 12,
              color: "var(--st-expired)",
              fontFamily: "var(--font-mono)",
            }}
          >
            Start date can't be in the past.
          </p>
        )}
        {endBeforeStart && (
          <p
            style={{
              marginTop: 10,
              fontSize: 12,
              color: "var(--st-expired)",
              fontFamily: "var(--font-mono)",
            }}
          >
            End date must be on or after start date.
          </p>
        )}
        {valid && (
          <div
            style={{
              marginTop: 10,
              display: "flex",
              alignItems: "center",
              gap: 8,
              fontSize: 11,
              color: "var(--sol-teal)",
              fontFamily: "var(--font-mono)",
            }}
          >
            <Icon name="check" size={11} stroke={2.4} /> Schedule valid
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
              disabled={!valid}
              onClick={() =>
                onComplete({ start_date: start, end_date: end })
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

function DateField({
  label,
  value,
  min,
  onChange,
}: {
  label: string;
  value: string;
  min: string;
  onChange: (v: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const { label: pretty, weekday } = fmt(value);

  function openPicker() {
    const el = inputRef.current;
    if (!el) return;
    // Chrome/Firefox/Safari ≥ 16 expose showPicker(); fall back to focus +
    // click for older engines. Wrapping in try/catch because some browsers
    // throw when called without user activation in edge contexts.
    try {
      if (typeof el.showPicker === "function") {
        el.showPicker();
        return;
      }
    } catch {
      /* fallthrough — picker call may throw without user activation */
    }
    el.focus();
    el.click();
  }

  return (
    <div>
      <Lbl>{label}</Lbl>
      <button
        type="button"
        onClick={openPicker}
        style={{
          marginTop: 6,
          padding: "12px 14px",
          borderRadius: 10,
          border: "1px solid var(--line-2)",
          background: "var(--bg-2)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          cursor: "pointer",
          width: "100%",
          color: "var(--tx-0)",
          font: "inherit",
          textAlign: "left",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column" }}>
          <span style={{ fontSize: 14, fontWeight: 500 }}>{pretty}</span>
          <span
            style={{
              fontSize: 10,
              color: "var(--tx-2)",
              fontFamily: "var(--font-mono)",
            }}
          >
            {weekday}
          </span>
        </div>
        <Icon name="calendar" size={14} stroke={1.6} />
      </button>
      {/* Off-screen native input. We open it programmatically via showPicker()
          so the styled button stays fully interactive. */}
      <input
        ref={inputRef}
        type="date"
        value={value}
        min={min}
        onChange={(e) => onChange(e.target.value)}
        style={{
          position: "absolute",
          width: 1,
          height: 1,
          padding: 0,
          margin: -1,
          overflow: "hidden",
          clip: "rect(0,0,0,0)",
          whiteSpace: "nowrap",
          border: 0,
        }}
        aria-hidden="true"
        tabIndex={-1}
      />
    </div>
  );
}
