import { useCallback, useEffect, useState } from "react";

import {
  EngineClient,
  getEngineConnection,
  waitForEngine,
  type EngineApi,
  type HealthResponse,
} from "../../shared/api/engine";

/** A connected engine: the API to call and what it reported at startup. */
export interface EngineSession {
  api: EngineApi;
  health: HealthResponse;
}

export type EngineConnectionState =
  | { kind: "connecting" }
  | { kind: "ready"; session: EngineSession }
  | { kind: "failed"; message: string };

export type ConnectFn = () => Promise<EngineSession>;

const STARTUP_RETRY = { attempts: 40, delayMs: 500 } as const;

export const connectToEngine: ConnectFn = async () => {
  const client = new EngineClient(await getEngineConnection());
  const health = await waitForEngine(client, STARTUP_RETRY);
  return { api: client, health };
};

export function useEngineConnection(connect: ConnectFn = connectToEngine): {
  state: EngineConnectionState;
  retry: () => void;
} {
  const [state, setState] = useState<EngineConnectionState>({ kind: "connecting" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    connect().then(
      (session) => {
        if (!cancelled) setState({ kind: "ready", session });
      },
      (error: unknown) => {
        const message = error instanceof Error ? error.message : String(error);
        if (!cancelled) setState({ kind: "failed", message });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [connect, attempt]);

  const retry = useCallback(() => {
    setState({ kind: "connecting" });
    setAttempt((n) => n + 1);
  }, []);
  return { state, retry };
}
