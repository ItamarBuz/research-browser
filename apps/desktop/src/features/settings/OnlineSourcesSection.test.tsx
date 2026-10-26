import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EngineProvider } from "../../shared/api/EngineContext";
import { fakeEngine } from "../../test/fakeEngine";
import { OnlineSourcesSection } from "./OnlineSourcesSection";

function renderSection(engine = fakeEngine()) {
  render(
    <EngineProvider api={engine.api}>
      <OnlineSourcesSection />
    </EngineProvider>,
  );
  return engine;
}

const saveButtons = () => screen.getAllByRole("button", { name: "Save" });

describe("OnlineSourcesSection", () => {
  it("toggles a source", async () => {
    const engine = renderSection();
    const arxiv = await screen.findByRole("checkbox", { name: /arXiv/ });
    expect(arxiv).toBeChecked();

    fireEvent.click(arxiv);

    await waitFor(() => {
      expect(arxiv).not.toBeChecked();
    });
    expect(engine.api.updateOnlineSettings).toHaveBeenCalledWith({ sources: { arxiv: false } });
  });

  it("turning online search off disables the source list", async () => {
    renderSection();
    fireEvent.click(
      await screen.findByRole("checkbox", { name: "Search online academic sources" }),
    );
    await waitFor(() => {
      expect(screen.getByRole("group", { name: "Sources" })).toBeDisabled();
    });
  });

  it("saves an API key without ever showing it again", async () => {
    const engine = renderSection();
    const input = await screen.findByLabelText("OpenAlex API key");

    fireEvent.change(input, { target: { value: "  my-key  " } });
    fireEvent.click(saveButtons()[1] as HTMLElement);

    await screen.findByRole("button", { name: "Remove" });
    expect(engine.api.updateOnlineSettings).toHaveBeenCalledWith({ openalex_api_key: "my-key" });
    expect(input).toHaveValue("");
    expect(input).toHaveAttribute("placeholder", "Saved");
  });

  it("saves and clears the contact email", async () => {
    const engine = renderSection();
    const input = await screen.findByLabelText("Contact email (optional)");

    fireEvent.change(input, { target: { value: "me@example.org" } });
    fireEvent.click(saveButtons()[0] as HTMLElement);
    await waitFor(() => {
      expect(engine.api.updateOnlineSettings).toHaveBeenCalledWith({
        contact_email: "me@example.org",
      });
    });

    fireEvent.change(input, { target: { value: "" } });
    fireEvent.click(saveButtons()[0] as HTMLElement);
    await waitFor(() => {
      expect(engine.api.updateOnlineSettings).toHaveBeenCalledWith({ clear_contact_email: true });
    });
  });
});
