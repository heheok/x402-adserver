export function truncateAddress(addr: string, keep = 4): string {
  if (!addr || addr.length <= keep * 2 + 1) return addr;
  return `${addr.slice(0, keep)}…${addr.slice(-keep)}`;
}

export function solscanTxUrl(txHash: string): string {
  return `https://solscan.io/tx/${txHash}?cluster=devnet`;
}

export function solscanAccountUrl(address: string): string {
  return `https://solscan.io/account/${address}?cluster=devnet`;
}
