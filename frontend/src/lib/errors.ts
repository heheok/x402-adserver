import { isAxiosError } from "axios";

/**
 * Extract a human-readable error message. Handles:
 *   - Axios errors with FastAPI-style body { detail: string | ValidationError[] }
 *   - Axios network errors (connection refused, CORS, etc.)
 *   - Plain Error objects — including our manual x402 throws shaped
 *     `Backend 400: {"detail":"..."}` which we unwrap.
 * Never returns the useless "Request failed with status code N".
 */
export function humanizeError(err: unknown): string {
  if (isAxiosError(err)) {
    const data = err.response?.data;
    if (data && typeof data === "object") {
      const detail = (data as { detail?: unknown }).detail;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) {
        // FastAPI validation errors: [{loc, msg, type}, ...]
        return detail
          .map((e) =>
            typeof e === "object" && e !== null && "msg" in e
              ? String((e as { msg: unknown }).msg)
              : JSON.stringify(e),
          )
          .join("; ");
      }
    }
    if (typeof data === "string" && data.length > 0) return data;
    if (err.code === "ERR_NETWORK") {
      return "Network error — is the backend running on port 8000?";
    }
    if (err.response?.status) return `HTTP ${err.response.status}`;
    return err.message;
  }
  if (err instanceof Error) {
    const match = err.message.match(/^Backend \d+:\s*(.+)$/);
    if (match) {
      try {
        const parsed = JSON.parse(match[1]);
        if (typeof parsed.detail === "string") return parsed.detail;
      } catch {
        // fall through and use err.message
      }
    }
    return err.message;
  }
  return String(err);
}
