"use client";

import dynamic from "next/dynamic";

const WorldGlobe = dynamic(() => import("@/components/world-globe"), {
  ssr: false,
  loading: () => <div className="globe-loading">Rendering country globe…</div>,
});

export function GlobePanel({ selected, onSelect }: { selected: string; onSelect: (iso3: string) => void }) {
  return <WorldGlobe selected={selected} onSelect={onSelect} />;
}
