import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EngineProvider } from "../../shared/api/EngineContext";
import { fakeEngine, libraryDocument } from "../../test/fakeEngine";
import { LibraryPage } from "./LibraryPage";

function renderLibrary(engine = fakeEngine(), onNavigate = vi.fn()) {
  render(
    <EngineProvider api={engine.api}>
      <LibraryPage onNavigate={onNavigate} pollMs={10} />
    </EngineProvider>,
  );
  return { engine, onNavigate };
}

const pdf = (name: string) => new File(["%PDF-1.4"], name, { type: "application/pdf" });

function chooseFiles(...files: File[]) {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error("file input missing");
  fireEvent.change(input, { target: { files } });
}

describe("LibraryPage", () => {
  it("shows an empty library", async () => {
    renderLibrary();
    expect(await screen.findByText("No documents yet.")).toBeInTheDocument();
  });

  it("imports PDFs and follows them until searchable", async () => {
    const { engine } = renderLibrary();
    await screen.findByText("No documents yet.");

    chooseFiles(pdf("sleep study.pdf"), new File(["x"], "notes.txt"));

    await waitFor(() => {
      expect(screen.getByText("Searchable")).toBeInTheDocument();
    });
    // Non-PDF files are filtered out before upload.
    expect(engine.api.importDocuments).toHaveBeenCalledWith([expect.any(File)]);
    const row = screen.getByText("sleep study.pdf", { selector: ".doc-title" }).closest("tr");
    expect(row).toHaveTextContent("English");
  });

  it("deletes after confirmation", async () => {
    const engine = fakeEngine();
    engine.library.seed(libraryDocument("d1", "Sleep and Memory"));
    renderLibrary(engine);

    const row = (await screen.findByText("Sleep and Memory")).closest("tr") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: /Delete/ }));
    expect(engine.api.deleteDocument).not.toHaveBeenCalled();
    fireEvent.click(within(row).getByRole("button", { name: "Confirm delete" }));

    await screen.findByText("No documents yet.");
    expect(engine.api.deleteDocument).toHaveBeenCalledWith("d1");
  });

  it("offers indexing when documents are missing from the index", async () => {
    const engine = fakeEngine();
    engine.library.seed(libraryDocument("d1", "Sleep and Memory", { searchable: false }));
    renderLibrary(engine);

    fireEvent.click(await screen.findByRole("button", { name: "Index now" }));

    await screen.findByText("Searchable");
    expect(engine.api.reindexLibrary).toHaveBeenCalled();
  });

  it("sends the user to settings when the model is missing", async () => {
    const engine = fakeEngine();
    engine.library.setModelReady(false);
    engine.library.seed(libraryDocument("d1", "Sleep and Memory", { searchable: false }));
    const { onNavigate } = renderLibrary(engine);

    fireEvent.click(await screen.findByRole("button", { name: "Download it in settings" }));
    expect(onNavigate).toHaveBeenCalledWith("settings");
  });

  it("shows why a document failed", async () => {
    const engine = fakeEngine();
    engine.library.seed(
      libraryDocument("d1", "scan.pdf", { status: "failed", error: "No extractable text" }),
    );
    renderLibrary(engine);
    expect(await screen.findByText(/No extractable text/)).toBeInTheDocument();
  });
});
