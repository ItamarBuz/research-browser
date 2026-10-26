import { vi } from "vitest";

import {
  EngineRequestError,
  type DocumentHit,
  type EngineApi,
  type HealthResponse,
  type ImportResult,
  type LibraryDocument,
  type LibraryState,
  type ModelInfo,
  type ModelList,
  type SearchRequest,
  type SearchResponse,
  type SystemInfo,
  type Tier,
} from "../shared/api/engine";

export const HEALTH: HealthResponse = { status: "ok", version: "0.1.0", api_version: 1 };

const GB = 1024 ** 3;
const LIMITS: Record<Tier, number> = { lite: 1, standard: 2, pro: 4 };

export function systemInfo(overrides: Partial<SystemInfo["tier"]> = {}): SystemInfo {
  return {
    hardware: {
      os: "Windows",
      arch: "AMD64",
      cpu_physical_cores: 6,
      cpu_logical_cores: 12,
      total_ram_mb: 16076,
      available_ram_mb: 8192,
      gpus: [
        {
          name: "NVIDIA GeForce RTX 3060",
          backend: "cuda",
          memory_mb: 12288,
          unified_memory: false,
        },
      ],
    },
    tier: {
      detected: "standard",
      effective: "standard",
      override_source: null,
      reasons: [{ code: "system_ram", value_gb: 15.7 }],
      ...overrides,
    },
    resident_model_limit: 2,
  };
}

function model(
  id: string,
  name: string,
  role: ModelInfo["role"],
  tiers: Tier[],
  gb: number,
): ModelInfo {
  const size = Math.round(gb * GB);
  return {
    id,
    name,
    role,
    license: "mit",
    size_bytes: size,
    tiers,
    recommended: false,
    state: { status: "not_downloaded", downloaded_bytes: 0, total_bytes: size },
  };
}

/**
 * An in-memory engine: tier overrides change recommendations, and a started download
 * reports half progress on the next poll and completes on the one after.
 */
export function fakeEngine(initial: SystemInfo = systemInfo()) {
  let system = initial;
  const library = fakeLibrary();
  const models: ModelInfo[] = [
    model("embed-e5-base", "Multilingual E5 Base", "embedder", ["standard"], 0.3),
    model("llm-qwen3-8b", "Qwen3 8B", "llm", ["standard"], 4.7),
    model("llm-qwen3-14b", "Qwen3 14B", "llm", ["pro"], 8.4),
    model("llm-dictalm2-7b", "DictaLM 2.0", "llm", [], 4.1),
  ];

  function advanceDownloads(): void {
    for (const m of models) {
      const { state } = m;
      if (state.status !== "downloading") continue;
      state.downloaded_bytes = Math.min(
        state.total_bytes,
        state.downloaded_bytes + state.total_bytes / 2,
      );
      if (state.downloaded_bytes >= state.total_bytes) state.status = "ready";
    }
  }

  function list(): ModelList {
    const tier = system.tier.effective;
    const infos = models.map((m) => ({
      ...m,
      state: { ...m.state },
      recommended: m.tiers.includes(tier),
    }));
    infos.sort((a, b) => Number(b.recommended) - Number(a.recommended));
    return { tier, models: infos };
  }

  const api = {
    getHealth: vi.fn(() => Promise.resolve(HEALTH)),
    getSystem: vi.fn(() => Promise.resolve(system)),
    setTierOverride: vi.fn((tier: Tier | null) => {
      const effective = tier ?? system.tier.detected;
      system = {
        ...system,
        tier: {
          ...system.tier,
          effective,
          override_source: tier ? "user" : null,
          reasons: tier
            ? [{ code: "override_user", value_gb: null }, ...initial.tier.reasons]
            : initial.tier.reasons,
        },
        resident_model_limit: LIMITS[effective],
      };
      return Promise.resolve(system);
    }),
    listModels: vi.fn(() => {
      const result = list();
      advanceDownloads();
      return Promise.resolve(result);
    }),
    startModelDownload: vi.fn((id: string) => {
      const target = models.find((m) => m.id === id);
      if (!target) return Promise.reject(new Error(`unknown ${id}`));
      target.state = { status: "downloading", downloaded_bytes: 0, total_bytes: target.size_bytes };
      return Promise.resolve({ ...target });
    }),
    ...library.api,
  } satisfies EngineApi;

  return {
    api,
    library,
    failDownload(id: string, error: string): void {
      const target = models.find((m) => m.id === id);
      if (target) target.state = { ...target.state, status: "failed", error };
    },
  };
}

