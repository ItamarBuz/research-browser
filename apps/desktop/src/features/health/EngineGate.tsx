import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { EngineProvider } from "../../shared/api/EngineContext";
import type { HealthResponse } from "../../shared/api/engine";
import { useEngineConnection, type ConnectFn } from "./useEngineHealth";

interface EngineGateProps {
  connect?: ConnectFn;
  /** Rendered once the engine is reachable, with the engine available via useEngine(). */
  children: (health: HealthResponse) => ReactNode;
}

/** Shows engine start-up progress or failure, and the app once the engine is ready. */
export function EngineGate({ connect, children }: EngineGateProps) {
  const { t } = useTranslation();
  const { state, retry } = useEngineConnection(connect);

  switch (state.kind) {
    case "connecting":
      return (
        <main className="app__main">
          <p className="status status--pending" role="status">
            {t("engine.connecting")}
          </p>
        </main>
      );
    case "failed":
      return (
        <main className="app__main">
          <div className="status status--error" role="alert">
            <p>{t("engine.failed", { message: state.message })}</p>
            <button type="button" onClick={retry}>
              {t("engine.retry")}
            </button>
          </div>
        </main>
      );
    case "ready":
      return (
        <EngineProvider api={state.session.api}>{children(state.session.health)}</EngineProvider>
      );
  }
}
