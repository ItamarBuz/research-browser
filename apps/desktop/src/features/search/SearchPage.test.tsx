import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EngineProvider } from "../../shared/api/EngineContext";
import i18n from "../../shared/i18n";
import { fakeEngine, libraryDocument } from "../../test/fakeEngine";
import { SearchPage } from "./SearchPage";

function renderSearch(engine = fakeEngine(), onNavigate = vi.fn()) {
  render(
    <EngineProvider api={engine.api}>
      <SearchPage onNavigate={onNavigate} />
    </EngineProvider>,
  );
  return { engine, onNavigate };
}

function search(text: string) {
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
}

function seeded() {
  const engine = fakeEngine();
  engine.library.seed(
    libraryDocument("d1", "Sleep and Memory Consolidation", {
      metadata: {
        title: "Sleep and Memory Consolidation",
        authors: ["A", "B", "C", "D"],
        year: 2021,
        doi: null,
      },
    }),
    libraryDocument("d2", "שינה וזיכרון", { language: "he" }),
  );
  return engine;
}

describe("SearchPage", () => {
  it("shows results with passages and page numbers", async () => {
    const { engine } = renderSearch(seeded());
    await screen.findByRole("searchbox");

    search("sleep");

    const results = await screen.findAllByRole("listitem");
    expect(results).toHaveLength(1);
    expect(results[0]).toHaveTextContent("Sleep and Memory Consolidation");
    expect(results[0]).toHaveTextContent("A, B, C et al.");
    expect(results[0]).toHaveTextContent("Page 1");
    expect(engine.api.searchLibrary).toHaveBeenCalledWith({
      query: "sleep",
      language: "cross",
      limit: 20,
    });
  });

  it("applies the source language filter", async () => {
    const { engine } = renderSearch(seeded());
    await screen.findByRole("searchbox");

    fireEvent.click(screen.getByRole("radio", { name: "Hebrew only" }));
    search("sleep");

    expect(await screen.findByText(/No matching passages/)).toBeInTheDocument();
    expect(engine.api.searchLibrary).toHaveBeenCalledWith({
      query: "sleep",
      language: "he",
      limit: 20,
    });
  });

  it("explains cross-lingual search", async () => {
    renderSearch();
    expect(await screen.findByText(/finds English papers for a Hebrew question/)).toBeVisible();
    fireEvent.click(screen.getByRole("radio", { name: "English only" }));
    expect(screen.queryByText(/finds English papers for a Hebrew question/)).toBeNull();
  });

  it("points an empty library to the import page", async () => {
    const { onNavigate } = renderSearch();
    fireEvent.click(await screen.findByRole("button", { name: "Import PDFs" }));
    expect(onNavigate).toHaveBeenCalledWith("library");
  });

  it("sends the user to settings when the model is missing", async () => {
    const engine = seeded();
    engine.library.setModelReady(false);
    const { onNavigate } = renderSearch(engine);
    await screen.findByRole("searchbox");

    search("sleep");

    fireEvent.click(await screen.findByRole("button", { name: "Open settings" }));
    expect(onNavigate).toHaveBeenCalledWith("settings");
  });

  it("lets the query be typed right-to-left in Hebrew", async () => {
    await act(async () => {
      await i18n.changeLanguage("he");
    });
    renderSearch(seeded());
    const box = await screen.findByRole("searchbox");
    expect(box).toHaveAttribute("dir", "auto");
    expect(screen.getByRole("radio", { name: "עברית בלבד" })).toBeInTheDocument();
  });
});
