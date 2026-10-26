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
export type LibraryState = Schemas["LibraryState"];
export type LibraryDocument = Schemas["LibraryDocument"];
export type IndexStatus = Schemas["IndexStatus"];
export type ImportResult = Schemas["ImportResult"];
export type SearchRequest = Schemas["SearchRequest"];
export type SearchResponse = Schemas["SearchResponse"];
export type DocumentHit = Schemas["DocumentHit"];
export type LanguageFilter = NonNullable<SearchRequest["language"]>;
export type DiscoveryRequest = Schemas["DiscoveryRequest"];
export type DiscoveryResponse = Schemas["DiscoveryResponse"];
export type WorkHit = Schemas["WorkHit"];
export type Work = Schemas["Work"];
export type SourceName = Schemas["SourceName"];
export type SourceStatus = Schemas["SourceStatus"];
export type OnlineSettingsView = Schemas["OnlineSettingsView"];
export type OnlineSettingsUpdate = Schemas["OnlineSettingsUpdate"];
export type DocumentMetadata = Schemas["DocumentMetadata"];

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

  getLibrary(): Promise<LibraryState> {
    return this.request<LibraryState>("/library");
  }

  importDocuments(files: readonly File[]): Promise<ImportResult[]> {
    const form = new FormData();
    for (const file of files) form.append("files", file, file.name);
    return this.request<ImportResult[]>("/library/documents", { method: "POST", body: form });
  }

  async deleteDocument(documentId: string): Promise<void> {
    await this.request<null>(`/library/documents/${encodeURIComponent(documentId)}`, {
      method: "DELETE",
    });
  }

  reindexLibrary(): Promise<IndexStatus> {
    return this.request<IndexStatus>("/library/reindex", { method: "POST" });
  }

  searchLibrary(request: SearchRequest): Promise<SearchResponse> {
    return this.request<SearchResponse>("/library/search", { method: "POST", body: request });
  }

  discover(request: DiscoveryRequest): Promise<DiscoveryResponse> {
    return this.request<DiscoveryResponse>("/discover", { method: "POST", body: request });
  }

  getOnlineSettings(): Promise<OnlineSettingsView> {
    return this.request<OnlineSettingsView>("/settings/online");
  }

  updateOnlineSettings(update: Partial<OnlineSettingsUpdate>): Promise<OnlineSettingsView> {
    return this.request<OnlineSettingsView>("/settings/online", { method: "PUT", body: update });
  }

  importDocumentFromUrl(url: string, metadata: DocumentMetadata | null): Promise<ImportResult> {
    return this.request<ImportResult>("/library/documents/from-url", {
      method: "POST",
      body: { url, metadata },
    });
  }

  private async request<T>(
    path: string,
    options: { method?: "PUT" | "POST" | "DELETE"; body?: unknown } = {},
  ): Promise<T> {
    const { body } = options;
    const isForm = body instanceof FormData;
    const init: RequestInit = {
      headers: {
        Authorization: `Bearer ${this.connection.token}`,
        // FormData sets its own multipart boundary header.
        ...(body === undefined || isForm ? {} : { "Content-Type": "application/json" }),
      },
    };
    if (options.method) init.method = options.method;
    if (body !== undefined) init.body = isForm ? body : JSON.stringify(body);

    let response: Response;
    try {
      response = await this.fetchImpl(`${this.connection.baseUrl}${path}`, init);
    } catch (cause) {
      throw new EngineRequestError(0, "Engine unreachable", String(cause));
    }
    if (!response.ok) {
      throw await toRequestError(response);
    }
    if (response.status === HTTP_NO_CONTENT) return null as T;
    return (await response.json()) as T;
  }
}

const HTTP_NO_CONTENT = 204;

/** The engine operations the UI uses; tests substitute a fake implementation. */
export type EngineApi = Pick<
  EngineClient,
  | "getHealth"
  | "getSystem"
  | "setTierOverride"
  | "listModels"
  | "startModelDownload"
  | "getLibrary"
  | "importDocuments"
  | "deleteDocument"
  | "reindexLibrary"
  | "searchLibrary"
  | "discover"
  | "getOnlineSettings"
  | "updateOnlineSettings"
  | "importDocumentFromUrl"
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
