"use client";

import { ChevronDown, Globe2 } from "lucide-react";
import type { Country } from "@/lib/types";

export function CountryPicker({ countries, selected, onSelect }: {
  countries: Country[]; selected: string; onSelect: (country: string) => void;
}) {
  return <div className="country-control"><Globe2 size={16} /><select aria-label="Select country" value={selected} onChange={(event) => onSelect(event.target.value)}>
    <option value="WLD">🌐 World</option>{countries.map((item) => <option key={item.iso3} value={item.iso3}>{item.name}</option>)}
  </select><ChevronDown size={14} /></div>;
}
