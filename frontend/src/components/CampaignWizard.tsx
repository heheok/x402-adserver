import { useState } from "react";

import Modal, { type StepId } from "./wizard/Modal";
import StepCalculator, { type Quote } from "./wizard/StepCalculator";
import StepImage, { type CreativeAsset } from "./wizard/StepImage";
import StepReview, { type CreatedCampaign } from "./wizard/StepReview";
import StepSchedule, { type ScheduleWindow } from "./wizard/StepSchedule";
import StepTargeting, { type TargetingSelection } from "./wizard/StepTargeting";

type Props = {
  onClose: () => void;
  onCreated?: (campaign: CreatedCampaign) => void;
  /** Fires when the user clicks "Done" on the success state. Use to navigate
   *  the user to the new campaign and close the wizard. */
  onDone?: (campaign: CreatedCampaign) => void;
};

export default function CampaignWizard({
  onClose,
  onCreated,
  onDone,
}: Props) {
  const [step, setStep] = useState<StepId>(1);
  const [creative, setCreative] = useState<CreativeAsset | null>(null);
  const [targeting, setTargeting] = useState<TargetingSelection | null>(null);
  const [schedule, setSchedule] = useState<ScheduleWindow | null>(null);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [funding, setFunding] = useState(false);

  function attemptClose() {
    if (funding) return; // mid-flow, don't allow.
    const midFlow =
      creative !== null || targeting !== null || schedule !== null;
    if (midFlow) {
      const ok = window.confirm(
        "Discard this campaign? Your selections won't be saved.",
      );
      if (!ok) return;
    }
    onClose();
  }

  // Funding state disables the back chevron in the modal header.
  const onBack =
    step > 1 && !funding
      ? () => setStep((step - 1) as StepId)
      : undefined;

  return (
    <Modal
      step={step}
      onBack={onBack}
      onClose={attemptClose}
      closeDisabled={funding}
    >
      {step === 1 && (
        <StepImage
          initial={creative}
          onComplete={(asset) => {
            setCreative(asset);
            setStep(2);
          }}
        />
      )}
      {step === 2 && (
        <StepTargeting
          initial={targeting}
          onBack={() => setStep(1)}
          onComplete={(sel) => {
            setTargeting(sel);
            setStep(3);
          }}
        />
      )}
      {step === 3 && (
        <StepSchedule
          initial={schedule}
          onBack={() => setStep(2)}
          onComplete={(sch) => {
            setSchedule(sch);
            setStep(4);
          }}
        />
      )}
      {step === 4 && targeting && schedule && (
        <StepCalculator
          targeting={targeting}
          schedule={schedule}
          onBack={() => setStep(3)}
          onComplete={(q) => {
            setQuote(q);
            setStep(5);
          }}
        />
      )}
      {step === 5 && creative && targeting && schedule && quote && (
        <StepReview
          creative={creative}
          targeting={targeting}
          schedule={schedule}
          quote={quote}
          onBack={() => setStep(4)}
          onCreated={onCreated}
          onClose={onClose}
          onDone={onDone}
          onFundingStateChange={setFunding}
        />
      )}
    </Modal>
  );
}
