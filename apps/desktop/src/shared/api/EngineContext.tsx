import { createContext, useContext, type ReactNode } from "react";

import type { EngineApi } from "./engine";

const EngineContext = createContext<EngineApi | null>(null);

export function EngineProvider({ api, children }: { api: EngineApi; children: ReactNode }) {
  return <EngineContext.Provider value={api}>{children}</EngineContext.Provider>;
}

/** The connected engine. Only valid below <EngineGate>, which provides it once ready. */
export function useEngine(): EngineApi {
  const api = useContext(EngineContext);
  if (!api) throw new Error("useEngine() called outside <EngineProvider>");
  return api;
}
