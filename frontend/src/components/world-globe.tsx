"use client";

import dynamic from "next/dynamic";
import countryMetadata from "world-countries";
import worldTopology from "world-atlas/countries-110m.json";
import { feature } from "topojson-client";
import type { Feature, FeatureCollection, MultiPolygon, Polygon } from "geojson";
import type { Topology } from "topojson-specification";
import { useEffect, useMemo, useRef, useState } from "react";

type CountryProperties = Record<string, unknown> & { cca3: string; common_name: string };
type GeoCountry = Feature<Polygon | MultiPolygon, CountryProperties>;
const Globe = dynamic(() => import("react-globe.gl"), { ssr: false,
  loading: () => <div className="globe-loading">Preparing 3D globe…</div> });

type Props = { selected: string; onSelect: (iso3: string) => void };

function featureProperties(feature: object): Record<string, unknown> {
  const properties = (feature as { properties?: unknown }).properties;
  return properties && typeof properties === "object" ? properties as Record<string, unknown> : {};
}

function countryCode(feature: object): string | null {
  // Globe polygon objects may be passed as the GeoJSON feature or as the
  // original world-countries record, depending on the rendering path.
  const properties = featureProperties(feature);
  const root = feature as { cca3?: unknown };
  const code = properties.cca3 ?? root.cca3;
  return typeof code === "string" && /^[A-Z]{3}$/.test(code) && code !== "ATA" ? code : null;
}

function flatCountryPath(country: GeoCountry, width = 360, height = 180): string {
  const polygons = country.geometry?.type === "Polygon" ? [country.geometry.coordinates] :
    country.geometry?.type === "MultiPolygon" ? country.geometry.coordinates : [];
  return polygons.map((polygon) => polygon.map((ring) => {
    const stride = Math.max(1, Math.ceil(ring.length / 90));
    const points = ring.filter((_, index) => index % stride === 0 || index === ring.length - 1);
    return points.map(([longitude, latitude], index) => `${index ? "L" : "M"}${((longitude + 180) / 360 * width).toFixed(1)},${((90 - latitude) / 180 * height).toFixed(1)}`).join(" ") + " Z";
  }).join(" ")).join(" ");
}

export default function WorldGlobe({ selected, onSelect }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(620);
  const [hovered, setHovered] = useState("");
  const [flatMobile, setFlatMobile] = useState(false);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(max-width: 639px)");
    const update = () => setFlatMobile(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (!container.current || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(260, Math.min(620, Math.floor(entry.contentRect.width)))));
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  const polygons = useMemo(() => {
    // world-countries contains ISO metadata but no shapes. Join it to the
    // Natural Earth TopoJSON polygons by numeric ISO code so clicks can be
    // hit-tested and resolve to the same ISO-3 IDs used by the API.
    const metadata = countryMetadata as unknown as { cca3: string; ccn3: string; name: { common: string } }[];
    const byNumericCode = new Map(metadata.map((country) => [country.ccn3.padStart(3, "0"), country]));
    const byName = new Map(metadata.map((country) => [country.name.common.toLowerCase(), country]));
    const collection = feature(
      worldTopology as unknown as Topology,
      (worldTopology as unknown as Topology).objects.countries,
    ) as FeatureCollection<Polygon | MultiPolygon, Record<string, unknown>>;
    return collection.features.flatMap((country): GeoCountry[] => {
      if (!country.geometry || country.properties?.name === "Antarctica") return [];
      const code = typeof country.id === "string" || typeof country.id === "number"
        ? String(country.id).padStart(3, "0") : "";
      const item = byNumericCode.get(code)
        ?? byName.get(String(country.properties?.name ?? "").toLowerCase());
      if (!item) return [];
      return [{ ...country, properties: { ...country.properties, cca3: item.cca3, common_name: item.name.common } as CountryProperties }];
    });
  }, []);
  const mobilePaths = useMemo(() => new Map(polygons.map((country) =>
    [String(country.properties.cca3), flatCountryPath(country)])), [polygons]);

  if (flatMobile) {
    const width = 360, height = 180;
    return <div className="globe-canvas flat-world-map" role="group" aria-label="Interactive flat world map. Select a country, or use the country search control.">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="World map country selector">
        <rect width={width} height={height} rx="12" className="map-ocean" />
        {polygons.map((country) => {
          const code = String(country.properties.cca3);
          return <path key={code} d={mobilePaths.get(code)} aria-label={`Select ${country.properties.common_name}`} role="button" tabIndex={0}
            className={code === selected ? "map-country selected" : "map-country"}
            onClick={() => onSelect(code)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(code); } }} />;
        })}
      </svg>
      <span className="flat-map-hint">Tap a country or use country search below</span>
    </div>;
  }

  return (
    <div className="globe-canvas" ref={container} aria-label="Interactive 3D globe. Select a country to open its financial dashboard.">
      <Globe
        width={width}
        height={Math.round(width * 0.64)}
        backgroundColor="rgba(0,0,0,0)"
        globeImageUrl="/assets/earth-night.jpg"
        bumpImageUrl="/assets/earth-topology.png"
        polygonsData={polygons}
        polygonAltitude={(feature) => { const iso = String(featureProperties(feature).cca3 ?? ""); return iso === selected ? 0.032 : iso === hovered ? 0.018 : 0.008; }}
        polygonCapColor={(feature) => { const iso = String(featureProperties(feature).cca3 ?? ""); return iso === selected ? "rgba(56,189,248,0.88)" : iso === hovered ? "rgba(56,189,248,0.48)" : "rgba(125,148,182,0.24)"; }}
        polygonSideColor={() => "rgba(37,99,235,0.18)"}
        polygonStrokeColor={() => "rgba(148,163,184,0.38)"}
        polygonLabel={(feature) => `<div class="globe-label">Select ${String(featureProperties(feature).common_name ?? "country")}<br/><small>${String(featureProperties(feature).cca3 ?? "")}</small></div>`}
        onPolygonHover={(feature) => setHovered(feature ? String(featureProperties(feature).cca3 ?? "") : "")}
        onPolygonClick={(feature) => { const iso = countryCode(feature); if (iso) onSelect(iso); }}
        polygonsTransitionDuration={180}
        atmosphereColor="#2563eb"
        atmosphereAltitude={0.16}
        showGraticules
        enablePointerInteraction
        animateIn
      />
    </div>
  );
}
