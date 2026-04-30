/**
 * Resolve the Solana RPC URL for the browser.
 *
 * - If VITE_SOLANA_RPC_URL is unset (dev compose) → direct devnet endpoint.
 * - If set to an absolute URL → used as-is.
 * - If set to a relative path (e.g. "/solana-rpc" in prod) → resolved against
 *   window.location.origin at runtime, so the same build works on
 *   localhost, your-domain.com, etc.
 *
 * Caddy proxies /solana-rpc → https://api.devnet.solana.com on the prod path,
 * dodging browser CORS quirks on the public devnet endpoint and putting
 * rate-limit attribution on the VM instead of the user.
 */
export function solanaRpcUrl(): string {
  const envRpc = import.meta.env.VITE_SOLANA_RPC_URL;
  if (!envRpc) return "https://api.devnet.solana.com";
  return new URL(envRpc, window.location.origin).toString();
}
