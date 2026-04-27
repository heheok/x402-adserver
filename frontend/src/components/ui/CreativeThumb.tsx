// Deterministic gradient seeded by an arbitrary string (typically campaign.id).
// We don't have brand metadata on campaigns, so we hash the id into a
// hue-pair and render a small Solana-flavored gradient block. Same id =>
// same colors across renders.

const PALETTES: Array<[string, string]> = [
  ["#9945FF", "#14F195"],
  ["#3D5AFE", "#00C2FF"],
  ["#F69100", "#FFD089"],
  ["#E33E7F", "#FF8FB3"],
  ["#11D5C0", "#9945FF"],
  ["#534BB1", "#AB9FF2"],
  ["#F03A47", "#FF7A45"],
  ["#E42575", "#9945FF"],
];

function pickPalette(seed: string): [string, string] {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = (hash * 31 + seed.charCodeAt(i)) | 0;
  }
  const idx = Math.abs(hash) % PALETTES.length;
  return PALETTES[idx];
}

type Props = {
  seed: string;
  size?: number;
  label?: string;
};

export default function CreativeThumb({ seed, size = 40, label }: Props) {
  const [a, b] = pickPalette(seed || "x402");
  const initial = label?.[0] || (seed[0] ?? "·").toUpperCase();
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: 8,
        background: `linear-gradient(135deg, ${a}, ${b})`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: "#fff",
        fontWeight: 700,
        fontSize: size * 0.45,
        fontFamily: "var(--font-mono)",
        boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.15)",
        flexShrink: 0,
      }}
    >
      {initial}
    </div>
  );
}
