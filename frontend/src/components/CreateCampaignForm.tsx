import { useState } from "react";

import StepDetails, { type CreatedCampaign } from "./wizard/StepDetails";
import StepImage, { type CreativeAsset } from "./wizard/StepImage";

type Props = {
  onCreated?: (campaign: CreatedCampaign) => void;
};

// Sessions 14 + 15 will insert "targeting", "schedule", "calculator" between
// "image" and "details" and rename "details" to "review".
type StepKey = "image" | "details";

const STEPS: { key: StepKey; label: string }[] = [
  { key: "image", label: "Creative" },
  { key: "details", label: "Details & Fund" },
];

export default function CreateCampaignForm({ onCreated }: Props = {}) {
  const [creative, setCreative] = useState<CreativeAsset | null>(null);
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
            setStep("details");
          }}
        />
      )}

      {step === "details" && creative && (
        <StepDetails
          creative={creative}
          onBack={() => setStep("image")}
          onCreated={onCreated}
        />
      )}
    </div>
  );
}
