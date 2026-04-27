export type CampaignStatus =
  | "draft"
  | "active"
  | "paused"
  | "completed"
  | "expired"
  | "refunded";

const LABELS: Record<CampaignStatus, string> = {
  draft: "Draft",
  active: "Active",
  paused: "Paused",
  completed: "Completed",
  expired: "Expired",
  refunded: "Refunded",
};

type Props = { status: string };

export default function StatusBadge({ status }: Props) {
  const known = (LABELS as Record<string, string>)[status];
  return (
    <span className={`x-badge x-badge-${status}`}>
      <span className="dot" />
      {known ?? status}
    </span>
  );
}
