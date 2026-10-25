import { useCallback, useEffect, useState } from "react";

import {
  EngineClient,
  getEngineConnection,
  waitForEngine,
  type HealthResponse,
} from "../../shared/api/engine";

export type EngineHealthState =
  | { kind: "connecting" }
  | { kind: "ready"; health: HealthResponse }
  | { kind: "failed"; message: string };

export type ConnectFn = () => Promise<HealthResponse>;

const STARTUP_RETRY = { attempts: 40, delayMs: 500 } as const;

export const connectToEngine: ConnectFn = async () => {
  const client = new EngineClient(await getEngineConnection());
  return waitForEngine(client, STARTUP_RETRY);
};

export function useEngineHealth(connect: ConnectFn = connectToEngine): {
  state: EngineHealthState;
  retry: () => void;
} {
  const [state, setState] = useState<EngineHealthState>({ kind: "connecting" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    connect().then(
      (health) => {
        if (!cancelled) setState({ kind: "ready", health });
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
