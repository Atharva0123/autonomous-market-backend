"use client";

import { ArrowRight, BarChart3, Globe2, Search, WalletCards } from "lucide-react";
import { useEffect } from "react";
import { SearchBox } from "@/components/search-box";
import type { Suggestion } from "@/lib/types";

type Props = { open: boolean; onClose: () => void; onChoose: (item: Suggestion) => void; onSubmit: (query: string) => void; onNavigate: (page: "pulse" | "research" | "tax" | "sources") => void };

export function CommandPalette({ open, onClose, onChoose, onSubmit, onNavigate }: Props) {
  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => document.querySelector<HTMLInputElement>(".command-palette .search-wrap input")?.focus(), 0);
    return () => window.clearTimeout(timer);
  }, [open]);
  if (!open) return null;
  return <div className="command-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="command-palette" role="dialog" aria-modal="true" aria-labelledby="command-title">
      <div className="command-title"><div><span className="panel-kicker">MARKET DESK COMMAND</span><h2 id="command-title">Jump to research</h2></div><kbd>ESC</kbd></div>
      <SearchBox onChoose={(item) => { onChoose(item); onClose(); }} onSubmit={(query) => { onSubmit(query); onClose(); }} placeholder="Search assets, countries, macro, or a prompt…" ariaLabel="Search command palette" />
      <div className="command-shortcuts"><button onClick={() => { onNavigate("pulse"); onClose(); }}><Globe2 size={16} /><span>Global Pulse</span><ArrowRight size={14} /></button><button onClick={() => { onNavigate("research"); onClose(); }}><BarChart3 size={16} /><span>Asset Research</span><ArrowRight size={14} /></button><button onClick={() => { onNavigate("tax"); onClose(); }}><WalletCards size={16} /><span>Tax & Policy</span><ArrowRight size={14} /></button><button onClick={() => { onNavigate("sources"); onClose(); }}><Search size={16} /><span>Data Sources</span><ArrowRight size={14} /></button></div>
      <div className="command-foot"><span>Navigate with ↑ ↓ and Enter</span><span>Ctrl K / ⌘ K</span></div>
    </section>
  </div>;
}
