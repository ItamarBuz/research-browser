import { invoke, isTauri } from "@tauri-apps/api/core";

import type { components } from "./schema";

export type HealthResponse = components["schemas"]["HealthResponse"];

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

  private async request<T>(path: string): Promise<T> {
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.connection.baseUrl}${path}`, {
        headers: { Authorization: `Bearer ${this.connection.token}` },
      });
    } catch (cause) {
      throw new EngineRequestError(0, "Engine unreachable", String(cause));
    }
    if (!response.ok) {
      throw await toRequestError(response);
    }
    return (await response.json()) as T;
  }
}

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
