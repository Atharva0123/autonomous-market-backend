import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CountryPicker } from "@/components/country-picker";

const globeProps = vi.hoisted(() => ({
  onPolygonClick: undefined as undefined | ((feature: object) => void),
  polygonsData: [] as { properties?: { cca3?: string } }[],
}));
vi.mock("react-globe.gl", () => ({
  default: (props: { onPolygonClick: (feature: object) => void; polygonsData: { properties?: { cca3?: string } }[] }) => {
    globeProps.onPolygonClick = props.onPolygonClick;
    globeProps.polygonsData = props.polygonsData;
    return <button onClick={() => props.onPolygonClick({ properties: { cca3: "IND" } })}>Mock India polygon</button>;
  },
}));

import WorldGlobe from "@/components/world-globe";

afterEach(cleanup);

describe("country exploration", () => {
  it("keeps an accessible picker as a keyboard-friendly globe fallback", () => {
    const onSelect = vi.fn();
    render(<CountryPicker countries={[{ iso2: "IN", iso3: "IND", name: "India" }]} selected="WLD" onSelect={onSelect} />);
    const picker = screen.getByRole("combobox", { name: "Select country" });
    expect((picker as HTMLSelectElement).value).toBe("WLD");
    fireEvent.change(picker, { target: { value: "IND" } });
    expect(onSelect).toHaveBeenCalledWith("IND");
  });

  it("selects a country when its globe polygon is clicked", async () => {
    const onSelect = vi.fn();
    render(<WorldGlobe selected="WLD" onSelect={onSelect} />);
    fireEvent.click(await screen.findByRole("button", { name: "Mock India polygon" }));
    expect(onSelect).toHaveBeenCalledWith("IND");
    expect(globeProps.onPolygonClick).toBeTypeOf("function");
  });

  it("selects a country when the globe returns its original country record", () => {
    const onSelect = vi.fn();
    render(<WorldGlobe selected="WLD" onSelect={onSelect} />);
    globeProps.onPolygonClick?.({ cca3: "JPN" });
    expect(onSelect).toHaveBeenCalledWith("JPN");
  });

  it("provides real country geometry with ISO codes to the globe for hit testing", () => {
    render(<WorldGlobe selected="WLD" onSelect={vi.fn()} />);
    expect(globeProps.polygonsData.length).toBeGreaterThan(150);
    expect(globeProps.polygonsData.find((polygon) => polygon.properties?.cca3 === "IND")).toBeDefined();
  });
});
