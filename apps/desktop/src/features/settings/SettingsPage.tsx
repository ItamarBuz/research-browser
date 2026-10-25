import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";

import { useEngine } from "../../shared/api/EngineContext";
import type { Tier } from "../../shared/api/engine";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { HardwareSection } from "./HardwareSection";
import { ModelsSection } from "./ModelsSection";
import { TierSection } from "./TierSection";
import { useModels } from "./useModels";

export function SettingsPage({ pollMs }: { pollMs?: number }) {
  const { t } = useTranslation();
  const api = useEngine();
  const loadSystem = useCallback(() => api.getSystem(), [api]);
  const system = useAsyncResource(loadSystem);
  const models = useModels(pollMs);
  const [actionError, setActionError] = useState<string>();

  const runAction = useCallback(async (action: () => Promise<void>) => {
    setActionError(undefined);
    try {
      await action();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  const changeTier = (tier: Tier | null) =>
    runAction(async () => {
      system.setData(await api.setTierOverride(tier));
      await models.reload(); // recommendations follow the effective tier
    });

  const download = (ids: string[]) => runAction(() => models.download(ids));

  const loadError = system.error ?? models.error;

  return (
    <div className="settings">
      <h1 className="page-title">{t("nav.settings")}</h1>
      {(loadError ?? actionError) && (
        <p className="status status--error" role="alert">
          {t("settings.error", { message: loadError ?? actionError })}
        </p>
      )}
      {system.data ? (
        <>
          <HardwareSection hardware={system.data.hardware} />
          <TierSection decision={system.data.tier} onChange={changeTier} />
        </>
      ) : (
        !loadError && <p role="status">{t("settings.loading")}</p>
      )}
      {models.data && <ModelsSection list={models.data} onDownload={download} />}
    </div>
  );
}
