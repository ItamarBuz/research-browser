import { useCallback, useEffect } from "react";

import { useEngine } from "../../shared/api/EngineContext";
import type { LibraryState } from "../../shared/api/engine";
import { useAsyncResource, type AsyncResource } from "../../shared/hooks/useAsyncResource";

export const LIBRARY_POLL_MS = 1000;

const IN_PROGRESS = new Set(["queued", "parsing", "indexing"]);

export function isProcessing(state: LibraryState | undefined): boolean {
  if (!state) return false;
  return state.index.busy || state.documents.some((d) => IN_PROGRESS.has(d.status));
}

/** Library contents, polled while documents are being imported or indexed. */
export function useLibrary(pollMs: number = LIBRARY_POLL_MS): AsyncResource<LibraryState> {
  const api = useEngine();
  const load = useCallback(() => api.getLibrary(), [api]);
  const resource = useAsyncResource(load);
  const { reload } = resource;
  const processing = isProcessing(resource.data);

  useEffect(() => {
    if (!processing) return;
    const timer = setInterval(() => void reload(), pollMs);
    return () => {
      clearInterval(timer);
    };
  }, [processing, reload, pollMs]);

  return resource;
}
