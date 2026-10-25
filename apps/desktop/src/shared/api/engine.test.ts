import { describe, expect, it, vi } from "vitest";

import { EngineClient, EngineRequestError, waitForEngine, type HealthResponse } from "./engine";

const connection = { baseUrl: "http://127.0.0.1:9999", token: "tok" };
const health: HealthResponse = { status: "ok", version: "0.1.0", api_version: 1 };
const noSleep = () => Promise.resolve();

function jsonResponse(body: unknown, status = 200, contentType = "application/json"): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": contentType } });
}

describe("EngineClient", () => {
  it("sends the bearer token and parses health", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(health));
    const client = new EngineClient(connection, fetchImpl);

    await expect(client.getHealth()).resolves.toEqual(health);
    expect(fetchImpl).toHaveBeenCalledWith("http://127.0.0.1:9999/health", {
      headers: { Authorization: "Bearer tok" },
    });
  });

  it("turns problem+json responses into EngineRequestError", async () => {
    const problem = { type: "x", title: "Model not ready", status: 503, detail: "downloading" };
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockResolvedValue(jsonResponse(problem, 503, "application/problem+json"));

    const error = await new EngineClient(connection, fetchImpl)
      .getHealth()
      .catch((e: unknown) => e);

    expect(error).toBeInstanceOf(EngineRequestError);
    expect(error).toMatchObject({ status: 503, title: "Model not ready", detail: "downloading" });
  });

  it("reports network failures as status 0", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(new EngineClient(connection, fetchImpl).getHealth()).rejects.toMatchObject({
      status: 0,
      title: "Engine unreachable",
    });
  });
});

describe("waitForEngine", () => {
  it("retries until the engine comes up", async () => {
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError("refused"))
      .mockRejectedValueOnce(new TypeError("refused"))
      .mockResolvedValue(jsonResponse(health));

    const result = await waitForEngine(new EngineClient(connection, fetchImpl), {
      attempts: 5,
      delayMs: 1,
      sleep: noSleep,
    });

    expect(result).toEqual(health);
    expect(fetchImpl).toHaveBeenCalledTimes(3);
  });

  it("does not retry auth failures", async () => {
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockResolvedValue(jsonResponse({ detail: "Missing or invalid engine token" }, 401));

    await expect(
      waitForEngine(new EngineClient(connection, fetchImpl), {
        attempts: 5,
        delayMs: 1,
        sleep: noSleep,
      }),
    ).rejects.toMatchObject({ status: 401 });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("gives up after the configured attempts", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockRejectedValue(new TypeError("refused"));

    await expect(
      waitForEngine(new EngineClient(connection, fetchImpl), {
        attempts: 3,
        delayMs: 1,
        sleep: noSleep,
      }),
    ).rejects.toBeInstanceOf(EngineRequestError);
    expect(fetchImpl).toHaveBeenCalledTimes(3);
  });
});
