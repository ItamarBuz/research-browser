import { useCallback, useEffect } from "react";

import { useEngine } from "../../shared/api/EngineContext";
import type { ModelList } from "../../shared/api/engine";
import { useAsyncResource, type AsyncResource } from "../../shared/hooks/useAsyncResource";

export const DOWNLOAD_POLL_MS = 1000;

/** The model catalog with live download progress (polled while anything is downloading). */
export function useModels(pollMs: number = DOWNLOAD_POLL_MS): AsyncResource<ModelList> & {
  download: (modelIds: string[]) => Promise<void>;
} {
  const api = useEngine();
  const load = useCallback(() => api.listModels(), [api]);
  const resource = useAsyncResource(load);
  const { reload } = resource;

  const downloading = resource.data?.models.some((m) => m.state.status === "downloading") ?? false;
  useEffect(() => {
    if (!downloading) return;
    const timer = setInterval(() => void reload(), pollMs);
    return () => {
      clearInterval(timer);
    };
  }, [downloading, reload, pollMs]);

  const download = useCallback(
    async (modelIds: string[]) => {
      // Each call returns immediately; the engine downloads in the background.
      for (const id of modelIds) await api.startModelDownload(id);
      await reload();
    },
    [api, reload],
  );

  return { ...resource, download };
}
