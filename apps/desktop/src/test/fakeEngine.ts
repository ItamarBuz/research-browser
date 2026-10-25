import { vi } from "vitest";

import type {
  EngineApi,
  HealthResponse,
  ModelInfo,
  ModelList,
  SystemInfo,
  Tier,
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
  } satisfies EngineApi;

  return {
    api,
    failDownload(id: string, error: string): void {
      const target = models.find((m) => m.id === id);
      if (target) target.state = { ...target.state, status: "failed", error };
    },
  };
}
