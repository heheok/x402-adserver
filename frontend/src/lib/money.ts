/**
 * Money helpers — Session 16.9.
 *
 * Wire format is integer microUSDC as a string (e.g. "422000" = $0.422).
 * 1 USDC = 1_000_000 microUSDC. Same convention as x402, SPL token amounts,
 * and every Solana RPC for token balances. Float USDC is forbidden in this
 * code path; use these helpers (or BigInt) for any sum/compare/format.
 *
 * formatUsdc + sumMicro + subMicro use BigInt internally so they're correct
 * regardless of value size — even sums that exceed JS Number safe-integer
 * range (2^53 ≈ 9e15 micro = $9B). Use `parseUsdc` only when you know the
 * single value is well under $9B and want a JS number for UI delta math
 * (e.g. WalletChip's chip animation).
 */
export const MICRO = 1_000_000;
const MICRO_BIG = 1_000_000n;

/** Format a microUSDC string for display (default 6 decimal places — full
 *  microUSDC precision). BigInt-native — overflow-proof at any scale.
 *
 *  Default bumped from 4 → 6 so per-play amounts at sub-cent CPMs render
 *  the full precision (e.g. 50 micro = $0.000050 instead of truncating to
 *  "0.0000"). Callers showing whole-dollar summaries (campaign totals,
 *  CPM, escrow, faucet topline) explicitly pass `dp=2` to stay compact. */
export function formatUsdc(microStr: string, dp: number = 6): string {
  const micro = BigInt(microStr);
  const negative = micro < 0n;
  const abs = negative ? -micro : micro;
  const whole = abs / MICRO_BIG;
  const frac = abs % MICRO_BIG;
  if (dp <= 0) return `${negative ? "-" : ""}${whole}`;
  const fracStr = frac.toString().padStart(6, "0").slice(0, dp);
  return `${negative ? "-" : ""}${whole}.${fracStr}`;
}

/** Parse a microUSDC string into a JS number USDC value.
 *
 *  Use ONLY for UI-delta arithmetic on values you know are < $9B (e.g.
 *  the WalletChip pending-amount animation). For display, prefer
 *  `formatUsdc`; for sums, use `sumMicro`. */
export function parseUsdc(microStr: string | number | null | undefined): number {
  if (microStr == null) return 0;
  return Number(microStr) / MICRO;
}

/** Sum a list of microUSDC strings. BigInt-safe for any value range. */
export function sumMicro(strs: Array<string | null | undefined>): string {
  let total = 0n;
  for (const s of strs) {
    if (s == null) continue;
    total += BigInt(s);
  }
  return total.toString();
}

/** Subtract two microUSDC strings, returning a microUSDC string. */
export function subMicro(a: string, b: string): string {
  return (BigInt(a) - BigInt(b)).toString();
}

/** Compare two microUSDC strings. Returns negative/0/positive like cmp. */
export function cmpMicro(a: string, b: string): number {
  const diff = BigInt(a) - BigInt(b);
  return diff === 0n ? 0 : diff < 0n ? -1 : 1;
}
