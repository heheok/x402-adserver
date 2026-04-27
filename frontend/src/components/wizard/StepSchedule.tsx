import { useMemo, useState } from "react";

export type ScheduleWindow = {
  start_date: string; // ISO YYYY-MM-DD
  end_date: string;
};

type Props = {
  initial: ScheduleWindow | null;
  onBack: () => void;
  onComplete: (schedule: ScheduleWindow) => void;
};

function todayIso(): string {
  // Use the local date — matches the date input's default semantics. The
  // backend re-validates against UTC today, so a midnight-edge mismatch can
  // surface as a 422 — accept that for the demo's single-tz setup.
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

export default function StepSchedule({ initial, onBack, onComplete }: Props) {
  const today = useMemo(todayIso, []);
  const [start, setStart] = useState<string>(initial?.start_date ?? today);
  const [end, setEnd] = useState<string>(
    initial?.end_date ?? addDays(today, 2),
  );

  const startInPast = start < today;
  const endBeforeStart = end < start;
  const valid = !startInPast && !endBeforeStart;

  // Inclusive day count.
  const days =
    Math.max(
      0,
      Math.round(
        (new Date(end + "T00:00:00").getTime() -
          new Date(start + "T00:00:00").getTime()) /
          (1000 * 60 * 60 * 24),
      ),
    ) + 1;

  return (
    <div>
      <h3>Schedule</h3>
      <p className="muted footnote">
        Campaign runs from start to end (inclusive). Bids are blocked outside
        the window; an expired campaign can be refunded.
      </p>

      <div className="form" style={{ marginTop: "0.75rem" }}>
        <div className="row">
          <label>
            <span>Start date</span>
            <input
              type="date"
              value={start}
              min={today}
              onChange={(e) => setStart(e.target.value)}
              required
            />
          </label>

          <label>
            <span>End date</span>
            <input
              type="date"
              value={end}
              min={start}
              onChange={(e) => setEnd(e.target.value)}
              required
            />
          </label>
        </div>

        {startInPast && <p className="error">Start date can't be in the past.</p>}
        {endBeforeStart && (
          <p className="error">End date must be on or after start date.</p>
        )}

        {valid && (
          <p className="muted footnote">
            Duration: {days} day{days === 1 ? "" : "s"}.
          </p>
        )}
      </div>

      <div className="actions" style={{ marginTop: "1rem" }}>
        <button type="button" className="secondary" onClick={onBack}>
          Back
        </button>
        <button
          type="button"
          disabled={!valid}
          onClick={() =>
            onComplete({ start_date: start, end_date: end })
          }
        >
          Next
        </button>
      </div>
    </div>
  );
}
