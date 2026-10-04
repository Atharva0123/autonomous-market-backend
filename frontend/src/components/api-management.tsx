"use client";

import { KeyRound, RefreshCw, Save, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { getProviderManagement, saveProviderManagement, type ProviderManagement } from "@/lib/api";
import { ApiTester } from "@/components/api-tester";

export function ApiManagement() {
  const [settings, setSettings] = useState<ProviderManagement | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const refresh = async () => {
    setBusy(true);
    setError("");
    try { setSettings(await getProviderManagement()); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Could not read administrator API settings."); }
    finally { setBusy(false); }
  };

  useEffect(() => { void refresh(); }, []);

  async function save() {
    if (!settings) return;
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      setSettings(await saveProviderManagement({
        price_provider: settings.price_provider,
        automatic_failover: settings.automatic_failover,
        enabled_providers: settings.enabled_providers,
      }));
      setSaved(true);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not save API preferences."); }
    finally { setBusy(false); }
  }

  return <section className="panel api-management">
    <div className="panel-title"><div><span className="panel-kicker">ADMIN · {settings?.admin_username ?? "ATHARVAKH"}</span><h2>API management</h2></div><span className="source-pill"><ShieldCheck size={12} /> Private controls</span></div>
    <p className="muted">Choose the equity history source, set automatic quota failover, and enable or disable registered research providers. This panel never displays or stores API-key values. Settings storage: {settings?.persistence_mode ?? "checking"}.</p>
    {error && <div className="alert error-alert" role="alert">{error}</div>}
    {!settings && !error && <p className="muted">Loading protected provider settings…</p>}
    {settings && <>
      <div className="price-routing-grid">
        <label className="price-route-control">Preferred equity history provider
          <select aria-label="Preferred equity history provider" value={settings.price_provider} onChange={(event) => { setSaved(false); setSettings({ ...settings, price_provider: event.target.value as ProviderManagement["price_provider"] }); }}>
            <option value="auto">Automatic · Marketstack then Alpha Vantage</option>
            <option value="Marketstack">Marketstack first</option>
            <option value="Alpha Vantage">Alpha Vantage first</option>
          </select>
        </label>
        <label className="failover-control"><input type="checkbox" checked={settings.automatic_failover} onChange={(event) => { setSaved(false); setSettings({ ...settings, automatic_failover: event.target.checked }); }} />
          <span><strong>Automatic failover</strong><small>Try the next enabled source on quota exhaustion, provider errors, or empty history.</small></span>
        </label>
      </div>
      <div className="provider-admin-grid">{settings.providers.map((provider) => <label className="provider-admin-row" key={provider.name}>
        <input type="checkbox" checked={provider.enabled} onChange={(event) => { setSaved(false); setSettings({ ...settings, enabled_providers: { ...settings.enabled_providers, [provider.name]: event.target.checked }, providers: settings.providers.map((item) => item.name === provider.name ? { ...item, enabled: event.target.checked } : item) }); }} />
        <span className="provider-admin-copy"><strong>{provider.name}</strong><small><i className={provider.ready ? "ready-dot" : "ready-dot not-ready"} />{provider.ready ? "Configured / public" : "Not configured"} · {provider.note}</small></span>
      </label>)}</div>
      <div className="api-management-foot"><span><KeyRound size={13} /> Keys stay server-side in environment secrets.</span><div>{saved && <small className="saved-note">Preferences saved.</small>}<button className="secondary-button" onClick={() => void refresh()} disabled={busy}><RefreshCw size={13} />Refresh</button><button className="primary-button" onClick={() => void save()} disabled={busy}><Save size={13} />{busy ? "Saving…" : "Save API settings"}</button></div></div>
      <p className="api-key-guidance">To add or rotate a key, set its provider environment variable in the API host’s private environment settings, then restart/redeploy the backend. Never use a <code>NEXT_PUBLIC_</code> variable for a secret.</p>
      <ApiTester providers={settings.providers} />
    </>}
  </section>;
}
