import { useTranslation } from "react-i18next";

import type { HealthResponse } from "../../shared/api/engine";

export function HomePage({
  health,
  onOpenSettings,
}: {
  health: HealthResponse;
  onOpenSettings: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="home">
      <h1 className="page-title">{t("home.title")}</h1>
      <p className="status status--ok" role="status">
        {t("engine.ready")} {/* <bdi> keeps the Latin version intact inside Hebrew text */}
        <bdi>v{health.version}</bdi>
      </p>
      <p>{t("home.comingSoon")}</p>
      <button type="button" className="primary" onClick={onOpenSettings}>
        {t("home.setUpModels")}
      </button>
    </div>
  );
}
