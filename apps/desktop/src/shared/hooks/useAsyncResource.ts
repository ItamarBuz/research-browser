import { useCallback, useEffect, useRef, useState } from "react";

export interface AsyncResource<T> {
  data: T | undefined;
  error: string | undefined;
  /** Re-runs the loader; resolves once state is updated. */
  reload: () => Promise<void>;
  /** Replaces the data directly, e.g. with the response of a mutation. */
  setData: (data: T) => void;
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * Loads data on mount and on demand, ignoring results that arrive after unmount.
 * `load` must be stable (wrap it in useCallback), or it reloads on every render.
 */
export function useAsyncResource<T>(load: () => Promise<T>): AsyncResource<T> {
  const [data, setDataState] = useState<T>();
  const [error, setError] = useState<string>();
  const mounted = useRef(true);

  const reload = useCallback(async () => {
    try {
      const value = await load();
      if (mounted.current) {
        setDataState(value);
        setError(undefined);
      }
    } catch (err) {
      if (mounted.current) setError(messageOf(err));
    }
  }, [load]);

  useEffect(() => {
    mounted.current = true;
    let current = true; // ignore a stale response if `load` changes mid-flight
    load().then(
      (value) => {
        if (current) {
          setDataState(value);
          setError(undefined);
        }
      },
      (err: unknown) => {
        if (current) setError(messageOf(err));
      },
    );
    return () => {
      current = false;
      mounted.current = false;
    };
  }, [load]);

  const setData = useCallback((value: T) => {
    setDataState(value);
    setError(undefined);
  }, []);

  return { data, error, reload, setData };
}
