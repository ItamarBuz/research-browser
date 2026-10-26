import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";

import { useEngine } from "../../shared/api/EngineContext";
import type { OnlineSettingsUpdate, SourceName } from "../../shared/api/engine";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";

const SOURCES: readonly SourceName[] = ["openalex", "semantic_scholar", "arxiv", "europe_pmc"];

type KeyField = "openalex_api_key" | "semantic_scholar_api_key";

function ApiKeyField({
  field,
  stored,
  disabled,
  onSave,
}: {
  field: KeyField;
  stored: boolean;
  disabled: boolean;
  onSave: (field: KeyField, value: string) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [value, setValue] = useState("");
  const id = `key-${field}`;
  return (
    <div className="field">
      <label htmlFor={id}>{t(`online.keys.${field}`)}</label>
      <div className="row-actions">
        <input
          id={id}
          type="password"
          autoComplete="off"
          dir="ltr"
          disabled={disabled}
          placeholder={stored ? t("online.keys.storedPlaceholder") : ""}
          value={value}
          onChange={(event) => {
            setValue(event.target.value);
          }}
        />
        <button
          type="button"
          disabled={disabled || !value.trim()}
          onClick={() => {
            void onSave(field, value.trim()).then(() => {
              setValue("");
            });
          }}
        >
          {t("online.keys.save")}
        </button>
        {stored && (
          <button type="button" disabled={disabled} onClick={() => void onSave(field, "")}>
            {t("online.keys.remove")}
          </button>
        )}
      </div>
    </div>
  );
}

export function OnlineSourcesSection() {
  const { t } = useTranslation();
  const api = useEngine();
  const load = useCallback(() => api.getOnlineSettings(), [api]);
  const settings = useAsyncResource(load);
  const [email, setEmail] = useState<string>();
  const [error, setError] = useState<string>();

  async function update(change: Partial<OnlineSettingsUpdate>) {
    setError(undefined);
    try {
      settings.setData(await api.updateOnlineSettings(change));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  const view = settings.data;
  if (!view) return null;
  const emailValue = email ?? view.contact_email ?? "";

  return (
    <section className="settings-section" aria-labelledby="online-heading">
      <h2 id="online-heading">{t("online.settings.title")}</h2>
      <p className="muted">{t("online.settings.intro")}</p>

      <label className="toggle">
        <input
          type="checkbox"
          checked={view.enabled}
          onChange={(event) => void update({ enabled: event.target.checked })}
        />
        {t("online.settings.enabled")}
      </label>

      <fieldset className="source-list" disabled={!view.enabled}>
        <legend>{t("online.settings.sourcesLegend")}</legend>
        {SOURCES.map((source) => (
          <label key={source} className="toggle">
            <input
              type="checkbox"
              checked={view.sources[source] ?? true}
              onChange={(event) => void update({ sources: { [source]: event.target.checked } })}
            />
            <span>
              <strong>{t(`online.sources.${source}.name`)}</strong>
              <span className="muted"> · {t(`online.sources.${source}.description`)}</span>
            </span>
          </label>
        ))}
      </fieldset>

      <div className="field">
        <label htmlFor="contact-email">{t("online.settings.email")}</label>
        <p className="muted hint">{t("online.settings.emailHint")}</p>
        <div className="row-actions">
          <input
            id="contact-email"
            type="email"
            dir="ltr"
            value={emailValue}
            onChange={(event) => {
              setEmail(event.target.value);
            }}
          />
          <button
            type="button"
            onClick={() =>
              void update(
                emailValue.trim()
                  ? { contact_email: emailValue.trim() }
                  : { clear_contact_email: true },
              )
            }
          >
            {t("online.keys.save")}
          </button>
        </div>
      </div>

      <h3>{t("online.keys.title")}</h3>
      <p className="muted hint">
        {view.secure_storage_available ? t("online.keys.intro") : t("online.keys.unavailable")}
      </p>
      <ApiKeyField
        field="openalex_api_key"
        stored={view.has_openalex_key}
        disabled={!view.secure_storage_available}
        onSave={(field, value) => update({ [field]: value })}
      />
      <ApiKeyField
        field="semantic_scholar_api_key"
        stored={view.has_semantic_scholar_key}
        disabled={!view.secure_storage_available}
        onSave={(field, value) => update({ [field]: value })}
      />
      {(error ?? settings.error) && (
        <p className="error" role="alert">
          {error ?? settings.error}
        </p>
      )}
    </section>
  );
}
