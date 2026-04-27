import { useState } from "react";

import StepCalculator, { type Quote } from "./wizard/StepCalculator";
import StepImage, { type CreativeAsset } from "./wizard/StepImage";
import StepReview, { type CreatedCampaign } from "./wizard/StepReview";
import StepSchedule, { type ScheduleWindow } from "./wizard/StepSchedule";
import StepTargeting, { type TargetingSelection } from "./wizard/StepTargeting";

type Props = {
  onCreated?: (campaign: CreatedCampaign) => void;
};

type StepKey = "image" | "targeting" | "schedule" | "calculator" | "review";

const STEPS: { key: StepKey; label: string }[] = [
  { key: "image", label: "Creative" },
  { key: "targeting", label: "Targeting" },
  { key: "schedule", label: "Schedule" },
  { key: "calculator", label: "Budget" },
  { key: "review", label: "Review & Fund" },
];

export default function CreateCampaignForm({ onCreated }: Props = {}) {
  const [creative, setCreative] = useState<CreativeAsset | null>(null);
  const [targeting, setTargeting] = useState<TargetingSelection | null>(null);
  const [schedule, setSchedule] = useState<ScheduleWindow | null>(null);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [step, setStep] = useState<StepKey>("image");

  const currentIndex = STEPS.findIndex((s) => s.key === step);

  return (
    <div className="subform">
      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          alignItems: "center",
          marginBottom: "0.75rem",
          fontSize: "0.85rem",
          color: "var(--muted)",
          flexWrap: "wrap",
        }}
      >
        {STEPS.map((s, i) => (
          <span
            key={s.key}
            style={{
              color: i === currentIndex ? "var(--text)" : "var(--muted)",
              fontWeight: i === currentIndex ? 600 : 400,
            }}
          >
            {i + 1}. {s.label}
            {i < STEPS.length - 1 ? "  →" : ""}
          </span>
        ))}
      </div>

      {step === "image" && (
        <StepImage
          initial={creative}
          onComplete={(asset) => {
            setCreative(asset);
            setStep("targeting");
          }}
        />
      )}

      {step === "targeting" && (
        <StepTargeting
          initial={targeting}
          onBack={() => setStep("image")}
          onComplete={(sel) => {
            setTargeting(sel);
            setStep("schedule");
          }}
        />
      )}

      {step === "schedule" && (
        <StepSchedule
          initial={schedule}
          onBack={() => setStep("targeting")}
          onComplete={(sch) => {
            setSchedule(sch);
            setStep("calculator");
          }}
        />
      )}

      {step === "calculator" && targeting && schedule && (
        <StepCalculator
          targeting={targeting}
          schedule={schedule}
          onBack={() => setStep("schedule")}
          onComplete={(q) => {
            setQuote(q);
            setStep("review");
          }}
        />
      )}

      {step === "review" && creative && targeting && schedule && quote && (
        <StepReview
          creative={creative}
          targeting={targeting}
          schedule={schedule}
          quote={quote}
          onBack={() => setStep("calculator")}
          onCreated={onCreated}
        />
      )}
    </div>
  );
}
