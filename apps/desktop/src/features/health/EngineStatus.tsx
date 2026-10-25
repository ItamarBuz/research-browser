import { useTranslation } from "react-i18next";

import { useEngineHealth, type ConnectFn } from "./useEngineHealth";

interface EngineStatusProps {
  connect?: ConnectFn;
}

export function EngineStatus({ connect }: EngineStatusProps) {
  const { t } = useTranslation();
  const { state, retry } = useEngineHealth(connect);

  switch (state.kind) {
    case "connecting":
      return (
        <p className="status status--pending" role="status">
          {t("engine.connecting")}
        </p>
      );
    case "ready":
      return (
        <p className="status status--ok" role="status">
          {t("engine.ready")}{" "}
          {/* <bdi> keeps the Latin version string's direction intact inside Hebrew text */}
          <bdi>v{state.health.version}</bdi>
        </p>
      );
    case "failed":
      return (
        <div className="status status--error" role="alert">
          <p>{t("engine.failed", { message: state.message })}</p>
          <button type="button" onClick={retry}>
            {t("engine.retry")}
          </button>
        </div>
      );
  }
}
