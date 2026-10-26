import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EngineProvider } from "../../shared/api/EngineContext";
import { fakeEngine, libraryDocument, onlineHit } from "../../test/fakeEngine";
import { SearchPage } from "./SearchPage";

vi.mock("../../shared/openExternal", () => ({ openExternal: vi.fn(() => Promise.resolve()) }));

function renderSearch(engine = fakeEngine(), onNavigate = vi.fn()) {
  engine.library.seed(libraryDocument("d1", "Sleep and Memory in the library"));
  render(
    <EngineProvider api={engine.api}>
      <SearchPage onNavigate={onNavigate} />
    </EngineProvider>,
  );
  return { engine, onNavigate };
}

async function search(engine: ReturnType<typeof fakeEngine>, text: string) {
  await screen.findByRole("searchbox");
  // Online search depends on the settings, so wait until they have loaded.
  await waitFor(() => {
    expect(engine.api.getOnlineSettings).toHaveBeenCalled();
  });
  await new Promise((resolve) => setTimeout(resolve, 0));
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
}

describe("online results", () => {
  it("shows library and online results side by side", async () => {
    const { engine } = renderSearch();
    await search(engine, "sleep");

    expect(await screen.findByRole("region", { name: "In your library" })).toBeInTheDocument();
    const online = await screen.findByRole("region", { name: "Found online" });
    expect(within(online).getByText("Sleep and memory online")).toBeInTheDocument();
    expect(within(online).getAllByText("12 citations")).toHaveLength(2);
    expect(within(online).getByText("OpenAlex: 2")).toBeInTheDocument();
    expect(within(online).getByText("Semantic Scholar: unavailable")).toHaveAttribute(
      "title",
      "semantic_scholar: rate limited",
    );
    expect(engine.api.discover).toHaveBeenCalledWith({
      query: "sleep",
      language: "cross",
      limit: 20,
    });
  });

  it("adds an open-access paper to the library with its catalog metadata", async () => {
    const { engine } = renderSearch();
    await search(engine, "sleep");

    const card = (await screen.findByText("Sleep and memory online")).closest("li") as HTMLElement;
    fireEvent.click(within(card).getByRole("button", { name: "Add to library" }));

    expect(await within(card).findByText("In your library")).toBeInTheDocument();
    expect(engine.api.importDocumentFromUrl).toHaveBeenCalledWith("https://example.org/paper.pdf", {
      title: "Sleep and memory online",
      authors: ["Ruth Cohen"],
      year: 2022,
      doi: "10.1/23",
      from_catalog: true,
    });
  });

  it("explains when there is no free PDF, and when a link is not a PDF", async () => {
    const engine = fakeEngine();
    engine.online.setResponse({
      results: [
        onlineHit("Paywalled study", { pdf_url: null }),
        onlineHit("Landing page", { pdf_url: "https://example.org/landing" }),
      ],
    });
    renderSearch(engine);
    await search(engine, "sleep");

    const paywalled = (await screen.findByText("Paywalled study")).closest("li") as HTMLElement;
    expect(within(paywalled).getByText("No free PDF found")).toBeInTheDocument();

    const landing = screen.getByText("Landing page").closest("li") as HTMLElement;
    fireEvent.click(within(landing).getByRole("button", { name: "Add to library" }));
    expect(await within(landing).findByRole("alert")).toHaveTextContent("web page, not a PDF");
  });

  it("shows the translated query and suggests the translation models when missing", async () => {
    const engine = fakeEngine();
    engine.online.setResponse({
      query_language: "he",
      queries: { en: "sleep deprivation memory", he: "חוסר שינה" },
      translation_missing: true,
    });
    const { onNavigate } = renderSearch(engine);
    await search(engine, "חוסר שינה");

    expect(await screen.findByText("«sleep deprivation memory»")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open settings" }));
    expect(onNavigate).toHaveBeenCalledWith("settings");
  });

  it("does not search online when it is turned off", async () => {
    const engine = fakeEngine();
    engine.online.setEnabled(false);
    renderSearch(engine);
    await search(engine, "sleep");

    await screen.findByRole("region", { name: "In your library" });
    expect(engine.api.discover).not.toHaveBeenCalled();
    expect(screen.queryByRole("region", { name: "Found online" })).toBeNull();
  });
});
