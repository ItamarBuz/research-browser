import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { App } from "./App";
import type { ConnectFn } from "./features/health/useEngineHealth";
import { fakeEngine, HEALTH } from "./test/fakeEngine";

const healthy: ConnectFn = () => Promise.resolve({ api: fakeEngine().api, health: HEALTH });

describe("App", () => {
  it("shows the engine as ready once health succeeds", async () => {
    render(<App connect={healthy} />);
    expect(await screen.findByText("Engine ready")).toBeInTheDocument();
    expect(screen.getByText("v0.1.0").tagName).toBe("BDI");
  });

  it("shows the failure and retries on request", async () => {
    const connect = vi
      .fn<ConnectFn>()
      .mockRejectedValueOnce(new Error("refused"))
      .mockImplementation(healthy);

    render(<App connect={connect} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("refused");

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Engine ready")).toBeInTheDocument();
    expect(connect).toHaveBeenCalledTimes(2);
  });

  it("opens on search and navigates between views", async () => {
    render(<App connect={healthy} />);
    await screen.findByText("Engine ready");
    expect(screen.getByRole("heading", { level: 1, name: "Search your library" })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Library" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Library" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Settings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Settings" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("switches to Hebrew and flips the document to RTL", async () => {
    render(<App connect={healthy} />);
    await screen.findByText("Engine ready");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "עברית" }));
      await Promise.resolve();
    });

    expect(screen.getByText("דפדפן מחקר")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("חיפוש בספרייה שלך");
    expect(document.documentElement).toHaveAttribute("dir", "rtl");
    expect(document.documentElement).toHaveAttribute("lang", "he");
  });
});
