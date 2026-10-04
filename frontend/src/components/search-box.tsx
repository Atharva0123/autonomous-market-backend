"use client";

import { ArrowUpRight, Search } from "lucide-react";
import { useEffect, useId, useState } from "react";
import type { KeyboardEvent } from "react";
import { getSuggestions } from "@/lib/api";
import type { Suggestion } from "@/lib/types";

type Props = { onChoose: (suggestion: Suggestion) => void; onSubmit: (query: string) => void; placeholder?: string; ariaLabel?: string; value?: string; onValueChange?: (value: string) => void };

export function SearchBox({ onChoose, onSubmit, placeholder = "Search countries, tickers, sectors, macro…", ariaLabel = "Search markets and research prompts", value: controlledValue, onValueChange }: Props) {
  const [internalValue, setInternalValue] = useState("");
  const value = controlledValue ?? internalValue;
  const [items, setItems] = useState<Suggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [recent, setRecent] = useState<string[]>([]);
  const searchId = useId();
  const updateValue = (next: string) => { setInternalValue(next); onValueChange?.(next); };

  useEffect(() => {
    try { setRecent(JSON.parse(window.localStorage.getItem("marketdesk-recent-searches") ?? "[]") as string[]); }
    catch { setRecent([]); }
  }, []);

  function remember(text: string) {
    const next = [text.trim(), ...recent.filter((item) => item.toLowerCase() !== text.trim().toLowerCase())].slice(0, 6);
    setRecent(next);
    try { window.localStorage.setItem("marketdesk-recent-searches", JSON.stringify(next)); } catch { /* Recent search history is optional. */ }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      getSuggestions(value).then(setItems).catch(() => setItems([]));
    }, 300);
    return () => window.clearTimeout(timer);
  }, [value]);

  function select(item: Suggestion) {
    updateValue(item.label);
    setOpen(false);
    remember(item.query_template ?? item.value);
    onChoose(item);
  }

  function submit(text: string) { const clean = text.trim(); setOpen(false); if (clean) remember(clean); onSubmit(clean); }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") { event.preventDefault(); setOpen(true); if (items.length) setActive((index) => (index + 1) % items.length); }
    if (event.key === "ArrowUp") { event.preventDefault(); if (items.length) setActive((index) => (index <= 0 ? items.length - 1 : index - 1)); }
    if (event.key === "Escape") setOpen(false);
    if (event.key === "Enter") {
      event.preventDefault();
      if (open && items[active]) select(items[active]);
      else submit(value);
    }
  }

  return (
    <div className="search-wrap">
      <Search size={18} aria-hidden="true" />
      <input value={value} placeholder={placeholder} aria-label={ariaLabel}
        role="combobox" aria-autocomplete="list" aria-controls={`${searchId}-suggestions`} aria-expanded={open}
        aria-activedescendant={open && items[active] ? `${searchId}-suggestion-${active}` : undefined} onFocus={() => setOpen(true)}
        onChange={(event) => { updateValue(event.target.value); setOpen(true); setActive(-1); }} onKeyDown={handleKeyDown} />
      <button className="search-action" type="button" aria-label="Submit research search" onClick={() => submit(value)}>
        <ArrowUpRight size={16} />
      </button>
      {open && (items.length > 0 || (!value.trim() && recent.length > 0)) && <div className="suggestions" id={`${searchId}-suggestions`} role="listbox">
        {!value.trim() && recent.length > 0 && <><div className="suggestion-group-label">RECENT SEARCHES</div>{recent.map((entry) => <button className="suggestion recent-suggestion" key={entry} role="option" aria-selected={false} onMouseDown={(event) => event.preventDefault()} onClick={() => { updateValue(entry); submit(entry); }}><span className="suggestion-kind">recent</span><span><strong>{entry}</strong><small>Run this query again</small></span></button>)}</>}
        {items.length > 0 && <div className="suggestion-group-label">{value.trim() ? "MATCHING ASSETS, COUNTRIES & TOPICS" : "TRENDING RESEARCH"}</div>}
        {items.map((item, index) => <button id={`${searchId}-suggestion-${index}`} key={`${item.kind}-${item.value}-${item.label}`} role="option"
          aria-selected={active === index} className={`suggestion ${active === index ? "suggestion-active" : ""}`}
          onMouseEnter={() => setActive(index)} onMouseDown={(event) => event.preventDefault()} onClick={() => select(item)}>
          <span className={`suggestion-kind kind-${item.kind}`}>{item.kind === "asset" || item.kind === "commodity" || item.kind === "index" ? "asset" : item.kind === "macro" ? "macro" : item.kind}</span><span><strong>{item.label}</strong><small>{item.description}</small></span>
        </button>)}
      </div>}
      {open && <button className="suggestions-dismiss" aria-label="Close search suggestions" onClick={() => setOpen(false)} />}
    </div>
  );
}
