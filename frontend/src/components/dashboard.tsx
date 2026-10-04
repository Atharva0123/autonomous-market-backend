"use client";

import { Activity, ArrowUpRight, BarChart3, BookOpenCheck, CalendarDays, Command,
  
  CircleHelp, Globe2, LayoutDashboard, LineChart, Menu, ShieldAlert, Sparkles,
  WalletCards } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import {
  CartesianGrid, ComposedChart, Line, LineChart as ReLineChart, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { GlobePanel } from "@/components/globe-panel";
import { SearchBox } from "@/components/search-box";
import { AssetAutocomplete } from "@/components/asset-autocomplete";
import { CountryPicker } from "@/components/country-picker";
import { CommandPalette } from "@/components/command-palette";
import { ApiManagement } from "@/components/api-management";
import { API_BASE, getCountries, getDataStatus, getNews, getOverview, getRelationships, getSources, getTaxPolicy, getUsage, submitForecast, submitTaxEstimate } from "@/lib/api";
import type { Country, CountryOverview, CountryRelationships, ForecastResponse, NewsStory, SourceInfo, Suggestion, TaxEstimate, UsageStatus } from "@/lib/types";

type Page = "pulse" | "research" | "tax" | "sources";
const SECTORS = ["All sector headlines", "Technology", "Financials", "Health Care", "Energy", "Industrials", "Consumer Discretionary", "Consumer Staples", "Materials", "Communication Services", "Real Estate", "Utilities"];
const ASSET_PRESETS = ["AAPL", "NVDA", "MSFT", "SPY", "BTC-USD", "GC=F"];
const SECTOR_MACRO_IDS: Record<string, string[]> = {
  [SECTORS[0]]: ["NY.GDP.MKTP.KD.ZG", "FP.CPI.TOTL.ZG", "SL.UEM.TOTL.ZS", "NE.TRD.GNFS.ZS", "FI.RES.TOTL.CD", "GC.TAX.TOTL.GD.ZS", "GC.DOD.TOTL.GD.ZS"],
  Technology: ["NY.GDP.MKTP.KD.ZG", "NE.TRD.GNFS.ZS", "FP.CPI.TOTL.ZG", "SL.UEM.TOTL.ZS"],
  Financials: ["FP.CPI.TOTL.ZG", "NY.GDP.MKTP.KD.ZG", "GC.DOD.TOTL.GD.ZS", "GC.TAX.TOTL.GD.ZS"],
  "Health Care": ["NY.GDP.MKTP.KD.ZG", "FP.CPI.TOTL.ZG", "SL.UEM.TOTL.ZS", "NE.TRD.GNFS.ZS"],
  Energy: ["NY.GDP.MKTP.KD.ZG", "FP.CPI.TOTL.ZG", "NE.TRD.GNFS.ZS", "FI.RES.TOTL.CD"],
  Industrials: ["NY.GDP.MKTP.KD.ZG", "NE.TRD.GNFS.ZS", "SL.UEM.TOTL.ZS", "FI.RES.TOTL.CD"],
  "Consumer Discretionary": ["NY.GDP.MKTP.KD.ZG", "SL.UEM.TOTL.ZS", "FP.CPI.TOTL.ZG", "GC.TAX.TOTL.GD.ZS"],
  "Consumer Staples": ["FP.CPI.TOTL.ZG", "NY.GDP.MKTP.KD.ZG", "SL.UEM.TOTL.ZS"],
  Materials: ["NE.TRD.GNFS.ZS", "FI.RES.TOTL.CD", "NY.GDP.MKTP.KD.ZG", "FP.CPI.TOTL.ZG"],
  "Communication Services": ["NY.GDP.MKTP.KD.ZG", "NE.TRD.GNFS.ZS", "FP.CPI.TOTL.ZG"],
  "Real Estate": ["FP.CPI.TOTL.ZG", "NY.GDP.MKTP.KD.ZG", "GC.DOD.TOTL.GD.ZS"],
  Utilities: ["FP.CPI.TOTL.ZG", "NY.GDP.MKTP.KD.ZG", "NE.TRD.GNFS.ZS"],
};

function localDate(date: Date) { return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`; }
function fmt(value: number | null | undefined, digits = 1) { return value == null || !Number.isFinite(value) ? "—" : value.toLocaleString(undefined, { maximumFractionDigits: digits }); }
function latest(series?: CountryOverview["macro"][number]) { return series?.observations.at(-1); }

export function Dashboard({ onLogout, username }: { onLogout?: () => Promise<void>; username?: string }) {
  const now = new Date();
  const [page, setPage] = useState<Page>("pulse");
  const [mode, setMode] = useState<"simple" | "pro">("simple");
  const [commandOpen, setCommandOpen] = useState(false);
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const [usage, setUsage] = useState<UsageStatus | null | undefined>(undefined);
  const [countries, setCountries] = useState<Country[]>([]);
  const [iso3, setIso3] = useState("WLD");
  const [overview, setOverview] = useState<CountryOverview | null>(null);
  const [macroLoading, setMacroLoading] = useState(true);
  const [relationships, setRelationships] = useState<CountryRelationships | null>(null);
  const [stories, setStories] = useState<NewsStory[]>([]);
  const [newsStatus, setNewsStatus] = useState("loading");
  const [newsError, setNewsError] = useState("");
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [dataStatus, setDataStatus] = useState<{ providers: Record<string, { ready: boolean; note: string }>; forecast_requirements: string[]; marketstack_key_configured: boolean; alphavantage_key_configured: boolean } | null>(null);
  const [sector, setSector] = useState(SECTORS[0]);
  const [rangeFrom, setRangeFrom] = useState(localDate(new Date(now.getFullYear() - 1, now.getMonth(), now.getDate())));
  const [rangeTo, setRangeTo] = useState(localDate(now));
  const [selectedPreset, setSelectedPreset] = useState<"7d" | "1m" | "ytd" | "1y" | "custom">("1y");
  const [macroHistoryYears, setMacroHistoryYears] = useState(10);
  const endYear = Number(rangeTo.slice(0, 4));
  const startYear = Math.max(1960, endYear - macroHistoryYears);
  const [selectedMetric, setSelectedMetric] = useState("NY.GDP.MKTP.KD.ZG");
  const [symbol, setSymbol] = useState("NVDA");
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [researchQuery, setResearchQuery] = useState("");
  const [researchTrace, setResearchTrace] = useState<string[]>([]);
  const [researchReport, setResearchReport] = useState<Record<string, unknown> | null>(null);
  const [researchCitations, setResearchCitations] = useState<{ provider?: string; url: string; retrieved_at?: string; status: string; record_id?: string }[]>([]);
  const [estimate, setEstimate] = useState<TaxEstimate | null>(null);
  const [taxError, setTaxError] = useState("");
  const [taxPolicy, setTaxPolicy] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setCommandOpen((open) => !open); }
      if (event.key === "Escape") setCommandOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const country = useMemo(() => countries.find((item) => item.iso3 === iso3), [countries, iso3]);
  const countryName = country?.name ?? (iso3 === "WLD" ? "World" : iso3 === "IND" ? "India" : iso3);
  const loadCountryOverview = useCallback(async () => {
    setMacroLoading(true);
    try {
      const [macro, crossMarket] = await Promise.all([
        getOverview(iso3, startYear, endYear),
        getRelationships(iso3, startYear, endYear).catch(() => null),
      ]);
      setOverview(macro);
      setRelationships(crossMarket);
      setUpdatedAt(new Date());
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load country data.");
    } finally {
      setMacroLoading(false);
    }
  }, [iso3, startYear, endYear]);

  const loadCountryNews = useCallback(async () => {
    setStories([]);
    setNewsStatus("loading");
    setNewsError("");
    try {
      const result = await getNews(iso3, sector === SECTORS[0] ? undefined : sector);
      setStories(result.stories);
      setNewsStatus(result.status);
      setNewsError(result.error ?? "");
    } catch (caught) {
      setStories([]);
      setNewsStatus("unavailable");
      setNewsError(caught instanceof Error ? caught.message : "News service request failed.");
    }
  }, [iso3, sector]);

  useEffect(() => {
    getCountries().then((rows) => setCountries(rows)).catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "Country catalog unavailable."));
    getSources().then(setSources).catch(() => setSources([]));
    getDataStatus().then(setDataStatus).catch(() => setDataStatus(null));
    const refreshUsage = () => getUsage().then(setUsage).catch(() => setUsage(null));
    void refreshUsage();
    const usageTimer = window.setInterval(refreshUsage, 60_000);
    return () => window.clearInterval(usageTimer);
  }, []);
  useEffect(() => {
    setOverview(null);
    setRelationships(null);
    void loadCountryOverview();
  }, [loadCountryOverview]);
  useEffect(() => { void loadCountryNews(); }, [loadCountryNews]);
  useEffect(() => {
    const interval = window.setInterval(() => { void loadCountryOverview(); void loadCountryNews(); }, 300_000);
    return () => window.clearInterval(interval);
  }, [loadCountryOverview, loadCountryNews]);

  const chooseSuggestion = (suggestion: Suggestion) => {
    if (suggestion.kind === "country") { setIso3(suggestion.value); setPage("pulse"); return; }
    if (suggestion.kind === "sector") { setSector(suggestion.value); setPage("pulse"); return; }
    if (["asset", "commodity", "index"].includes(suggestion.kind)) { setSymbol(suggestion.value); setPage("research"); return; }
    const query = (suggestion.query_template ?? suggestion.value)
      .replaceAll("{asset}", symbol)
      .replaceAll("{country}", countryName)
      .replaceAll("{sector}", sector)
      .replaceAll("{date_from}", rangeFrom)
      .replaceAll("{date_to}", rangeTo);
    setResearchQuery(query);
    setPage("research");
    void submitResearch(query);
  };

  async function submitResearch(query: string) {
    const nextQuery = query || researchQuery;
    if (!nextQuery.trim()) { setPage("research"); return; }
    setResearchQuery(nextQuery); setPage("research"); setResearchTrace([]); setResearchReport(null); setResearchCitations([]); setBusy(true); setError("");
    try {
      const response = await fetch(`${API_BASE}/api/v1/research/stream`, {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: nextQuery, date_from: rangeFrom, date_to: rangeTo, make_prediction: /predict/i.test(nextQuery) }),
      });
      if (!response.ok || !response.body) throw new Error(`Research request failed (${response.status})`);
      const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = "";
      while (true) {
        const { value, done } = await reader.read(); if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n"); buffer = chunks.pop() ?? "";
        for (const chunk of chunks) {
          const line = chunk.split("\n").find((entry) => entry.startsWith("data: "));
          if (!line) continue;
          const event = JSON.parse(line.slice(6)) as { type: string; message?: string; payload?: { report: Record<string, unknown>; citations?: { provider?: string; url: string; retrieved_at?: string; status: string; record_id?: string }[] } };
          if (event.type === "trace" && event.message) setResearchTrace((current) => [...current, event.message as string]);
          if (event.type === "complete" && event.payload) { setResearchReport(event.payload.report); setResearchCitations(event.payload.citations ?? []); }
          if (event.type === "error") throw new Error(event.message ?? "Research failed");
        }
      }
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Research request failed."); }
    finally { setBusy(false); }
  }

  async function runForecast() {
    setPage("research"); setBusy(true); setError(""); setForecast(null);
    try { setForecast(await submitForecast(symbol, rangeFrom, rangeTo)); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Forecast unavailable."); }
    finally { setBusy(false); }
  }

  const metrics = ["NY.GDP.MKTP.KD.ZG", "FP.CPI.TOTL.ZG", "SL.UEM.TOTL.ZS", "NE.TRD.GNFS.ZS", "GC.TAX.TOTL.GD.ZS"];
  const relevantMacroIds = SECTOR_MACRO_IDS[sector] ?? SECTOR_MACRO_IDS[SECTORS[0]];
  const chartSeries = overview?.macro.filter((item) => relevantMacroIds.includes(item.indicator)) ?? [];
  const metricSeries = overview?.macro.find((item) => item.indicator === selectedMetric);
  const macroChartRows = (metricSeries?.observations ?? []).map((item) => ({ period: item.period, value: item.value }));

  useEffect(() => {
    const availableIds = SECTOR_MACRO_IDS[sector] ?? SECTOR_MACRO_IDS[SECTORS[0]];
    const firstRelevant = overview?.macro.find((item) => availableIds.includes(item.indicator));
    if (firstRelevant && !availableIds.includes(selectedMetric)) setSelectedMetric(firstRelevant.indicator);
  }, [sector, overview, selectedMetric]);

  function applyDatePreset(preset: "7d" | "1m" | "ytd" | "1y") {
    const today = new Date(); const start = new Date(today);
    if (preset === "7d") start.setDate(start.getDate() - 7);
    if (preset === "1m") { const day = start.getDate(); start.setDate(1); start.setMonth(start.getMonth() - 1); start.setDate(Math.min(day, new Date(start.getFullYear(), start.getMonth() + 1, 0).getDate())); }
    if (preset === "ytd") { start.setMonth(0, 1); }
    if (preset === "1y") { const day = start.getDate(); start.setDate(1); start.setFullYear(start.getFullYear() - 1); start.setDate(Math.min(day, new Date(start.getFullYear(), start.getMonth() + 1, 0).getDate())); }
    setSelectedPreset(preset); setRangeFrom(localDate(start)); setRangeTo(localDate(today));
  }
  const changeDateFrom = (value: string) => { setSelectedPreset("custom"); setRangeFrom(value); };
  const changeDateTo = (value: string) => { setSelectedPreset("custom"); setRangeTo(value); };

  return <main className="app-shell">
    <CommandPalette open={commandOpen} onClose={() => setCommandOpen(false)} onChoose={chooseSuggestion} onSubmit={(query) => void submitResearch(query)} onNavigate={setPage} />
    {mobileDrawerOpen && <button className="drawer-backdrop" aria-label="Close workspace menu" onClick={() => setMobileDrawerOpen(false)} />}
    <aside className={`sidebar ${mobileDrawerOpen ? "drawer-open" : ""}`}>
      <a className="brand" href="#home" onClick={(event) => { event.preventDefault(); setPage("pulse"); }}>
        <span className="brand-mark"><Activity size={20} /></span><span>MARKET<span className="brand-light">DESK</span><small>GLOBAL RESEARCH SYSTEM</small></span>
      </a>
      <div className="sidebar-label">WORKSPACE</div>
      <nav className="side-nav" aria-label="Main workspace">
        <button className={page === "pulse" ? "nav-item active" : "nav-item"} onClick={() => { setPage("pulse"); setMobileDrawerOpen(false); }}><LayoutDashboard size={17} />Global Pulse</button>
        <button className={page === "research" ? "nav-item active" : "nav-item"} onClick={() => { setPage("research"); setMobileDrawerOpen(false); }}><LineChart size={17} />Asset Research</button>
        <button className={page === "tax" ? "nav-item active" : "nav-item"} onClick={() => { setPage("tax"); setMobileDrawerOpen(false); }}><WalletCards size={17} />Tax & Policy</button>
        <button className={page === "sources" ? "nav-item active" : "nav-item"} onClick={() => { setPage("sources"); setMobileDrawerOpen(false); }}><BookOpenCheck size={17} />Data Sources</button>
      </nav>
      <div className="sidebar-label section-spaced">QUICK RESEARCH</div>
      <div className="quick-assets">{ASSET_PRESETS.map((asset) => <button key={asset} onClick={() => { setSymbol(asset); setPage("research"); }}><span>{asset}</span><ArrowUpRight size={13} /></button>)}</div>
      <div className="sidebar-bottom"><span className="status-dot" />LOCAL RESEARCH MODE<p>No broker connections · no orders</p></div>
    </aside>

    <section className="main-column">
      <header className="topbar">
        <button className="hamburger-button" aria-label="Open workspace menu" aria-expanded={mobileDrawerOpen} onClick={() => setMobileDrawerOpen((open) => !open)}><Menu size={20} /></button>
        <div className="crumb"><span>RESEARCH</span><span className="slash">/</span><strong>{page === "pulse" ? "GLOBAL PULSE" : page === "research" ? "ASSET RESEARCH" : page === "tax" ? "TAX & POLICY" : "SOURCE COVERAGE"}</strong></div>
        <div className="top-actions"><span className={`connection ${usage === null ? "connection-offline" : ""}`}><span className="status-dot" />API {usage === undefined ? "CHECKING" : usage ? "ONLINE" : "OFFLINE"} · MARKETSTACK {usage ? usage.key_configured ? `${usage.remaining}/${usage.limit} REQ LEFT` : `${usage.remaining} LEFT · KEY NEEDED` : "QUOTA UNKNOWN"}</span><button className="command-trigger" onClick={() => setCommandOpen(true)} aria-label="Open command palette"><Command size={14} /><span>Commands</span><kbd>⌘ K</kbd></button>{onLogout && <button className="signout-button" onClick={async () => { await onLogout(); }}>Sign out</button>}<button className="avatar" aria-label={`Signed in as ${username ?? "local user"}`}>{(username ?? "A").slice(0,1).toUpperCase()}</button></div>
      </header>

      <div className="content">
        <div className="page-heading">
          <div><div className="eyebrow"><span className="eyebrow-line" />GLOBAL MARKET INTELLIGENCE</div><h1>{page === "pulse" ? "See the connections." : page === "research" ? "Research an asset." : page === "tax" ? "Policy, with provenance." : "Know the data behind it."}</h1>
            <p>{page === "pulse" ? "Macro, markets, sectors and sentiment—one sourced view at a time." : page === "research" ? "A historical record, a tested baseline, and a clearly bounded outlook." : page === "tax" ? "Official country tax context and a narrow, rule-cited India estimate." : "Coverage, cadence, key requirements and source terms."}</p></div>
          <div className="mode-switch" role="group" aria-label="Choose dashboard detail level"><button type="button" className={mode === "simple" ? "selected" : ""} aria-pressed={mode === "simple"} title="Key takeaways and sourced context" onClick={() => setMode("simple")}>Overview</button><button type="button" className={mode === "pro" ? "selected" : ""} aria-pressed={mode === "pro"} title="Expanded metrics, source coverage, and research diagnostics" onClick={() => setMode("pro")}>Analyst</button></div>
        </div>

        <div className="command-row">
          <SearchBox onChoose={chooseSuggestion} onSubmit={submitResearch} />
          <label className="date-control"><CalendarDays size={14} /><span>FROM</span><input aria-label="Data from date" type="date" value={rangeFrom} onChange={(e) => changeDateFrom(e.target.value)} /></label>
          <label className="date-control"><span>TO</span><input aria-label="Data to date" type="date" value={rangeTo} onChange={(e) => changeDateTo(e.target.value)} /></label>
          <button className="predict-button" onClick={() => { setResearchQuery(`Make prediction for ${symbol}`); setPage("research"); void runForecast(); }}><Sparkles size={15} />Make prediction</button>
        </div>
        <div className="date-presets" aria-label="Date range presets"><span>TAKE DATA FROM</span>{([ ["7 Days", "7d"], ["1 Month", "1m"], ["YTD", "ytd"], ["1 Year", "1y"] ] as const).map(([label, preset]) => <button key={preset} className={selectedPreset === preset ? "active" : ""} onClick={() => applyDatePreset(preset)}>{label}</button>)}<small>{selectedPreset === "custom" ? "Custom range selected" : "Custom range: edit the dates above"}</small></div>

        {error && <div className="alert error-alert"><ShieldAlert size={17} /><span>{error}</span><button onClick={() => setError("")}>Dismiss</button></div>}

        {page === "pulse" && <>
        <div className="section-toolbar"><div><span className="live-pip" />GLOBAL SNAPSHOT <span className="muted">· {updatedAt ? `Updated ${updatedAt.toLocaleTimeString()}` : "Loading sources"} · 5 min refresh</span></div>
              <div className="country-toolbar"><label className="history-control">MACRO HISTORY<select aria-label="Macro history range" value={macroHistoryYears} onChange={(event) => setMacroHistoryYears(Number(event.target.value))}><option value={5}>5 years</option><option value={10}>10 years</option><option value={20}>20 years</option><option value={66}>Since 1960</option></select></label><button className="clear-filter-button compact" onClick={() => { setMacroHistoryYears(10); setSector(SECTORS[0]); setSelectedMetric("NY.GDP.MKTP.KD.ZG"); }}>Clear filters</button><CountryPicker countries={countries} selected={iso3} onSelect={setIso3} /></div></div>
          <div className="hero-grid">
            <section className="panel globe-panel"><div className="panel-title"><div><span className="panel-kicker">EXPLORE BY COUNTRY</span><h2>Global macro map</h2></div><span className="orbit-icon"><Globe2 size={18} /></span></div>
              <GlobePanel selected={iso3} onSelect={setIso3} /><div className="globe-footer"><span><i className="legend-selected" />Selected market</span><span>Click a country to drill in</span></div></section>
            <section className="country-summary"><div className="country-identity"><span className="country-flag">{country?.flag ?? "🌐"}</span><div><span className="panel-kicker">COUNTRY PROFILE</span><h2>{countryName}</h2><span className="country-code">ISO · {iso3}</span></div><span className="availability-tag">{overview?.market_coverage ?? "loading"} coverage</span></div>
              <div className="metric-grid">{metrics.map((id) => { const item = overview?.macro.find((entry) => entry.indicator === id); const point = latest(item); return <div className="metric-card" key={id}>
                <span>{item?.label ?? id}</span><strong>{point ? fmt(point.value, id === "NY.GDP.MKTP.KD.ZG" ? 2 : 1) : "—"}<small>{point ? ` ${item?.unit}` : " unavailable"}</small></strong><small className="metric-period">{point ? `Observation · ${point.period}` : macroLoading ? "Loading selected-country series…" : item?.source.usage_note ?? "Source returned no observation in this period."}</small>{item?.source && <a className="metric-source" href={item.source.url} target="_blank" rel="noreferrer">{item.source.name} ↗</a>}
              </div>; })}</div>
              <div className="summary-foot"><span>Public World Bank macro series · release cadence varies</span><button className="text-button" onClick={() => setPage("sources")}>View sources <ArrowUpRight size={13} /></button></div>
            </section>
          </div>

          <NewsSentiment stories={stories} status={newsStatus} error={newsError} />
          <EventStream stories={stories} status={newsStatus} updatedAt={updatedAt} global={iso3 === "WLD"} />
          <HeadlineImpactScan stories={stories} />
          <TrendRadar stories={stories} />

          <div className="dashboard-grid">
            <section className="panel macro-panel"><div className="panel-title"><div><span className="panel-kicker">HISTORICAL EVIDENCE · {sector === SECTORS[0] ? "COUNTRY" : sector.toUpperCase() + " CONTEXT"}</span><h2>Macro trendline · {countryName}</h2></div><select aria-label="Select macro indicator" value={selectedMetric} onChange={(event) => setSelectedMetric(event.target.value)}>
              {chartSeries.map((item) => <option key={item.indicator} value={item.indicator}>{item.label}</option>)}
            </select></div>
              <p className="sector-macro-note">{sector === SECTORS[0] ? "Select a sector to focus this chart on its relevant national indicators." : `Showing sourced national macro indicators that can affect ${sector.toLowerCase()} conditions. These are country statistics, not sector returns or proof of causality.`}</p>
              {macroChartRows.length ? <ResponsiveContainer width="100%" height={250}><ReLineChart data={macroChartRows} margin={{ top: 12, right: 18, bottom: 0, left: 0 }}><CartesianGrid stroke="#263747" strokeDasharray="3 5" vertical={false} /><XAxis dataKey="period" stroke="#788d9e" tickLine={false} axisLine={false} /><YAxis stroke="#788d9e" tickLine={false} axisLine={false} width={52} /><Tooltip contentStyle={{ background: "#111e2a", border: "1px solid #344858", borderRadius: 10 }} /><Line type="monotone" dataKey="value" stroke="#38bdf8" strokeWidth={2.5} dot={{ r: 3, fill: "#38bdf8", strokeWidth: 0 }} activeDot={{ r: 6 }} /></ReLineChart></ResponsiveContainer> : <div className="empty-state"><BarChart3 size={24} /><strong>{macroLoading ? `Loading ${countryName} macro history…` : "This series is unavailable"}</strong><span>{macroLoading ? `Fetching the last ${macroHistoryYears} years from World Bank indicators.` : metricSeries?.source.usage_note ?? `No observations for ${countryName} in ${startYear}–${endYear}.`}</span></div>}
              <div className="chart-caption"><span>Annual / release frequency varies by series · {overview?.macro.find((item) => item.indicator === selectedMetric)?.source.name ?? "Source unavailable"}</span><span>{startYear}—{endYear}</span></div>
              {overview?.macro.find((item) => item.indicator === selectedMetric)?.source.url && <SourceBadge name="Open original series" url={String(overview.macro.find((item) => item.indicator === selectedMetric)?.source.url)} />}
            </section>
            <section className="panel news-panel"><div className="panel-title"><div><span className="panel-kicker">SECTOR + COUNTRY COVERAGE</span><h2>Latest headlines</h2></div><div className="news-filters"><select aria-label="Filter headlines by sector" value={sector} onChange={(event) => setSector(event.target.value)}>{SECTORS.map((item) => <option key={item}>{item}</option>)}</select><button className="clear-filter-button compact" onClick={() => setSector(SECTORS[0])}>Clear filter</button></div></div>
              <div className="news-list">{stories.slice(0, 5).map((story) => <NewsRow key={story.url} story={story} />)}
                {newsStatus === "loading" && <p className="muted">Fetching the latest indexed stories…</p>}
                {newsStatus === "unavailable" && <p className="empty-note">News feed unavailable{newsError ? ` · ${newsError}` : ""}. Macro and country controls remain usable.</p>}
                {newsStatus === "available" && !stories.length && <p className="empty-note">No matching stories were returned for the current country/filter.</p>}
              </div><div className="summary-foot"><span>GDELT indexed headlines · English-only sentiment</span><span className="muted">30-day news window</span></div>
            </section>
          </div>

          <section className="panel sectors-panel"><div className="panel-title"><div><span className="panel-kicker">CROSS-STREAM CORRELATION MATRIX</span><h2>How available macro series moved together</h2></div><span className="discovery-tag">Observed association · not causal proof</span></div><p className="muted">Current matrix coverage is aligned annual World Bank indicators. Geopolitical event, commodity-price, and intraday asset joins are unavailable until verified historical feeds are configured.</p>
            <div className="relationship-grid">{relationships?.correlations.map((row) => <div className="relationship-card" key={row.label}><span>{row.label}</span><strong>{row.coefficient == null ? "N/A" : row.coefficient.toFixed(2)}</strong><small>Latest {row.rolling_window_years ?? 5}-year window · {row.period_start ?? "—"}–{row.period_end ?? "—"} · {row.evidence_count} aligned observations</small><MiniCorrelation points={row.rolling_points ?? []} /><div className="relationship-source"><a href={row.source_left.url} target="_blank" rel="noreferrer">{row.source_left.name}</a> · <a href={row.source_right.url} target="_blank" rel="noreferrer">source</a></div></div>)}</div>
            <p className="muted">{relationships?.interpretation ?? "Aligned public series are being loaded. Correlation is descriptive and does not prove transmission or causality."}</p>
            <div className="connection-flow"><div className="flow-node"><span>01 · MACRO</span><strong>GDP · CPI · Rates</strong><small>Growth and central-bank conditions</small></div><div className="flow-link"><span>can influence</span><ArrowUpRight size={15} /></div><div className="flow-node"><span>02 · FX & RATES</span><strong>Currency · Yields</strong><small>Discount rates and cross-border flows</small></div><div className="flow-link"><span>can reprice</span><ArrowUpRight size={15} /></div><div className="flow-node"><span>03 · SECTORS</span><strong>Demand · Margins</strong><small>Industry performance and earnings</small></div><div className="flow-link"><span>appears in</span><ArrowUpRight size={15} /></div><div className="flow-node"><span>04 · ASSETS</span><strong>Indices · Commodities</strong><small>Market prices when a source is available</small></div></div>
            <div className="sector-chip-row">{SECTORS.slice(1).map((name) => <button key={name} className={sector === name ? "sector-chip active" : "sector-chip"} onClick={() => setSector(name)}>{name}<ArrowUpRight size={12} /></button>)}</div>
          </section>
          {mode === "pro" && <ProTelemetry overview={overview} stories={stories} sources={sources} />}
          <div className="disclaimer"><CircleHelp size={15} /> Country statistics are historical releases. Market prices and policy coverage depend on configured sources; this app does not execute trades.</div>
        </>}

        {page === "research" && <ResearchView symbol={symbol} setSymbol={setSymbol} query={researchQuery} setQuery={setResearchQuery} onRunResearch={submitResearch} onRunForecast={runForecast} busy={busy} forecast={forecast} report={researchReport} citations={researchCitations} trace={researchTrace} mode={mode} rangeFrom={rangeFrom} rangeTo={rangeTo} setRangeFrom={changeDateFrom} setRangeTo={changeDateTo} />}
        {page === "tax" && <TaxView iso3={iso3} countryName={countryName} startYear={startYear} endYear={endYear} estimate={estimate} setEstimate={setEstimate} taxError={taxError} setTaxError={setTaxError} taxPolicy={taxPolicy} setTaxPolicy={setTaxPolicy} />}
        {page === "sources" && <SourcesView sources={sources} overview={overview} stories={stories} dataStatus={dataStatus} />}
      </div>
      <footer className="app-footer"><span>MARKET INTELLIGENCE DESK</span><span>LOCAL · RESEARCH ONLY · SOURCES ATTACHED TO OBSERVATIONS</span><span>v1.0</span></footer>
    </section>
  </main>;
}

function MiniCorrelation({ points }: { points: { period_end: string; coefficient?: number | null }[] }) {
  const valid = points.filter((point): point is { period_end: string; coefficient: number } => point.coefficient != null);
  if (valid.length < 2) return <small className="muted">Insufficient history for rolling line</small>;
  const path = valid.map((point, index) => `${index * 100 / (valid.length - 1)},${10 - point.coefficient * 9}`).join(" ");
  return <svg className="correlation-sparkline" viewBox="0 0 100 20" role="img" aria-label="Five-year rolling correlation history" preserveAspectRatio="none"><line x1="0" y1="10" x2="100" y2="10" /><polyline points={path} /></svg>;
}

function NewsRow({ story }: { story: NewsStory }) {
  const score = story.sentiment_score;
  return <article className="news-row"><span className={`sentiment-mark ${story.sentiment_label}`} />
    <div className="news-copy"><a href={story.url} target="_blank" rel="noreferrer">{story.title}</a><div><span>{story.publisher}</span><span>{story.published_at ? new Date(story.published_at).toLocaleString() : "Time not supplied"}</span><a className="source-link" href={story.source.url} target="_blank" rel="noreferrer">source↗</a></div></div>
    <div className={`sentiment-score ${story.sentiment_label}`}><strong>{score == null ? "N/A" : `${score >= 0 ? "+" : ""}${score.toFixed(2)}`}</strong><small>{story.sentiment_label} · {story.sentiment_evidence_count} item</small></div>
  </article>;
}

function NewsSentiment({ stories, status, error }: { stories: NewsStory[]; status: string; error?: string }) {
  const scored = stories.filter((story) => story.sentiment_score != null);
  const now = Date.now();
  const averageFor = (days: number) => {
    const recent = scored.filter((story) => story.published_at && now - new Date(story.published_at).getTime() <= days * 86_400_000 && new Date(story.published_at).getTime() <= now + 3_600_000);
    return { score: recent.length ? recent.reduce((total, story) => total + (story.sentiment_score ?? 0), 0) / recent.length : null, count: recent.length };
  };
  const shortTerm = averageFor(7);
  const longTerm = averageFor(30);
  const average = longTerm.score;
  const label = average == null ? "unavailable" : average >= 0.15 ? "positive" : average <= -0.15 ? "negative" : "neutral";
  const shortLabel = shortTerm.score == null ? "unavailable" : shortTerm.score >= 0.15 ? "positive" : shortTerm.score <= -0.15 ? "negative" : "neutral";
  return <section className="panel sentiment-overview"><div><span className="panel-kicker">COUNTRY / NEWS SENTIMENT</span><h2>Headline sentiment index</h2><p>English-language headlines only · VADER compound score · not a trading signal</p></div>
    <div className="sentiment-gauge"><strong className={label}>{average == null ? "N/A" : `${average >= 0 ? "+" : ""}${average.toFixed(2)}`}</strong><div className={average == null ? "sentiment-track unavailable" : "sentiment-track"} role={average == null ? undefined : "meter"} aria-label="Average English headline sentiment" aria-valuemin={average == null ? undefined : -1} aria-valuemax={average == null ? undefined : 1} aria-valuenow={average ?? undefined} aria-valuetext={average == null ? "Sentiment unavailable" : `${label}: ${average.toFixed(2)}`}><span className="sentiment-zero" />{average != null && <i className={`sentiment-pointer ${label}`} style={{ left: `${Math.max(2, Math.min(98, (average + 1) * 50))}%` }}><span>{average >= 0 ? "+" : ""}{average.toFixed(2)}</span></i>}</div><div className="sentiment-axis"><span>−1 bearish</span><span>0</span><span>+1 bullish</span></div><small className="sentiment-state">{average == null ? status === "loading" ? "Waiting for scored headlines…" : error || "No scored headlines returned for this country and date range." : `Index updates from ${scored.length} scored headlines when the country or sector changes.`}</small></div>
    <div className="sentiment-periods"><div className={`sentiment-period ${shortLabel}`}><span>SHORT TERM · 7D</span><strong>{shortTerm.score == null ? "N/A" : `${shortTerm.score >= 0 ? "+" : ""}${shortTerm.score.toFixed(2)}`}</strong><small>{shortTerm.count} dated headlines</small></div><div className={`sentiment-period ${label}`}><span>LONGER TERM · 30D</span><strong>{longTerm.score == null ? "N/A" : `${longTerm.score >= 0 ? "+" : ""}${longTerm.score.toFixed(2)}`}</strong><small>{longTerm.count} dated headlines</small></div><small className="sentiment-freshness">{status === "loading" ? "Refreshing news index…" : status === "unavailable" ? "News source unavailable" : `${scored.length} scored headlines · equal-weighted English VADER scores`}</small><a href="https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/amp/" target="_blank" rel="noreferrer">GDELT source notes ↗</a></div>
  </section>;
}

function EventStream({ stories, status, updatedAt, global }: { stories: NewsStory[]; status: string; updatedAt: Date | null; global: boolean }) {
  const items = stories.slice(0, 8);
  return <section className="panel event-stream" aria-label="Indexed market headlines">
    <div className="event-stream-head"><div><span className="panel-kicker">{global ? "GLOBAL" : "COUNTRY"} EVENT STREAM</span><strong>Indexed headlines</strong></div><span className="stream-status"><i className={status === "available" ? "" : "stream-dot-muted"} />{status === "available" ? "REFRESHES EVERY 5 MIN" : status.toUpperCase()}</span></div>
    {items.length ? <div className="event-window"><div className="event-track">{[...items, ...items].map((story, index) => <a className="event-item" key={`${story.url}-${index}`} href={story.url} target="_blank" rel="noreferrer"><span className={`event-score ${story.sentiment_label}`}>{story.sentiment_score == null ? "—" : story.sentiment_score.toFixed(2)}</span><span>{story.title}</span><small>{story.publisher}</small></a>)}</div></div> : <p className="event-empty">{status === "unavailable" ? "The news index is unavailable; no event stream is inferred." : "Headlines are loading for this country and selected topic."}</p>}
    <div className="event-stream-foot"><span>GDELT-indexed · provider timestamps may lag publication</span><span>{updatedAt ? `Retrieved ${updatedAt.toLocaleTimeString()}` : "Waiting for first response"}</span></div>
  </section>;
}

function HeadlineImpactScan({ stories }: { stories: NewsStory[] }) {
  const categories = [
    { name: "Geopolitics & trade", terms: /conflict|war |sanction|tariff|trade restriction|election|geopolit|strait|chokepoint/i, channels: "Energy · defense · exporters · shipping" },
    { name: "Rates & policy", terms: /central bank|interest rate|federal reserve|rate cut|rate hike|inflation|treasury yield|monetary policy/i, channels: "Banks · bonds · currencies · growth stocks" },
    { name: "Energy & commodities", terms: /crude|oil price|natural gas|opec|commodity|copper|gold price|energy supply/i, channels: "Energy · materials · transport · input costs" },
    { name: "Supply chain & transport", terms: /shipping|supply chain|port closure|freight|canal|vessel|logistics|export route/i, channels: "Industrials · retail · semiconductors · freight" },
    { name: "Natural hazards", terms: /earthquake|wildfire|hurricane|flood|drought|cyclone|volcano|storm warning/i, channels: "Insurance · utilities · agriculture · regional assets" },
    { name: "Technology & cyber", terms: /cyberattack|ransomware|data breach|semiconductor|chip export|artificial intelligence|data center/i, channels: "Technology · chips · cloud · cybersecurity" },
  ];
  const cards = categories.map((category) => ({
    ...category,
    evidence: stories.filter((story) => category.terms.test(story.title)).slice(0, 2),
    count: stories.filter((story) => category.terms.test(story.title)).length,
  })).filter((category) => category.count > 0);
  return <section className="panel impact-scan">
    <div className="panel-title"><div><span className="panel-kicker">CROSS-ASSET EVENT WATCH · HEADLINE EVIDENCE</span><h2>Potential market impact channels</h2></div><span className="discovery-tag">Discovery signals · verify sources</span></div>
    <p className="muted">Keyword tags group current headlines into themes equity researchers often monitor. Counts are headline matches—not verified incidents, event probabilities, or causal price effects. No map location is inferred.</p>
    {cards.length ? <div className="impact-card-grid">{cards.map((item) => <article className="impact-card" key={item.name}><div className="impact-card-heading"><strong>{item.name}</strong><span>{item.count} headline{item.count === 1 ? "" : "s"}</span></div><small>Possible exposure channels: {item.channels}</small>{item.evidence.map((story) => <a key={story.url} href={story.url} target="_blank" rel="noreferrer">{story.title}<span>{story.publisher} ↗</span></a>)}</article>)}</div> : <div className="empty-note">No headlines in this snapshot matched these event themes. This does not mean the risks are absent.</div>}
  </section>;
}

function TrendRadar({ stories }: { stories: NewsStory[] }) {
  const count = stories.filter((story) => story.sentiment_score != null).length;
  return <section className="panel trend-radar"><div><span className="panel-kicker">MARKET INSTABILITY / TREND RADAR</span><h2>Composite score unavailable</h2><p>Do not infer a 0–100 score from one stream. Current inputs are shown with their coverage state.</p></div><div className="radar-score"><strong>—</strong><span>0–100 composite</span></div><div className="radar-inputs"><div><span className="radar-state observed" />Headline sentiment<strong>{count} scored</strong><small>English headlines in this snapshot</small></div><div><span className="radar-state missing" />Interest rates<strong>Unavailable</strong><small>No configured cross-country current-rate feed</small></div><div><span className="radar-state missing" />Retail buzz<strong>Unavailable</strong><small>WSB snapshot not joined to this country series</small></div></div></section>;
}

function ProTelemetry({ overview, stories, sources }: { overview: CountryOverview | null; stories: NewsStory[]; sources: SourceInfo[] }) {
  const availableSeriesCount = overview?.macro.filter((item) => item.status === "available").length ?? 0;
  return <section className="panel pro-panel"><div className="panel-title"><div><span className="panel-kicker">PRO QUANT MODE</span><h2>Source & coverage telemetry</h2></div><span className="availability-tag">{availableSeriesCount} macro series available</span></div>
    <div className="pro-tables"><div><h3>Current response evidence</h3><table><thead><tr><th>Series</th><th>Latest observation</th><th>Value</th><th>Source status</th></tr></thead><tbody>{overview?.macro.map((series) => <tr key={series.indicator}><td>{series.label}</td><td>{latest(series)?.period ?? "—"}</td><td>{fmt(latest(series)?.value, 2)} {series.unit}</td><td>{series.source.status}</td></tr>)}</tbody></table></div>
      <div><h3>Provider contract status</h3><table><thead><tr><th>Source</th><th>Domain</th><th>State</th><th>Cadence</th></tr></thead><tbody>{sources.map((source) => <tr key={source.id}><td><a href={source.url} target="_blank" rel="noreferrer">{source.name}</a></td><td>{source.domain}</td><td>{source.status}</td><td>{source.cadence}</td></tr>)}</tbody></table></div></div>
    <p className="muted">{stories.length} headlines currently loaded. Provider contract status is not a promise of coverage or exchange data entitlement.</p>
  </section>;
}

function ResearchView({ symbol, setSymbol, query, setQuery, onRunResearch, onRunForecast, busy, forecast, report, citations, trace, mode, rangeFrom, rangeTo, setRangeFrom, setRangeTo }: {
  symbol: string; setSymbol: (value: string) => void; query: string; setQuery: (value: string) => void;
  onRunResearch: (value: string) => Promise<void>; onRunForecast: () => Promise<void>; busy: boolean;
  forecast: ForecastResponse | null; report: Record<string, unknown> | null; citations: { provider?: string; url: string; retrieved_at?: string; status: string; record_id?: string }[]; trace: string[]; mode: "simple" | "pro";
  rangeFrom: string; rangeTo: string; setRangeFrom: (value: string) => void; setRangeTo: (value: string) => void;
}) {
  const historicalSharpe = useMemo(() => {
    const closes = forecast?.prices?.map((item) => item.close).filter((value): value is number => Number.isFinite(value) && value > 0) ?? [];
    const returns = closes.slice(1).map((value, index) => value / closes[index] - 1);
    if (returns.length < 30) return null;
    const mean = returns.reduce((sum, value) => sum + value, 0) / returns.length;
    const variance = returns.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (returns.length - 1);
    const deviation = Math.sqrt(variance);
    return deviation ? mean / deviation * Math.sqrt(252) : null;
  }, [forecast]);
  const chartRows = useMemo(() => {
    if (!forecast?.prices?.length) return [];
    const closes = forecast.prices.map((point) => point.close);
    const rows = forecast.prices.map((point, index) => ({
      date: point.date,
      history: point.close as number | null,
      movingAverage: index >= 19 ? closes.slice(index - 19, index + 1).reduce((sum, close) => sum + close, 0) / 20 : null,
      upper: null as number | null,
      lower: null as number | null,
    }));
    const last = rows.at(-1); if (!last) return rows;
    const horizons = forecast.forecasts?.horizons ?? [];
    for (const horizon of horizons) {
      const date = `+${horizon.horizon_days}d`;
      const movingAverage = closes.slice(-20).reduce((sum, close) => sum + close, 0) / Math.min(20, closes.length);
      rows.push({ date, history: null, movingAverage, upper: horizon.upper_95 ?? null, lower: horizon.lower_95 ?? null });
    }
    return rows;
  }, [forecast]);
  const [visibleIndicators, setVisibleIndicators] = useState({ movingAverage: true, upper: true, lower: true });
  const resetResearchFilters = () => {
    const today = new Date();
    setSymbol("NVDA");
    setRangeFrom(localDate(new Date(today.getFullYear() - 1, today.getMonth(), today.getDate())));
    setRangeTo(localDate(today));
    setQuery("");
    setVisibleIndicators({ movingAverage: true, upper: true, lower: true });
  };
  const centralHorizon = forecast?.forecasts?.horizons.find((row) => row.horizon_days === 30) ?? forecast?.forecasts?.horizons[0];
  const scenarioChange = centralHorizon ? (centralHorizon.base_price / centralHorizon.last_observed_price - 1) * 100 : null;
  const scenarioDirection = scenarioChange == null || Math.abs(scenarioChange) < 0.5 || !centralHorizon?.model_adds_signal ? "neutral" : scenarioChange > 0 ? "positive" : "negative";
  const volatility = forecast?.forecasts?.observed_annualized_volatility_pct;

  return <div className="research-layout"><section className="panel research-command"><div className="panel-title"><div><span className="panel-kicker">ASSET FORECAST LAB</span><h2>Historical proof before outlook</h2></div><span className="discovery-tag">No orders · research only</span></div>
    <div className="research-controls"><label>Asset or symbol<AssetAutocomplete value={symbol} onChange={setSymbol} /></label>
      <label>Historical data from<input type="date" value={rangeFrom} onChange={(event) => setRangeFrom(event.target.value)} /></label><label>Through<input type="date" value={rangeTo} onChange={(event) => setRangeTo(event.target.value)} /></label>
      <div className="research-actions"><button className="clear-filter-button" onClick={resetResearchFilters} disabled={busy}>Clear filters</button><button className="primary-button" onClick={() => void onRunForecast()} disabled={busy || !symbol.trim()}><Sparkles size={15} />{busy ? "Running…" : "Forecast 7 / 30 / 90d"}</button></div></div>
    <div className="preset-row">{ASSET_PRESETS.map((asset) => <button key={asset} className={symbol === asset ? "asset-pill active" : "asset-pill"} onClick={() => setSymbol(asset)}>{asset}</button>)}</div>
    <div className="research-question"><SearchBox value={query} onValueChange={setQuery} ariaLabel="Ask the research agent" placeholder="Search prompts or ask a question…" onSubmit={(text) => { void onRunResearch(text); }} onChoose={(suggestion) => {
      const text = (suggestion.query_template ?? (suggestion.kind === "sector" ? `Research recent news, sentiment, macro drivers and risks for the ${suggestion.value} sector` : ["asset", "commodity", "index"].includes(suggestion.kind) ? `Analyze ${suggestion.value} price history, sentiment, risk and 7/30/90-day scenarios` : suggestion.label))
        .replaceAll("{asset}", symbol).replaceAll("{country}", "World").replaceAll("{sector}", suggestion.value)
        .replaceAll("{date_from}", rangeFrom).replaceAll("{date_to}", rangeTo);
      setQuery(text);
      if (suggestion.kind === "prompt" || suggestion.kind === "macro") void onRunResearch(text);
    }} />{busy && <small className="muted">Research is in progress; current inputs are preserved.</small>}</div>
  </section>

  {busy && <div className="progress-card"><div className="loading-orbit" /><div><strong>Working through the evidence</strong><p>Provider calls are bounded and failures are recorded. This may take a moment.</p>{trace.slice(-3).map((item, i) => <small key={`${item}-${i}`}>{item}</small>)}</div></div>}

  {forecast?.status === "unavailable" && <div className="alert"><ShieldAlert size={17} />{forecast.error}</div>}
  {forecast?.forecasts && <>
    <div className="forecast-heading"><div><span className="panel-kicker">{symbol} · HISTORICAL MARKET DATA</span><h2>Price history & tested scenarios</h2><p>{forecast.forecasts.observations} observations · provider {forecast.price_source} · fetched {new Date(forecast.forecasts.generated_at).toLocaleString()}</p></div>{forecast.price_source_url ? <a className="source-pill" href={forecast.price_source_url} target="_blank" rel="noreferrer">{forecast.price_source ?? "Provider"} source ↗</a> : <span className="source-pill">{forecast.price_source ?? "Provider"} source</span>}</div>
    {mode === "simple" && <section className="panel simple-outlook"><div className="simple-signal"><span className={`traffic-badge ${scenarioDirection}`}>{scenarioDirection === "positive" ? "BASE CASE ABOVE" : scenarioDirection === "negative" ? "BASE CASE BELOW" : "NO VALIDATED DIRECTION"}</span><strong>{scenarioChange == null ? "Scenario not available" : `${scenarioChange >= 0 ? "+" : ""}${fmt(scenarioChange, 2)}%`}</strong><small>30-day model path · scenario, not a trade signal</small></div><div className="simple-evidence"><span className="panel-kicker">PLAIN-LANGUAGE EVIDENCE</span><p>1. The selected model&apos;s 30-day path is {scenarioChange == null ? "unavailable" : scenarioChange >= 0 ? "above" : "below"} the last observed close.</p><p>2. {centralHorizon?.model_adds_signal ? "Walk-forward evaluation beat the naïve baseline on the reported test metric." : "The selected model has not shown a reliable edge over the naïve baseline."}</p><p>3. Observed annualized volatility is {volatility == null ? "unavailable" : `${fmt(volatility, 1)}%`}; it describes recent variability, not a maximum-loss estimate.</p></div><div className="simple-risk"><span>HISTORICAL VOLATILITY SCALE</span><strong>{volatility == null ? "—" : `${fmt(volatility, 1)}%`}</strong><div className="risk-meter" role={volatility == null ? undefined : "meter"} aria-label="Observed annualized volatility percentage" aria-valuemin={volatility == null ? undefined : 0} aria-valuemax={volatility == null ? undefined : 100} aria-valuenow={volatility == null ? undefined : Math.min(100, Math.max(0, volatility))}><i style={{ width: `${Math.min(100, Math.max(0, volatility ?? 0))}%` }} /></div><small>Historical standard deviation, annualized · scale capped at 100%</small></div></section>}
    <div className="risk-summary"><div><span>Observed annualized volatility</span><strong>{forecast.forecasts.observed_annualized_volatility_pct == null ? "—" : `${fmt(forecast.forecasts.observed_annualized_volatility_pct, 1)}%`}</strong><small>Realized from {forecast.forecasts.risk_lookback_observations ?? "—"} recent observations</small></div><div><span>Observed maximum drawdown</span><strong>{forecast.forecasts.observed_max_drawdown_pct == null ? "—" : `${fmt(forecast.forecasts.observed_max_drawdown_pct, 1)}%`}</strong><small>Historical peak-to-trough · same lookback</small></div><div><span>Risk interpretation</span><strong>Historical context</strong><small>Descriptive risk measures; not a forecast or loss limit.</small></div></div>
    {mode === "pro" && <section className="pro-factor-grid"><div className="panel"><span className="panel-kicker">HISTORICAL RISK</span><strong>{historicalSharpe == null ? "—" : historicalSharpe.toFixed(2)}</strong><small>Annualized Sharpe-like ratio, zero risk-free rate assumption</small></div><div className="panel"><span className="panel-kicker">OPTIONS SKEW</span><strong>Unavailable</strong><small>No configured options surface provider</small></div><div className="panel"><span className="panel-kicker">ORDER-FLOW IMBALANCE</span><strong>Unavailable</strong><small>No order book / trade direction feed connected</small></div></section>}
    <section className="panel forecast-chart-panel"><div className="forecast-indicator-toolbar"><div className="chart-legend"><span className="legend-historical">Observed close</span></div><span className="indicator-label">INDICATORS</span><label><input type="checkbox" checked={visibleIndicators.movingAverage} onChange={(event) => setVisibleIndicators({ ...visibleIndicators, movingAverage: event.target.checked })} />Moving average</label><label><input type="checkbox" checked={visibleIndicators.upper} onChange={(event) => setVisibleIndicators({ ...visibleIndicators, upper: event.target.checked })} />Upper bound</label><label><input type="checkbox" checked={visibleIndicators.lower} onChange={(event) => setVisibleIndicators({ ...visibleIndicators, lower: event.target.checked })} />Lower bound</label><button className="clear-filter-button compact" onClick={() => setVisibleIndicators({ movingAverage: true, upper: true, lower: true })}>Clear filters</button></div>
      {chartRows.length > 0 && <ResponsiveContainer width="100%" height={390}><ComposedChart data={chartRows} margin={{ top: 15, right: 24, bottom: 5, left: 6 }}><CartesianGrid stroke="#263747" strokeDasharray="3 5" vertical={false} /><XAxis dataKey="date" stroke="#a8b6c4" tickLine={false} minTickGap={45} /><YAxis stroke="#a8b6c4" tickLine={false} axisLine={false} domain={["auto", "auto"]} tick={{ fill: "#cbd5e1", fontSize: 12 }} /><Tooltip contentStyle={{ background: "#111e2a", border: "1px solid #526477", borderRadius: 10, color: "#f1f5f9", fontSize: 13 }} /><ReferenceLine x={forecast.prices?.at(-1)?.date} stroke="#94a3b8" strokeDasharray="4 4" /><Line dataKey="history" name="Observed close" stroke="#38bdf8" strokeWidth={2.4} dot={false} connectNulls /><Line hide={!visibleIndicators.movingAverage} dataKey="movingAverage" name="20-observation moving average" stroke="#f59e0b" strokeWidth={2.5} dot={false} connectNulls /><Line hide={!visibleIndicators.upper} dataKey="upper" name="95% upper bound" stroke="#a78bfa" strokeWidth={2} strokeDasharray="5 4" connectNulls dot={{ r: 3 }} /><Line hide={!visibleIndicators.lower} dataKey="lower" name="95% lower bound" stroke="#fb7185" strokeWidth={2} strokeDasharray="5 4" connectNulls dot={{ r: 3 }} /></ComposedChart></ResponsiveContainer>}
      <p className="chart-caption">Upper and lower forecast bounds are empirical 95% ranges, shown only when at least 20 chronological calibration residuals are available. The moving-average line is a 20-observation historical indicator, held at its latest value over forecast dates; it is not the model forecast.</p>
    </section>
    <div className="horizon-grid">{forecast.forecasts.horizons.map((horizon) => <div className="panel horizon-card" key={horizon.horizon_days}><span className="panel-kicker">{horizon.horizon_days}-DAY SCENARIO</span><strong className="scenario-price">{fmt(horizon.base_price, 2)}</strong><small>Scenario change · {fmt((horizon.base_price / horizon.last_observed_price - 1) * 100, 2)}%</small><small>{horizon.selected_model.replaceAll("_", " ")}</small><div className={horizon.model_adds_signal ? "signal-label positive" : "signal-label neutral"}>{horizon.status}</div><div className="horizon-range">{horizon.lower_95 != null && horizon.upper_95 != null ? `95% historical range · ${fmt(horizon.lower_95, 2)} — ${fmt(horizon.upper_95, 2)}` : "95% range withheld · insufficient calibration residuals"}</div><div className="backtest-stats mae-stats"><span>Naïve baseline MAE<strong>{horizon.baseline_mae_pct == null ? "—" : `${fmt(horizon.baseline_mae_pct, 2)}%`}</strong></span><span>Selected model MAE<strong>{horizon.model_mae_pct == null ? "—" : `${fmt(horizon.model_mae_pct, 2)}%`}</strong></span></div></div>)}</div>
    <section className="panel model-method"><div className="panel-title"><div><span className="panel-kicker">METHOD + LIMITS</span><h2>What this forecast can say</h2></div><ShieldAlert size={18} /></div><p>{forecast.forecasts.method}</p>{forecast.forecasts.limitations.map((item) => <small key={item}>• {item}</small>)}<div className="forecast-citations"><span>Price source: {forecast.price_source ?? "unknown"}</span><span>Last observation: {forecast.prices?.at(-1)?.date ?? "unknown"}</span><span>Retrieval: {new Date(forecast.forecasts.generated_at).toLocaleString()}</span></div></section>
  </>}

  {report && <section className="panel report-panel"><div className="panel-title"><div><span className="panel-kicker">SOURCE-ATTRIBUTED RESEARCH</span><h2>Agent readout</h2></div><span className="signal-label neutral">No trade recommendation</span></div><p>{String(report.executive_summary ?? "")}</p><div className="report-grid"><div><h3>Evidence and findings</h3>{(report.key_findings as string[] | undefined)?.map((item) => <p key={item}>• {item}</p>)}</div><div><h3>Reported risks</h3>{(report.risks as string[] | undefined)?.map((item) => <p key={item}>• {item}</p>)}</div></div><div className="research-citations"><h3>Provider records</h3>{citations.filter((item) => item.url).map((item, index) => <a key={`${item.provider}-${index}`} href={item.url} target="_blank" rel="noreferrer">{item.provider ?? "Provider"} · {item.status}{item.retrieved_at ? ` · ${new Date(item.retrieved_at).toLocaleString()}` : ""} ↗</a>)}</div>{mode === "pro" && <><details><summary>Agent execution trace</summary>{trace.map((item, i) => <code className="trace-line" key={`${i}-${item}`}>{item}</code>)}</details><details><summary>Raw provider responses and rate-limit metadata</summary>{(report.tool_results as Record<string, unknown>[] | undefined)?.map((item, i) => <pre className="raw-payload" key={`${i}-${String(item.provider)}`}><strong>{String(item.provider)} · {item.ok ? "success" : "unavailable"} · rate remaining {String(item.rate_limit_remaining ?? "not supplied")}</strong>{JSON.stringify(item, null, 2)}</pre>)}</details></>}</section>}
  {!forecast && !report && !busy && <div className="empty-state large-empty"><LineChart size={25} /><strong>Start with a symbol or a research prompt</strong><span>Predictions require dated historical price observations from a configured provider.</span></div>}
  <div className="mobile-prediction-bar"><span>Asset: <strong>{symbol || "Select a ticker"}</strong></span><button className="primary-button" onClick={() => void onRunForecast()} disabled={busy || !symbol.trim()}><Sparkles size={16} />{busy ? "Working…" : "Make prediction"}</button></div>
  </div>;
}

function TaxView({ iso3, countryName, startYear, endYear, estimate, setEstimate, taxError, setTaxError, taxPolicy, setTaxPolicy }: {
  iso3: string; countryName: string; startYear: number; endYear: number; estimate: TaxEstimate | null;
  setEstimate: (value: TaxEstimate | null) => void; taxError: string; setTaxError: (value: string) => void;
  taxPolicy: Record<string, unknown> | null; setTaxPolicy: (value: Record<string, unknown> | null) => void;
}) {
  const [taxStories, setTaxStories] = useState<NewsStory[]>([]);
  useEffect(() => {
    getTaxPolicy(iso3, startYear, endYear).then((data) => setTaxPolicy(data as unknown as Record<string, unknown>)).catch((error: unknown) => setTaxError(error instanceof Error ? error.message : "Tax policy feed unavailable."));
    getNews(iso3, "tax policy OR tax legislation").then((data) => setTaxStories(data.stories)).catch(() => setTaxStories([]));
  }, [iso3, startYear, endYear, setTaxPolicy, setTaxError]);
  async function calculate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setTaxError(""); setEstimate(null);
    const form = new FormData(event.currentTarget);
    const payload = { asset_type: form.get("asset_type"), acquisition_date: form.get("acquisition_date"), transfer_date: form.get("transfer_date"), purchase_value_inr: Number(form.get("purchase_value_inr")), sale_value_inr: Number(form.get("sale_value_inr")), eligible_costs_inr: Number(form.get("eligible_costs_inr") || 0), stt_eligible: form.get("stt_eligible") === "on", prior_112a_gains_inr: Number(form.get("prior_112a_gains_inr") || 0), tax_year: "FY2025-26" };
    try { setEstimate(await submitTaxEstimate(payload)); }
    catch (caught) { setTaxError(caught instanceof Error ? caught.message : "Estimate unavailable."); }
  }
  const revenue = taxPolicy?.tax_revenue_series as { observations?: { period: string; value: number }[]; source?: { url: string; name: string } } | undefined;
  return <div className="tax-layout"><section className="panel tax-country"><div className="panel-title"><div><span className="panel-kicker">PUBLIC FISCAL OBSERVATIONS</span><h2>{countryName} tax context</h2></div><span className="availability-tag">{iso3}</span></div>
    <p className="muted">Tax revenue as a share of GDP is a macroeconomic measure; it is not a personal tax rate or liability.</p>
    {revenue?.observations?.length ? <ResponsiveContainer width="100%" height={250}><ReLineChart data={revenue.observations}><CartesianGrid stroke="#263747" strokeDasharray="3 5" vertical={false} /><XAxis dataKey="period" stroke="#8395a5" /><YAxis stroke="#8395a5" /><Tooltip contentStyle={{ background: "#111e2a", border: "1px solid #344858" }} /><Line dataKey="value" name="Tax revenue · % GDP" stroke="#38bdf8" dot={false} /></ReLineChart></ResponsiveContainer> : <div className="empty-note">Official tax-revenue observations are unavailable for this country/range.</div>}
    {revenue?.source && <SourceBadge name={revenue.source.name} url={revenue.source.url} />}
    <h3>Statutory policy coverage</h3><p>{String(taxPolicy?.statutory_rates_status ?? "loading") === "not_catalogued" ? "Country-specific statutory rates are not yet catalogued here. No rate is inferred from tax-revenue statistics." : "Official tax policy entry available for this country. Verify the cited tax year."}</p>
    {typeof taxPolicy?.official_policy_url === "string" && <a className="secondary-button inline-link" href={taxPolicy.official_policy_url} target="_blank" rel="noreferrer">Open official policy ↗</a>}
    <div className="tax-caveat"><ShieldAlert size={16} /><span>This is a research aid; tax law changes by year and personal circumstances. Review official guidance.</span></div>
    <h3>Recent tax-policy headlines</h3><div className="news-list">{taxStories.slice(0, 4).map((story) => <NewsRow key={story.url} story={story} />)}{!taxStories.length && <p className="empty-note">No matching indexed headlines are available for this query.</p>}</div>
  </section>
  <section className="panel tax-calc"><div className="panel-title"><div><span className="panel-kicker">RULE-VALIDATED SCOPE</span><h2>India listed investment estimate</h2></div><span className="source-pill">FY 2025–26 only</span></div>
    <p className="muted">Resident individuals · listed shares/equity-oriented funds · eligible STT cases · transfers after 23 July 2024.</p>
    <form className="tax-form" onSubmit={(event) => void calculate(event)}>
      <label>Asset type<select name="asset_type"><option value="listed_equity">Listed equity share</option><option value="equity_oriented_fund">Equity-oriented mutual fund</option></select></label>
      <label>Acquired<input name="acquisition_date" type="date" defaultValue="2025-01-10" required /></label><label>Transferred<input name="transfer_date" type="date" defaultValue="2025-09-10" required min="2024-07-23" max="2026-03-31" /></label>
      <label>Purchase value · ₹<input name="purchase_value_inr" type="number" min="0.01" step="0.01" defaultValue="100000" required /></label><label>Sale value · ₹<input name="sale_value_inr" type="number" min="0.01" step="0.01" defaultValue="125000" required /></label>
      <label>Eligible costs · ₹<input name="eligible_costs_inr" type="number" min="0" step="0.01" defaultValue="0" /></label><label>Prior section 112A gains this year · ₹<input name="prior_112a_gains_inr" type="number" min="0" step="0.01" defaultValue="0" /></label>
      <label className="checkbox-label"><input name="stt_eligible" type="checkbox" required /> Eligible Securities Transaction Tax paid</label>
      <button className="primary-button" type="submit">Estimate capital-gains component</button>
    </form>
    {taxError && <div className="alert error-alert"><ShieldAlert size={16} />{taxError}</div>}
    {estimate && <div className="estimate-result"><span className="panel-kicker">ESTIMATED TAX COMPONENT · NOT TOTAL TAX</span><strong>₹{fmt(estimate.estimated_tax_before_surcharge_cess_inr, 2)}</strong><div>{estimate.gain_type.replace("_", " ")} · {estimate.applicable_rate_pct}% · taxable gain ₹{fmt(estimate.taxable_gain_inr, 2)}</div>{estimate.assumptions.map((item) => <small key={item}>• {item}</small>)}{estimate.citations.map((cite) => <SourceBadge key={cite.source_id} name={cite.name} url={cite.url} />)}</div>}
    <p className="disclaimer-small">Excludes surcharge, cess, losses, rebates, other income, non-resident/treaty rules and filing adjustments. Not tax advice. Tax inputs stay in the local browser/API process and are never sent to the LLM.</p>
  </section></div>;
}

function SourceBadge({ name, url }: { name: string; url: string }) {
  return <a className="source-badge" href={url} target="_blank" rel="noreferrer"><BookOpenCheck size={13} />{name}<ArrowUpRight size={12} /></a>;
}

function SourcesView({ sources, overview, stories, dataStatus }: { sources: SourceInfo[]; overview: CountryOverview | null; stories: NewsStory[]; dataStatus: { providers: Record<string, { ready: boolean; note: string }>; forecast_requirements: string[]; marketstack_key_configured: boolean; alphavantage_key_configured: boolean } | null }) {
  const priceConfigured = Boolean(dataStatus?.marketstack_key_configured || dataStatus?.alphavantage_key_configured);
  const priceSourceName = dataStatus?.marketstack_key_configured ? "Marketstack" : "Alpha Vantage";
  return <div className="sources-layout"><section className="panel"><div className="panel-title"><div><span className="panel-kicker">TRANSPARENT BY DEFAULT</span><h2>Coverage & source contracts</h2></div><span className="source-pill">{sources.length} catalog entries</span></div><p className="muted">An entry may be catalogued without a verified live adapter. The status column distinguishes those states.</p>
    <div className={priceConfigured ? "setup-banner configured" : "setup-banner"}><div><strong>{priceConfigured ? "Price history source configured" : "Forecast data setup required"}</strong><p>{priceConfigured ? `${priceSourceName} key detected. Access still follows your plan, quota and symbol coverage.` : "Add MARKETSTACK_API_KEY or ALPHAVANTAGE_API_KEY in the project .env, then restart the backend. The app does not store provider keys in the browser."}</p><small>Marketstack free: EOD · 12 months · 100 requests/month. Alpha Vantage free: daily · compact latest 100 observations.</small></div><a href="https://www.alphavantage.co/support/#api-key" target="_blank" rel="noreferrer">Get a free key ↗</a></div>
    <ApiManagement />
    <div className="provider-status-grid">{Object.entries(dataStatus?.providers ?? {}).map(([name, item]) => <div className="provider-status" key={name}><span className={item.ready ? "status-dot" : "status-dot status-dot-off"} /><div><strong>{name}</strong><small>{item.ready ? "Configured / public" : "Needs configuration"} · {item.note}</small></div></div>)}</div>
    <div className="source-table-wrap"><table><thead><tr><th>Source</th><th>Domain</th><th>Adapter status</th><th>Freshness</th><th>Access</th></tr></thead><tbody>{sources.map((source) => { const verified = source.status === "implemented" || source.status.startsWith("documented-adapter") || source.status === "configured-adapter"; return <tr key={source.id}><td><a href={source.url} target="_blank" rel="noreferrer">{source.name} ↗</a></td><td>{source.domain}</td><td><span className={`status-tag ${verified ? "status-good" : "status-warn"}`}>{source.status}</span></td><td>{source.cadence}</td><td>{source.key}</td></tr>; })}</tbody></table></div></section>
    <div className="source-summary-grid"><div className="panel"><span className="panel-kicker">COUNTRY DATA</span><strong>{overview?.macro.filter((series) => series.status === "available").length ?? 0}/{overview?.macro.length ?? 0}</strong><small>macro series available in current country snapshot</small></div><div className="panel"><span className="panel-kicker">NEWS ITEMS</span><strong>{stories.length}</strong><small>country stories loaded with source URLs</small></div><div className="panel"><span className="panel-kicker">MARKET PRICE COVERAGE</span><strong>Partial</strong><small>availability depends on free provider access and instrument</small></div></div>
    <section className="panel"><div className="panel-title"><div><span className="panel-kicker">OBSERVATION PROVENANCE</span><h2>Current macro sources</h2></div></div><div className="news-list">{overview?.macro.map((series) => <article className="source-observation" key={series.indicator}><div><strong>{series.label}</strong><small>{series.indicator} · {series.unit} · latest {series.observations.at(-1)?.period ?? "none"}</small></div><span className={`status-tag ${series.status === "available" ? "status-good" : "status-warn"}`}>{series.source.status}</span><a href={series.source.url} target="_blank" rel="noreferrer">Data ↗</a></article>)}</div></section>
  </div>;
}
