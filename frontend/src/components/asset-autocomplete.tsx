"use client";

import { useEffect, useState } from "react";
import { getSuggestions } from "@/lib/api";
import type { Suggestion } from "@/lib/types";

export function AssetAutocomplete({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [items, setItems] = useState<Suggestion[]>([]);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (!value.trim()) { setItems([]); return; }
      getSuggestions(value).then((rows) => setItems(rows.filter((item) => ["asset", "commodity", "index"].includes(item.kind)))).catch(() => setItems([]));
    }, 150);
    return () => window.clearTimeout(timer);
  }, [value]);
  return <>
    <input value={value} onChange={(event) => {
      const typed = event.target.value;
      const match = items.find((item) => item.label === typed);
      onChange((match?.value ?? typed).toUpperCase());
    }} maxLength={20} placeholder="NVDA, ^NSEI, BTC-USD" list="market-symbol-suggestions" autoComplete="off" />
    <datalist id="market-symbol-suggestions">{items.map((item) => <option key={`${item.kind}-${item.value}`} value={item.value}>{item.label} · {item.description}</option>)}</datalist>
  </>;
}
