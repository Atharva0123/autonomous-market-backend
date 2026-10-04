import type { Country, CountryOverview, CountryRelationships, ForecastResponse, NewsStory, SourceInfo, Suggestion, TaxEstimate, UsageStatus } from "@/lib/types";

// The browser always calls the same-origin Next.js proxy. Provider credentials
// and the backend origin must stay server-side and must never use NEXT_PUBLIC_*.
export const API_BASE = "";

export type AuthStatus = { setup_required: boolean; authenticated: boolean; username?: string | null; google_enabled?: boolean };
export const getAuthStatus = (): Promise<AuthStatus> => request("/api/v1/auth/status");
export const setupAccount = (username: string, password: string, setupToken: string) => request<{ status: string; username: string }>("/api/v1/auth/setup", { method: "POST", body: JSON.stringify({ username, password, setup_token: setupToken }) });
export const login = (username: string, password: string) => request<{ status: string; username: string }>("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
export const logout = async () => {
  const result = await request<{ status: string }>("/api/v1/auth/logout", { method: "POST" });
  clearClientCache();
  return result;
};
export const getUsage = (): Promise<UsageStatus> => request("/api/v1/usage");

export type ProviderManagement = {
  admin_username: string;
  price_provider: "auto" | "Marketstack" | "Alpha Vantage";
  automatic_failover: boolean;
  enabled_providers: Record<string, boolean>;
  persistence_mode: string;
  providers: { name: string; ready: boolean; enabled: boolean; note: string }[];
};
export const getProviderManagement = (): Promise<ProviderManagement> => request("/api/v1/admin/providers");
export const saveProviderManagement = (settings: Pick<ProviderManagement, "price_provider" | "automatic_failover" | "enabled_providers">) =>
  request<ProviderManagement>("/api/v1/admin/providers", { method: "PUT", body: JSON.stringify(settings) });
export type ProviderTestResult = { provider: string; ok: boolean; status_code?: number | null; elapsed_ms: number; attempts: number; from_cache: boolean; rate_limit_remaining?: number | null; rate_limit_reset_seconds?: number | null; budget_remaining?: number | null; error?: string | null; data?: unknown };
export const testProvider = (provider: string, query: string, symbol: string): Promise<ProviderTestResult> =>
  request("/api/v1/admin/test-provider", { method: "POST", body: JSON.stringify({ provider, query, symbol }) });

const CACHE_PREFIX = "marketdesk-cache-v1:";
const CLIENT_CACHE_TTL_MS = 60_000;
const memoryCache = new Map<string, { expires: number; value: unknown }>();
const cacheablePath = (path: string) => path.startsWith("/api/v1/countries") || path.startsWith("/api/v1/catalog/search") || path === "/api/v1/sources" || path === "/api/v1/data-status";
function cachedValue<T>(path: string): T | undefined {
  const now = Date.now();
  const memory = memoryCache.get(path);
  if (memory && memory.expires > now) { memoryCache.delete(path); memoryCache.set(path, memory); return memory.value as T; }
  if (typeof window !== "undefined") {
    try {
      const raw = window.localStorage.getItem(CACHE_PREFIX + path);
      if (raw) {
        const saved = JSON.parse(raw) as { expires: number; value: T };
        if (saved.expires > now) { memoryCache.set(path, saved); return saved.value; }
        window.localStorage.removeItem(CACHE_PREFIX + path);
      }
    } catch { /* Storage may be disabled or full; network remains the source of truth. */ }
  }
  return undefined;
}
function saveCached(path: string, value: unknown) {
  const row = { expires: Date.now() + CLIENT_CACHE_TTL_MS, value };
  memoryCache.delete(path); memoryCache.set(path, row);
  while (memoryCache.size > 40) memoryCache.delete(memoryCache.keys().next().value as string);
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(CACHE_PREFIX + path, JSON.stringify(row));
      const keys = Object.keys(window.localStorage).filter((key) => key.startsWith(CACHE_PREFIX));
      for (const key of keys.slice(0, Math.max(0, keys.length - 40))) window.localStorage.removeItem(key);
    } catch { /* Cache is an optimization only. */ }
  }
}
export function clearClientCache() {
  memoryCache.clear();
  if (typeof window !== "undefined") {
    try {
      for (const key of Object.keys(window.localStorage).filter((item) => item.startsWith(CACHE_PREFIX) || item === "marketdesk-recent-searches")) window.localStorage.removeItem(key);
    }
    catch { /* Ignore private-mode storage failures. */ }
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const canCache = (!init?.method || init.method === "GET") && cacheablePath(path);
  if (canCache) { const cached = cachedValue<T>(path); if (cached !== undefined) return cached; }
  const response = await fetch(`${API_BASE}${path}`, { ...init, credentials: "include", cache: "no-store", headers: { "Content-Type": "application/json", ...init?.headers } });
  if (!response.ok) {
    const detail = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(detail?.detail ?? `Request failed (${response.status})`);
  }
  const payload = await response.json() as T;
  if (canCache) saveCached(path, payload);
  return payload;
}

export const getCountries = (): Promise<Country[]> => request("/api/v1/countries");
export const getSuggestions = (query: string): Promise<Suggestion[]> => request(`/api/v1/catalog/search?q=${encodeURIComponent(query)}`);
export const getOverview = (iso3: string, startYear: number, endYear: number): Promise<CountryOverview> =>
  request(`/api/v1/countries/${iso3}/overview?start_year=${startYear}&end_year=${endYear}`);
export const getRelationships = (iso3: string, startYear: number, endYear: number): Promise<CountryRelationships> =>
  request(`/api/v1/countries/${iso3}/relationships?start_year=${startYear}&end_year=${endYear}`);
export const getNews = async (iso3: string, topic?: string): Promise<{ status: string; stories: NewsStory[]; error?: string }> =>
  request(`/api/v1/countries/${iso3}/news?days=30&limit=100${topic ? `&topic=${encodeURIComponent(topic)}` : ""}`);
export const getSources = (): Promise<SourceInfo[]> => request("/api/v1/sources");
export const getDataStatus = (): Promise<{ providers: Record<string, { ready: boolean; note: string }>; forecast_requirements: string[]; marketstack_key_configured: boolean; alphavantage_key_configured: boolean }> => request("/api/v1/data-status");
export const getTaxPolicy = (iso3: string, startYear: number, endYear: number) =>
  request<{ country: Country; tax_revenue_series: CountryOverview["macro"][number]; statutory_rates_status: string; official_policy_url?: string | null; limitations: string[] }>(
    `/api/v1/countries/${iso3}/tax-policy?start_year=${startYear}&end_year=${endYear}`);
export const submitForecast = (symbol: string, dateFrom: string, dateTo: string): Promise<ForecastResponse> =>
  request(`/api/v1/forecasts/${encodeURIComponent(symbol)}?date_from=${dateFrom}&date_to=${dateTo}`, { method: "POST" });
export const submitTaxEstimate = (payload: Record<string, unknown>): Promise<TaxEstimate> =>
  request("/api/v1/tax/estimate-india", { method: "POST", body: JSON.stringify(payload) });
