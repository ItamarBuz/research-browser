import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EngineProvider } from "../../shared/api/EngineContext";
import { isolate } from "../../shared/format";
import i18n from "../../shared/i18n";
import { fakeEngine, systemInfo } from "../../test/fakeEngine";
import { SettingsPage } from "./SettingsPage";

function renderSettings(engine = fakeEngine()) {
  render(
    <EngineProvider api={engine.api}>
      <SettingsPage pollMs={10} />
    </EngineProvider>,
  );
  return engine;
}

const tierSection = () => screen.getByRole("region", { name: "Performance tier" });
const modelsSection = () => screen.getByRole("region", { name: "AI models" });

describe("SettingsPage", () => {
  it("shows the detected hardware", async () => {
    renderSettings();
    const hardware = await screen.findByRole("region", { name: "Your computer" });

    expect(hardware).toHaveTextContent("Windows (AMD64)");
    expect(hardware).toHaveTextContent("6 cores · 12 threads");
    expect(hardware).toHaveTextContent(`${isolate("15.7 GB")} total`);
    expect(hardware).toHaveTextContent(`NVIDIA GeForce RTX 3060 · ${isolate("12 GB")} · CUDA`);
  });

  it("explains the detected tier", async () => {
    renderSettings();
    await screen.findByRole("region", { name: "Performance tier" });

    expect(tierSection()).toHaveTextContent("Standard");
    expect(tierSection()).toHaveTextContent(`${isolate("15.7 GB")} of system memory`);
    expect(screen.getByRole("radio", { name: /Automatic/ })).toBeChecked();
  });

  it("applies a manual tier and refreshes recommendations", async () => {
    const engine = renderSettings();
    await screen.findByRole("region", { name: "AI models" });
    expect(within(modelsSection()).getByText("Qwen3 8B")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: "Pro" }));

    await waitFor(() => {
      expect(screen.getByRole("radio", { name: "Pro" })).toBeChecked();
    });
    expect(engine.api.setTierOverride).toHaveBeenCalledWith("pro");
    expect(tierSection()).toHaveTextContent("You chose this tier manually");
    await waitFor(() => {
      expect(modelsSection()).toHaveTextContent("recommended for the Pro tier");
    });
  });

  it("returns to automatic detection", async () => {
    const engine = fakeEngine(systemInfo({ effective: "lite", override_source: "user" }));
    renderSettings(engine);
    await screen.findByRole("region", { name: "Performance tier" });
    expect(screen.getByRole("radio", { name: "Lite" })).toBeChecked();

    fireEvent.click(screen.getByRole("radio", { name: /Automatic/ }));

    await waitFor(() => {
      expect(engine.api.setTierOverride).toHaveBeenCalledWith(null);
    });
  });

  it("locks the tier when set by the environment", async () => {
    renderSettings(fakeEngine(systemInfo({ effective: "lite", override_source: "env" })));
    await screen.findByRole("region", { name: "Performance tier" });

    expect(screen.getByRole("group", { name: "Choose a tier" })).toBeDisabled();
    expect(tierSection()).toHaveTextContent("RB_TIER");
  });

  it("downloads all recommended models with live progress", async () => {
    const engine = renderSettings();
    const button = await screen.findByRole("button", { name: /Download all recommended/ });

    fireEvent.click(button);

    await waitFor(() => {
      expect(within(modelsSection()).getAllByText("Ready")).toHaveLength(2);
    });
    expect(engine.api.startModelDownload.mock.calls.map(([id]) => id)).toEqual([
      "embed-e5-base",
      "llm-qwen3-8b",
    ]);
    expect(screen.queryByRole("button", { name: /Download all recommended/ })).toBeNull();
  });

  it("offers optional models separately", async () => {
    renderSettings();
    const summary = await screen.findByText("2 optional models");
    const details = summary.closest("details");
    expect(details).toHaveTextContent("DictaLM 2.0");
    expect(details).toHaveTextContent("Qwen3 14B"); // the Pro-tier model is optional on Standard
  });

  it("shows download failures with a retry", async () => {
    const engine = fakeEngine();
    engine.failDownload("llm-qwen3-8b", "Not enough disk space");
    renderSettings(engine);

    const row = (await screen.findByText("Qwen3 8B")).closest("tr");
    expect(row).toHaveTextContent("Not enough disk space");

    fireEvent.click(within(row as HTMLElement).getByRole("button", { name: "Retry" }));
    await waitFor(() => {
      expect(engine.api.startModelDownload).toHaveBeenCalledWith("llm-qwen3-8b");
    });
  });

  it("renders in Hebrew", async () => {
    await act(async () => {
      await i18n.changeLanguage("he");
    });
    renderSettings();

    expect(await screen.findByRole("region", { name: "רמת ביצועים" })).toHaveTextContent("רגילה");
    expect(screen.getByRole("region", { name: "המחשב שלך" })).toBeInTheDocument();
  });
});