export function libraryDocument(
  id: string,
  title: string,
  overrides: Partial<LibraryDocument> = {},
): LibraryDocument {
  return {
    id,
    file_name: `${id}.pdf`,
    size_bytes: 1000,
    added_at: "2026-10-25T10:00:00Z",
    status: "ready",
    error: null,
    metadata: { title, authors: ["Ada Lovelace"], year: 2021, doi: null },
    language: "en",
    page_count: 3,
    passage_count: 3,
    searchable: true,
    ...overrides,
  };
}

/**
 * In-memory library: an import is "queued" on the first poll and ready + searchable on the
 * next; search matches documents whose title shares a word with the query.
 */
function fakeLibrary() {
  let documents: LibraryDocument[] = [];
  let modelReady = true;

  function advance(): void {
    documents = documents.map((d) =>
      d.status === "queued"
        ? { ...d, status: "ready", searchable: modelReady, page_count: 2, language: "en" }
        : d,
    );
  }

  function state(): LibraryState {
    const ready = documents.filter((d) => d.status === "ready");
    const indexed = ready.filter((d) => d.searchable).length;
    return {
      documents: documents.map((d) => ({ ...d })),
      index: {
        embedding_model: "embed-e5-small",
        model_ready: modelReady,
        ready_documents: ready.length,
        indexed_documents: indexed,
        pending_documents: ready.length - indexed,
        busy: false,
      },
    };
  }

  const api = {
    getLibrary: vi.fn(() => {
      const result = state();
      advance();
      return Promise.resolve(result);
    }),
    importDocuments: vi.fn((files: readonly File[]) =>
      Promise.resolve(
        files.map((file): ImportResult => {
          if (!file.name.endsWith(".pdf")) return { file_name: file.name, error: "Not a PDF file" };
          const doc = libraryDocument(file.name.replace(/\W/g, ""), file.name, {
            status: "queued",
            searchable: false,
            page_count: 0,
            language: null,
          });
          documents = [doc, ...documents];
          return { file_name: file.name, document: doc };
        }),
      ),
    ),
    deleteDocument: vi.fn((id: string) => {
      documents = documents.filter((d) => d.id !== id);
      return Promise.resolve();
    }),
    reindexLibrary: vi.fn(() => {
      documents = documents.map((d) => (d.status === "ready" ? { ...d, searchable: true } : d));
      return Promise.resolve(state().index);
    }),
    searchLibrary: vi.fn((request: SearchRequest): Promise<SearchResponse> => {
      if (!modelReady) {
        return Promise.reject(new EngineRequestError(503, "Model not ready", "download it"));
      }
      const words = request.query.toLowerCase().split(/\s+/);
      const results: DocumentHit[] = documents
        .filter((d) => d.searchable)
        .filter((d) => request.language === "cross" || d.language === request.language)
        .filter((d) => words.some((w) => d.metadata.title.toLowerCase().includes(w)))
        .map((d) => ({
          document: d,
          score: 0.03,
          passages: [
            {
              passage_id: `${d.id}:0`,
              page: 1,
              text: `A passage about ${d.metadata.title}.`,
              score: 0.03,
              similarity: 0.8,
            },
          ],
        }));
      return Promise.resolve({
        query_language: "en",
        embedding_model: "embed-e5-small",
        results,
        took_ms: 12,
      });
    }),
  } satisfies Partial<EngineApi>;

  return {
    api,
    seed(...docs: LibraryDocument[]): void {
      documents = docs;
    },
    setModelReady(ready: boolean): void {
      modelReady = ready;
    },
  };
}
