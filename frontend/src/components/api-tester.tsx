"use client";

import { Activity, Play, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { testProvider, type ProviderManagement, type ProviderTestResult } from "@/lib/api";

export function ApiTester({ providers }: { providers: ProviderManagement["providers"] }) {
  const [provider, setProvider] = useState("Marketstack");
  const [query, setQuery] = useState("Check historical price data and provider connectivity");
  const [symbol, setSymbol] = useState("NVDA");
  const [result, setResult] = useState<ProviderTestResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const enabled = providers.filter((item) => item.enabled);
  const selectedEnabled = provider === "Public News RSS scraper" || enabled.some((item) => item.name === provider);

  async function run() {
    setBusy(true); setError(""); setResult(null);
    try { setResult(await testProvider(provider, query.trim(), symbol.trim())); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Provider check failed."); }
    finally { setBusy(false); }
  }

  return <section className="api-tester" aria-labelledby="api-tester-title">
    <div className="api-tester-heading"><div><span className="panel-kicker">ADMIN · CONNECTIVITY DIAGNOSTIC</span><h3 id="api-tester-title"><Activity size={17} /> API & scraper tester</h3></div><span className="source-pill"><ShieldCheck size={13} /> Credentials redacted</span></div>
    <p className="muted">Run one explicit connectivity request against an enabled provider. A live Marketstack check may consume your plan’s monthly request budget; cached results are labeled.</p>
    <div className="api-test-controls"><label>Provider<select value={provider} onChange={(event) => setProvider(event.target.value)}><optgroup label="Enabled API adapters">{enabled.map((item) => <option key={item.name} value={item.name}>{item.name}{item.ready ? " · ready" : " · unconfigured"}</option>)}</optgroup><option value="Public News RSS scraper">Public News RSS scraper · fallback</option></select></label><label>Example ticker<input value={symbol} onChange={(event) => setSymbol(event.target.value)} maxLength={32} disabled={provider === "Public News RSS scraper"} /></label><label>{provider === "Public News RSS scraper" ? "News topic" : "Test query"}<input value={query} onChange={(event) => setQuery(event.target.value)} maxLength={300} /></label><button className="primary-button" onClick={() => void run()} disabled={busy || !selectedEnabled || !query.trim()}><Play size={15} />{busy ? "Checking…" : "Run API test"}</button></div>
    {error && <p className="api-test-error" role="alert">{error}</p>}
    {result && <div className={`api-test-result ${result.ok ? "success" : "failure"}`} role="status"><div className="api-test-summary"><strong>{result.provider} · {result.ok ? "Connected" : "Request failed"}</strong><span>{result.status_code == null ? "No HTTP status" : `HTTP ${result.status_code}`} · {Math.round(result.elapsed_ms)} ms · {result.attempts} attempt(s){result.from_cache ? " · cached" : ""}</span>{result.budget_remaining != null && <span>Configured monthly budget remaining: {result.budget_remaining}</span>}{result.rate_limit_remaining != null && <span>Provider requests remaining: {result.rate_limit_remaining}</span>}{result.rate_limit_reset_seconds != null && <span>Rate limit reset in about {Math.ceil(result.rate_limit_reset_seconds)} seconds</span>}</div>{result.error && <p>{result.error}</p>}<details><summary>Sanitized response preview</summary><pre>{JSON.stringify(result.data ?? { status: result.ok ? "connected" : "no response data" }, null, 2)}</pre></details></div>}
    <small className="api-tester-note">429 handling: the HTTP adapter respects Retry-After and bounded retries. Country headlines fall back from GDELT to public RSS; equity history uses the configured Marketstack/Alpha Vantage failover. Scraper fallback does not bypass logins or access restrictions.</small>
  </section>;
}
