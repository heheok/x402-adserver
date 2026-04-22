import axios, { type AxiosInstance } from "axios";
import { useMemo } from "react";
import { usePrivy } from "@privy-io/react-auth";

const baseURL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

/**
 * Un-authenticated axios instance — use for public endpoints like /health.
 * For authed endpoints, use `useApi()` so each request gets a fresh Privy JWT.
 */
export const api: AxiosInstance = axios.create({ baseURL });

/**
 * Returns an axios instance that attaches the caller's Privy access token as
 * a Bearer header on every request. The token can expire; fetching it on
 * each request lets Privy refresh it transparently.
 */
export function useApi(): AxiosInstance {
  const { getAccessToken } = usePrivy();

  return useMemo(() => {
    const instance = axios.create({ baseURL });
    instance.interceptors.request.use(async (config) => {
      const token = await getAccessToken();
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });
    return instance;
  }, [getAccessToken]);
}
