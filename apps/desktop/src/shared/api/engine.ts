import { invoke, isTauri } from "@tauri-apps/api/core";

import type { components } from "./schema";

type Schemas = components["schemas"];
export type HealthResponse = Schemas["HealthResponse"];
export type SystemInfo = Schemas["SystemInfo"];
export type HardwareProfile = Schemas["HardwareProfile"];
export type GpuInfo = Schemas["GpuInfo"];
export type TierDecision = Schemas["TierDecision"];
export type Tier = Schemas["Tier"];
export type TierReason = Schemas["TierReason"];
export type ModelList = Schemas["ModelList"];
export type ModelInfo = Schemas["ModelInfo"];
export type ModelRole = Schemas["ModelRole"];

/** Where the engine sidecar listens and the per-launch token it expects. */
export interface EngineConnection {
  baseUrl: string;
  token: string;
}

/** An RFC 7807 problem returned by the engine, or a transport failure. */
export class EngineRequestError extends Error {
  constructor(
    readonly status: number,
    readonly title: string,
    readonly detail?: string,
  ) {
    super(detail ? `${title}: ${detail}` : title);
    this.name = "EngineRequestError";
  }
}

/**
 * Resolves the engine connection. Inside Tauri it comes from the Rust shell; in a plain
 * browser (`pnpm dev` without Tauri) it comes from VITE_ENGINE_URL / VITE_ENGINE_TOKEN so the
 * UI can be developed against a manually started engine.
 */
export async function getEngineConnection(): Promise<EngineConnection> {
  if (isTauri()) {
    return invoke<EngineConnection>("engine_connection");
  }
  const baseUrl = import.meta.env.VITE_ENGINE_URL as string | undefined;
  const token = import.meta.env.VITE_ENGINE_TOKEN as string | undefined;
  if (!baseUrl || !token) {
    throw new EngineRequestError(
      0,
      "Engine not configured",
      "Run inside Tauri, or set VITE_ENGINE_URL and VITE_ENGINE_TOKEN",
    );
  }
  return { baseUrl, token };
}

interface ProblemBody {
  title?: unknown;
  detail?: unknown;
}

export class EngineClient {
  constructor(
    private readonly connection: EngineConnection,
    private readonly fetchImpl: typeof fetch = fetch.bind(globalThis),
  ) {}

  getHealth(): Promise<HealthResponse> {
    return this.request<HealthResponse>("/health");
  }

  getSystem(): Promise<SystemInfo> {
    return this.request<SystemInfo>("/system");
  }

  /** `null` returns to automatic tier detection. */
  setTierOverride(tier: Tier | null): Promise<SystemInfo> {
    return this.request<SystemInfo>("/system/tier-override", { method: "PUT", body: { tier } });
  }

  listModels(): Promise<ModelList> {
    return this.request<ModelList>("/models");
  }

  startModelDownload(modelId: string): Promise<ModelInfo> {
    return this.request<ModelInfo>(`/models/${encodeURIComponent(modelId)}/download`, {
      method: "POST",
    });
  }

  private async request<T>(
    path: string,
    options: { method?: "PUT" | "POST"; body?: unknown } = {},
  ): Promise<T> {
    const init: RequestInit = {
      headers: {
        Authorization: `Bearer ${this.connection.token}`,
        ...(options.body === undefined ? {} : { "Content-Type": "application/json" }),
      },
    };
    if (options.method) init.method = options.method;
    if (options.body !== undefined) init.body = JSON.stringify(options.body);

    let response: Response;
    try {
      response = await this.fetchImpl(`${this.connection.baseUrl}${path}`, init);
    } catch (cause) {
      throw new EngineRequestError(0, "Engine unreachable", String(cause));
    }
    if (!response.ok) {
      throw await toRequestError(response);
    }
    return (await response.json()) as T;
  }
}

/** The engine operations the UI uses; tests substitute a fake implementation. */
export type EngineApi = Pick<
  EngineClient,
  "getHealth" | "getSystem" | "setTierOverride" | "listModels" | "startModelDownload"
>;

async function toRequestError(response: Response): Promise<EngineRequestError> {
  try {
    const body = (await response.json()) as ProblemBody;
    const title = typeof body.title === "string" ? body.title : response.statusText;
    const detail = typeof body.detail === "string" ? body.detail : undefined;
    return new EngineRequestError(response.status, title, detail);
  } catch {
    return new EngineRequestError(response.status, response.statusText || "Request failed");
  }
}

export interface RetryOptions {
  attempts: number;
  delayMs: number;
  sleep?: (ms: number) => Promise<void>;
}

const defaultSleep = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms));

/** Polls /health until the engine answers; it can take a few seconds to start. */
export async function waitForEngine(
  client: EngineClient,
  { attempts, delayMs, sleep = defaultSleep }: RetryOptions,
): Promise<HealthResponse> {
  let lastError: unknown;
  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      return await client.getHealth();
    } catch (error) {
      lastError = error;
      // A 4xx means the engine is up but rejected us; retrying will not help.
      if (error instanceof EngineRequestError && error.status >= 400 && error.status < 500) {
        throw error;
      }
      if (attempt < attempts) await sleep(delayMs);
    }
  }
  throw lastError;
}
