import Icon from "./ui/Icon";

export type TabId = "overview" | "campaigns";

type Props = {
  tab: TabId;
  onTabChange: (tab: TabId) => void;
  onNewCampaign: () => void;
};

const TABS: Array<{ id: TabId; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "campaigns", label: "Campaigns" },
];

export default function TabRow({ tab, onTabChange, onNewCampaign }: Props) {
  return (
    <div
      className="x-bar-pad"
      style={{
        height: 56,
        padding: "0 28px",
        display: "flex",
        alignItems: "center",
        gap: 4,
        borderBottom: "1px solid var(--line-1)",
        background: "var(--bg-0)",
      }}
    >
      {TABS.map((t) => (
        <button
          key={t.id}
          onClick={() => onTabChange(t.id)}
          style={{
            height: 56,
            padding: "0 14px",
            border: 0,
            background: "transparent",
            color: tab === t.id ? "var(--tx-0)" : "var(--tx-2)",
            fontWeight: tab === t.id ? 600 : 500,
            fontSize: 14,
            cursor: "pointer",
            borderBottom: "2px solid",
            borderBottomColor: tab === t.id ? "var(--tx-0)" : "transparent",
            marginBottom: -1,
            letterSpacing: "-0.005em",
          }}
        >
          {t.label}
        </button>
      ))}
      <div style={{ flex: 1 }} />
      <button className="x-btn x-btn-primary x-btn-sm" onClick={onNewCampaign}>
        <Icon name="plus" size={12} stroke={2} /> New campaign
      </button>
    </div>
  );
}
