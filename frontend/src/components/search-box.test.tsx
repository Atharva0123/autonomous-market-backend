import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SearchBox } from "@/components/search-box";

vi.mock("@/lib/api", () => ({
  getSuggestions: vi.fn(async () => [
    { kind: "asset", label: "NVIDIA (NVDA)", value: "NVDA", description: "Market asset" },
    { kind: "country", label: "India", value: "IND", description: "Country" },
  ]),
}));

afterEach(cleanup);

describe("SearchBox accessible hybrid autocomplete", () => {
  it("supports keyboard selection from suggestions", async () => {
    const choose = vi.fn();
    render(<SearchBox onChoose={choose} onSubmit={vi.fn()} />);
    const input = screen.getByRole("combobox", { name: "Search markets and research prompts" });
    fireEvent.change(input, { target: { value: "NV" } });
    await waitFor(() => expect(screen.getByRole("option", { name: /NVIDIA/ })).toBeTruthy());
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(choose).toHaveBeenCalledWith(expect.objectContaining({ kind: "asset", value: "NVDA" }));
    expect(input).toHaveValue("NVIDIA (NVDA)");
  });

  it("supports pointer selection and free-form research submission", async () => {
    const choose = vi.fn();
    const submit = vi.fn();
    render(<SearchBox onChoose={choose} onSubmit={submit} />);
    const input = screen.getByRole("combobox", { name: "Search markets and research prompts" });
    fireEvent.change(input, { target: { value: "India" } });
    await waitFor(() => expect(screen.getByRole("option", { name: /India/ })).toBeTruthy());
    fireEvent.click(screen.getByRole("option", { name: /India/ }));
    expect(choose).toHaveBeenCalledWith(expect.objectContaining({ kind: "country", value: "IND" }));
    fireEvent.change(input, { target: { value: "macro outlook for semiconductors" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit research search" }));
    expect(submit).toHaveBeenCalledWith("macro outlook for semiconductors");
  });
});
