import { useTranslation } from "react-i18next";

import type { ModelInfo, ModelList } from "../../shared/api/engine";
import { formatBytes, formatPercent } from "../../shared/format";

type Download = (modelIds: string[]) => Promise<void>;

const NEEDS_DOWNLOAD = new Set(["not_downloaded", "failed"]);

function StatusCell({ model, onDownload }: { model: ModelInfo; onDownload: Download }) {
  const { t, i18n } = useTranslation();
  const { state } = model;
  const start = () => void onDownload([model.id]);

  switch (state.status) {
    case "not_downloaded":
      return (
        <button type="button" onClick={start}>
          {t("settings.models.download")}
        </button>
      );
    case "downloading": {
      const fraction = state.total_bytes > 0 ? state.downloaded_bytes / state.total_bytes : 0;
      return (
        <span className="progress">
          <progress
            max={state.total_bytes}
            value={state.downloaded_bytes}
            aria-label={t("settings.models.progressLabel", { name: model.name })}
          />
          {formatPercent(fraction, i18n.language)}
        </span>
      );
    }
    case "ready":
      return <span className="ok">{t("settings.models.ready")}</span>;
    case "failed":
      return (
        <span className="error-cell">
          <span className="error">{state.error ?? t("settings.models.failed")}</span>
          <button type="button" onClick={start}>
            {t("settings.models.retry")}
          </button>
        </span>
      );
  }
}

function ModelTable({ models, onDownload }: { models: ModelInfo[]; onDownload: Download }) {
  const { t, i18n } = useTranslation();
  return (
    <table className="models-table">
      <thead>
        <tr>
          <th scope="col">{t("settings.models.columns.model")}</th>
          <th scope="col">{t("settings.models.columns.purpose")}</th>
          <th scope="col">{t("settings.models.columns.size")}</th>
          <th scope="col">{t("settings.models.columns.license")}</th>
          <th scope="col">{t("settings.models.columns.status")}</th>
        </tr>
      </thead>
      <tbody>
        {models.map((model) => (
          <tr key={model.id}>
            <th scope="row">
              <bdi>{model.name}</bdi>
            </th>
            <td>{t(`settings.models.roles.${model.role}`)}</td>
            <td>{formatBytes(model.size_bytes, i18n.language)}</td>
            <td>
              <bdi>{model.license.toUpperCase()}</bdi>
            </td>
            <td>
              <StatusCell model={model} onDownload={onDownload} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function ModelsSection({ list, onDownload }: { list: ModelList; onDownload: Download }) {
  const { t, i18n } = useTranslation();
  const recommended = list.models.filter((m) => m.recommended);
  const optional = list.models.filter((m) => !m.recommended);
  const pending = recommended.filter((m) => NEEDS_DOWNLOAD.has(m.state.status));
  const pendingBytes = pending.reduce((sum, m) => sum + m.size_bytes, 0);

  return (
    <section className="settings-section" aria-labelledby="models-heading">
      <h2 id="models-heading">{t("settings.models.title")}</h2>
      <p className="muted">
        {t("settings.models.intro", { tier: t(`settings.tier.names.${list.tier}`) })}
      </p>

      {pending.length > 0 && (
        <button
          type="button"
          className="primary"
          onClick={() => void onDownload(pending.map((m) => m.id))}
        >
          {t("settings.models.downloadAll", { size: formatBytes(pendingBytes, i18n.language) })}
        </button>
      )}
      <ModelTable models={recommended} onDownload={onDownload} />

      {optional.length > 0 && (
        <details className="optional-models">
          <summary>{t("settings.models.optionalTitle", { count: optional.length })}</summary>
          <p className="muted">{t("settings.models.optionalIntro")}</p>
          <ModelTable models={optional} onDownload={onDownload} />
        </details>
      )}
    </section>
  );
}
